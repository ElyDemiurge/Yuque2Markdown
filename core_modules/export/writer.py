"""导出文件写入工具。

本模块封装常用的目录创建与文本、二进制、JSON 文件写入逻辑。
"""

from __future__ import annotations

import json
from pathlib import Path


def ensure_dir(path: Path) -> None:
    """确保目录存在，不存在时递归创建。"""
    path.mkdir(parents=True, exist_ok=True)


def write_text_file(path: Path, content: str) -> None:
    """写入 UTF-8 文本文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_binary_file(path: Path, content: bytes) -> None:
    """写入二进制文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_json_file(path: Path, data: dict, *, indent: int = 2) -> None:
    """将字典数据写入 JSON 文件。

    参数:
        path: 目标文件路径。
        data: 需要写入的字典数据。
        indent: JSON 缩进空格数。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
