"""Tests for export writer utilities."""
import sys
sys.path.insert(0, ".")

import json
from pathlib import Path
from core_modules.export.writer import ensure_dir, write_text_file, write_binary_file, write_json_file


def test_write_text_file_creates_parent_dirs(tmp_path):
    """父目录不存在时应自动创建。"""
    path = tmp_path / "a" / "b" / "c" / "file.txt"
    write_text_file(path, "hello world")
    assert path.read_text(encoding="utf-8") == "hello world"


def test_write_text_file_utf8(tmp_path):
    """应正确处理 UTF-8 内容（包括中文）。"""
    path = tmp_path / "test.txt"
    write_text_file(path, "你好世界\n欢迎使用\n")
    assert path.read_text(encoding="utf-8") == "你好世界\n欢迎使用\n"


def test_write_binary_file_creates_parent_dirs(tmp_path):
    """二进制写入也应自动创建父目录。"""
    path = tmp_path / "img" / "photo.png"
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    write_binary_file(path, content)
    assert path.read_bytes() == content


def test_write_binary_file_exact_bytes(tmp_path):
    """应正确写入精确字节内容。"""
    path = tmp_path / "data.bin"
    content = bytes(range(256))
    write_binary_file(path, content)
    assert path.read_bytes() == content


def test_write_json_file_indent_and_ascii(tmp_path):
    """JSON 应使用 indent=2 格式化，保留非 ASCII 字符。"""
    path = tmp_path / "data.json"
    data = {"name": "我的文档", "count": 42, "tags": ["a", "b"]}
    write_json_file(path, data)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == data
    content = path.read_text(encoding="utf-8")
    # 验证缩进格式
    assert "\n" in content
    # 验证中文未被转义
    assert "我的文档" in content


def test_write_json_file_overwrites(tmp_path):
    """重复写入同一文件应覆盖。"""
    path = tmp_path / "overwrite.json"
    write_json_file(path, {"v": 1})
    write_json_file(path, {"v": 2})
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == {"v": 2}


def test_ensure_dir_creates_existing(tmp_path):
    """ensure_dir 对已存在的目录不应报错。"""
    d = tmp_path / "existing"
    d.mkdir()
    ensure_dir(d)  # 不应抛出


def test_ensure_dir_creates_nested(tmp_path):
    """ensure_dir 应创建嵌套目录。"""
    d = tmp_path / "a" / "b" / "c"
    ensure_dir(d)
    assert d.is_dir()
