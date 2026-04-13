from __future__ import annotations

from urllib.parse import urlparse

from core_modules.export.models import RepoRef


def resolve_repo_input(value: str) -> RepoRef:
    raw = value.strip()
    if not raw:
        raise ValueError("知识库输入不能为空")

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("知识库 URL 不合法，应包含 group_login 和 book_slug")
        group_login, book_slug = parts[0], parts[1]
        return RepoRef(group_login=group_login, book_slug=book_slug, url=raw)

    parts = [part for part in raw.split("/") if part]
    if len(parts) != 2:
        raise ValueError("知识库标识不合法，应为 group_login/book_slug")
    return RepoRef(group_login=parts[0], book_slug=parts[1], url=f"https://www.yuque.com/{parts[0]}/{parts[1]}")
