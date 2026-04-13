from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core_modules.export.models import CheckpointState, DocExportState, RepoRef

CHECKPOINT_FILE_NAME = "_export_checkpoint.json"


def checkpoint_path(output_dir: Path) -> Path:
    return output_dir / CHECKPOINT_FILE_NAME


def create_checkpoint(repo: RepoRef) -> CheckpointState:
    return CheckpointState(
        repo={
            "group_login": repo.group_login,
            "book_slug": repo.book_slug,
            "book_id": repo.book_id,
        },
        export_started_at=datetime.now(timezone.utc).isoformat(),
    )


def load_checkpoint(output_dir: Path) -> CheckpointState | None:
    path = checkpoint_path(output_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_doc_states = data.get("doc_states", {})
    data["doc_states"] = {key: DocExportState(**value) for key, value in raw_doc_states.items()}
    return CheckpointState(**data)


def save_checkpoint(output_dir: Path, state: CheckpointState) -> None:
    path = checkpoint_path(output_dir)
    path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
