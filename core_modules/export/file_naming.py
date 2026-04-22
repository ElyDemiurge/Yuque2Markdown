"""文件名与路径安全处理工具。"""

from __future__ import annotations

import os
import re
from pathlib import Path

INVALID_FILE_CHARS = r'[\\/:*?"<>|]'


def sanitize_name(name: str, fallback: str = "untitled") -> str:
    """将标题清洗为可安全落盘的文件名。

    参数:
        name: 原始名称。
        fallback: 清洗后为空时使用的兜底名称。

    返回:
        可安全用于文件名的字符串。
    """
    # 明显像路径输入时只保留末段，避免把目录结构带进输出文件名；
    # 普通标题里的 "/"（例如 "/bin/sh"）则保留语义，统一替换成 "_".
    if os.path.isabs(name) or re.search(r"(^|[/\\])\.\.([/\\]|$)", name):
        name = os.path.basename(name)

    # 将分隔符视为普通非法字符处理，避免标题中包含 "/" 时被错误截断。
    name = name.replace("/", "_").replace("\\", "_")

    # 将文件系统不接受的字符统一替换为 "_".
    cleaned = re.sub(INVALID_FILE_CHARS, "_", name).strip()

    # 将连续空白压缩为单个空格。
    cleaned = re.sub(r"\s+", " ", cleaned)

    # 去掉结尾的点，避免后续兼容其他文件系统时出现问题。
    cleaned = cleaned.rstrip(".")

    # 如果清洗后只剩空串或 "." / ".."，则回退到兜底文件名。
    if not cleaned or cleaned in (".", ".."):
        return fallback

    # 限制长度，避免极端长标题导致路径过长。
    MAX_NAME_LENGTH = 200
    if len(cleaned) > MAX_NAME_LENGTH:
        cleaned = cleaned[:MAX_NAME_LENGTH].rstrip()

    return cleaned


def unique_name(name: str, used_names: set[str], suffix: str | None = None) -> str:
    """为同目录下的重名文件生成唯一名称。

    参数:
        name: 原始名称。
        used_names: 当前目录中已占用的名称集合，会被原地更新。
        suffix: 首次冲突时优先尝试追加的自定义后缀。
    """
    candidate = name
    index = 1
    while candidate in used_names:
        if suffix is not None:
            candidate = f"{name}-{suffix}"
            suffix = None
        else:
            candidate = f"{name}-{index}"
            index += 1
    used_names.add(candidate)
    return candidate


def safe_join(base: Path, *parts: str) -> Path:
    """拼接路径，并保证结果始终位于 ``base`` 目录下。

    参数:
        base: 基础目录。
        *parts: 待拼接的路径段。

    返回:
        经过清洗和校验后的路径对象。

    异常:
        ValueError: 检测到路径逃逸风险时抛出。
    """
    result = base
    for part in parts:
        if re.match(r"^\.\.[/\\][^/\\]+$", part):
            raise ValueError(f"Path traversal detected: {part}")
        sanitized = sanitize_name(part)
        result = result / sanitized

    # 优先用 resolve() 做严格校验；失败时再退回到保守的字符串检查。
    try:
        result_resolved = result.resolve()
        base_resolved = base.resolve()
    except OSError:
        if ".." in str(result) or str(result).startswith("/"):
            raise ValueError(f"Path traversal detected: {result}")
        return result

    # 结果必须仍然位于 base 下，不能借路径拼接逃逸到目录外。
    if not str(result_resolved).startswith(str(base_resolved) + os.sep) and result_resolved != base_resolved:
        raise ValueError(f"Path traversal detected: {result} escapes base {base}")

    return result
