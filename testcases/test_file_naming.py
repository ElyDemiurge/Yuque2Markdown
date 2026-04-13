"""Tests for file naming utilities."""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from core_modules.export.file_naming import sanitize_name, unique_name, safe_join


# ── sanitize_name tests ────────────────────────────────────────

def test_sanitize_normal():
    assert sanitize_name("我的文档") == "我的文档"


def test_sanitize_removes_invalid_chars():
    assert sanitize_name('file<name>') == "file_name_"
    assert sanitize_name("path/to/file") == "path_to_file"
    assert sanitize_name('file*name?test') == "file_name_test"


def test_sanitize_path_traversal():
    """Path traversal attempts should be neutralized to just the basename."""
    assert sanitize_name("../../../etc/passwd") == "passwd"
    assert sanitize_name("foo/bar/../../../etc/passwd") == "etc"
    assert sanitize_name("/etc/passwd") == "passwd"
    assert sanitize_name("..\\..\\windows\\system32") == "windows"


def test_sanitize_dots_only():
    assert sanitize_name("..") == "untitled"
    assert sanitize_name(".") == "untitled"
    assert sanitize_name("") == "untitled"


def test_sanitize_whitespace():
    assert sanitize_name("  hello world  ") == "hello world"
    assert sanitize_name("a    b") == "a b"


def test_sanitize_trailing_dot():
    assert sanitize_name("filename.") == "filename"


def test_sanitize_fallback():
    assert sanitize_name("", fallback="custom") == "custom"


def test_sanitize_long_name():
    long_name = "a" * 300
    result = sanitize_name(long_name)
    assert len(result) == 200


def test_sanitize_mixed():
    assert sanitize_name("  foo//bar<test>..md  ") == "foo_bar_test_"


# ── unique_name tests ─────────────────────────────────────────

def test_unique_name_simple():
    used: set[str] = set()
    assert unique_name("doc", used) == "doc"
    assert "doc" in used


def test_unique_name_duplicate():
    used = {"doc"}
    assert unique_name("doc", used) == "doc-1"
    assert unique_name("doc", used) == "doc-2"
    assert "doc-1" in used
    assert "doc-2" in used


def test_unique_name_with_suffix():
    used: set[str] = set()
    assert unique_name("doc", used, suffix="42") == "doc"
    assert unique_name("doc", used, suffix="42") == "doc-42"
    assert unique_name("doc", used, suffix="42") == "doc-1"


# ── safe_join tests ───────────────────────────────────────────

def test_safe_join_simple(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    result = safe_join(base, "subdir", "file.txt")
    assert result == base / "subdir" / "file.txt"
    assert str(result).startswith(str(base))


def test_safe_join_traversal_blocked(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    try:
        safe_join(base, "../outside")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "traversal" in str(e).lower()


def test_safe_join_path_traversal_in_name(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    result = safe_join(base, "../../../etc/passwd")
    # Should sanitize the traversal component
    assert str(result).startswith(str(base))
    assert ".." not in str(result)


def test_safe_join_multiple_parts(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    result = safe_join(base, "a", "b", "c")
    assert result == base / "a" / "b" / "c"


# ── combined usage tests ──────────────────────────────────────

def test_sanitize_then_unique():
    """sanitize_name output should work correctly with unique_name."""
    used: set[str] = set()
    raw = "My Doc<test>"
    safe = sanitize_name(raw)
    name = unique_name(safe, used)
    assert name == "My_Doc_test_"
    assert name in used


def test_path_traversal_protection_end_to_end():
    """A real-world path traversal attack should be fully neutralized."""
    attack = "../../../tmp/evil.sh"
    safe = sanitize_name(attack)
    # Should not contain path separators or dots
    assert "/" not in safe
    assert "\\" not in safe
    assert safe == "evil.sh"


if __name__ == "__main__":
    import tempfile
    import traceback

    tests = [
        obj
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]

    passed = failed = 0
    for test in tests:
        try:
            if "tmp_path" in test.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as tmp:
                    test(Path(tmp))
            else:
                test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
