"""知识库输入解析工具。

本模块负责把用户输入的知识库标识或完整 URL 解析成统一的 ``RepoRef``。
"""

from __future__ import annotations

from urllib.parse import urlparse

from core_modules.export.models import RepoRef


def resolve_repo_input(value: str) -> RepoRef:
    """解析知识库输入。

    参数:
        value: 用户输入的知识库标识，支持 ``group_login/book_slug`` 或完整 URL。

    返回:
        解析后的 ``RepoRef`` 对象。

    异常:
        ValueError: 输入为空或格式不合法时抛出。
    """
    raw = value.strip()
    if not raw:
        raise ValueError("知识库输入不能为空")

    if raw.startswith("http://") or raw.startswith("https://"):
        # URL 模式下直接提取路径中的前两段，分别作为 group_login 与 book_slug。
        parsed = urlparse(raw)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("知识库 URL 不合法，应包含 group_login 和 book_slug")
        group_login, book_slug = parts[0], parts[1]
        return RepoRef(group_login=group_login, book_slug=book_slug, url=raw)

    # 短格式必须严格为两段，避免把额外路径误判为合法知识库输入。
    parts = [part for part in raw.split("/") if part]
    if len(parts) != 2:
        raise ValueError("知识库标识不合法，应为 group_login/book_slug")
    return RepoRef(group_login=parts[0], book_slug=parts[1], url=f"https://www.yuque.com/{parts[0]}/{parts[1]}")
