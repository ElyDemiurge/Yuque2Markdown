from __future__ import annotations

import os
import re
from pathlib import Path

INVALID_FILE_CHARS = r'[\\/:*?"<>|]'


def sanitize_name(name: str, fallback: str = "untitled") -> str:
    # Step 1: Extract only the basename to prevent path traversal attacks
    # This handles inputs like "../../../etc/passwd" or "foo/bar/../../../etc/passwd"
    name = os.path.basename(name)

    # Step 2: Remove any path separators that somehow got through
    name = name.replace("/", "_").replace("\\", "_")

    # Step 3: Remove invalid file characters
    cleaned = re.sub(INVALID_FILE_CHARS, "_", name).strip()

    # Step 4: Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Step 5: Remove trailing dots (problematic on Windows)
    cleaned = cleaned.rstrip(".")

    # Step 6: Reject empty or dot-only names
    if not cleaned or cleaned in (".", ".."):
        return fallback

    # Step 7: Enforce length limit to prevent filesystem issues
    MAX_NAME_LENGTH = 200
    if len(cleaned) > MAX_NAME_LENGTH:
        cleaned = cleaned[:MAX_NAME_LENGTH].rstrip()

    return cleaned


def unique_name(name: str, used_names: set[str], suffix: str | None = None) -> str:
    candidate = name
    index = 1
    while candidate in used_names:
        extra = suffix or str(index)
        candidate = f"{name}-{extra}"
        index += 1
    used_names.add(candidate)
    return candidate


def safe_join(base: Path, *parts: str) -> Path:
    """Safely join path components, ensuring the result stays within base directory.

    This prevents directory traversal attacks by validating that the resulting
    path stays within the base directory after resolution.

    Args:
        base: The base directory that must contain the result
        *parts: Path components to join

    Returns:
        The resolved safe path

    Raises:
        ValueError: If the resulting path would escape the base directory
    """
    result = base
    for part in parts:
        sanitized = sanitize_name(part)
        result = result / sanitized

    # Resolve and verify the path stays within base
    try:
        result_resolved = result.resolve()
        base_resolved = base.resolve()
    except OSError:
        # resolve() can fail for restricted paths; fall back to string check
        if ".." in str(result) or str(result).startswith("/"):
            raise ValueError(f"Path traversal detected: {result}")
        return result

    # Verify result is within base (handles Windows drive differences automatically)
    if not str(result_resolved).startswith(str(base_resolved) + os.sep) and result_resolved != base_resolved:
        raise ValueError(f"Path traversal detected: {result} escapes base {base}")

    return result

