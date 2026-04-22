"""导出断点文件的读写工具。"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core_modules.export.models import CheckpointState, DocExportState, RepoRef

CHECKPOINT_FILE_NAME = "_export_checkpoint.json"


def checkpoint_path(output_dir: Path) -> Path:
    """返回指定输出目录下的断点文件路径。"""
    return output_dir / CHECKPOINT_FILE_NAME


def create_checkpoint(repo: RepoRef) -> CheckpointState:
    """根据知识库信息创建新的断点对象。"""
    return CheckpointState(
        repo={
            "group_login": repo.group_login,
            "book_slug": repo.book_slug,
            "book_id": repo.book_id,
        },
        export_started_at=datetime.now(timezone.utc).isoformat(),
    )


def load_checkpoint(output_dir: Path) -> CheckpointState | None:
    """读取断点文件。

    参数:
        output_dir: 当前知识库导出目录。

    返回:
        断点文件存在时返回 ``CheckpointState``，否则返回 ``None``。
    """
    path = checkpoint_path(output_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_doc_states = data.get("doc_states", {})
    # JSON 中的文档状态需要还原为 dataclass，便于后续代码按对象访问字段。
    data["doc_states"] = {key: DocExportState(**value) for key, value in raw_doc_states.items()}
    return CheckpointState(**data)


def save_checkpoint(output_dir: Path, state: CheckpointState) -> None:
    """把断点对象写回磁盘。"""
    path = checkpoint_path(output_dir)
    path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
