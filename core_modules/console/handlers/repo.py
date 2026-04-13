"""知识库与文档选择处理器。"""

from core_modules.config.models import AppConfig, SessionState
from core_modules.console.helpers import filter_repos
from core_modules.console.menu import show_message, run_select_list
from core_modules.console.state.manager import build_selected_docs_text, count_docs
from core_modules.console.state.view import format_rate_limit
from core_modules.export.cli import fetch_repo_toc
from core_modules.selector import select_doc_ids


def handle_repo_input_inline(
    config: AppConfig,
    session: SessionState,
    value: str,
    *,
    build_client_from_config,
) -> bool:
    """Validate and process repository input inline."""
    token = (config.token or "").strip()
    if not session.connection_ok:
        session.token_status_message = "Token 无效，无法校验知识库"
        show_message("Token 无效", ["请先设置有效 Token 并刷新连接状态。"])
        return False
    try:
        client = build_client_from_config(config, token)
        repo, toc_tree = fetch_repo_toc(client, value)
    except Exception as exc:
        session.status_message = f"知识库校验失败: {exc}"
        show_message("知识库校验失败", [str(exc)])
        return False
    session.repo_input = f"{repo.group_login}/{repo.book_slug}"
    session.repo_display_name = repo.name or repo.book_slug
    session.repo_namespace = repo.namespace or f"{repo.group_login}/{repo.book_slug}"
    session.repo_url = repo.url or ""
    session.selected_doc_count = count_docs(toc_tree)
    session.status_message = f"知识库校验通过: {session.repo_namespace}"
    session.dirty = True
    return True


def handle_repo_selection(
    session: SessionState,
    repos: list[dict],
    rate_limit_summary: str,
) -> bool:
    """Handle repository selection from list."""
    if not repos:
        session.status_message = "暂无可选知识库，请先刷新连接"
        show_message("暂无可选知识库", ["请先刷新连接状态，确认 token 有效且账号有可访问仓库。"])
        return False
    filtered_repos = filter_repos(repos, session.repo_filter)
    repo_lines = [f"{repo.get('name')} | https://www.yuque.com/{repo.get('namespace')}" for repo in filtered_repos]
    index, filter_text = run_select_list(
        "选择知识库",
        repo_lines,
        initial_index=session.repo_list_index,
        filter_text=session.repo_filter,
        empty_message="当前过滤条件下没有匹配的知识库",
    )
    session.repo_filter = filter_text
    if index is None:
        return False
    if not filtered_repos or index >= len(filtered_repos):
        return False
    repo = filtered_repos[index]
    session.repo_list_index = index
    namespace = repo.get("namespace")
    if not namespace:
        return False
    session.repo_input = namespace
    session.repo_display_name = repo.get("name") or namespace.split("/")[-1]
    session.repo_namespace = namespace
    session.repo_url = f"https://www.yuque.com/{namespace}"
    session.status_message = f"已选择知识库: {session.repo_display_name}"
    session.dirty = True
    return True


def handle_doc_selection(
    config: AppConfig,
    session: SessionState,
    rate_limit_summary: str,
    *,
    build_client_from_config,
) -> tuple[str, bool]:
    """Handle document selection with TOC navigation."""
    token = (config.token or "").strip()
    if not session.connection_ok:
        session.token_status_message = "Token 无效，无法读取目录"
        show_message("Token 无效", ["请先设置有效 Token 并刷新连接状态。"])
        return rate_limit_summary, False
    if not session.repo_input:
        session.status_message = "请先设置知识库"
        show_message("缺少知识库", ["请先手动输入知识库，或从列表选择知识库。"])
        return rate_limit_summary, False
    client = build_client_from_config(config, token)
    _, toc_tree = fetch_repo_toc(client, session.repo_input)
    summary_lines = [
        f"知识库: {session.repo_display_name or session.repo_namespace or session.repo_input}",
        f"当前选择: {build_selected_docs_text(session)}",
    ]
    selected = select_doc_ids(toc_tree, initial_selected=session.selected_doc_ids, summary_lines=summary_lines)
    session.selected_doc_ids = selected if selected else None
    session.selected_doc_count = len(selected) if selected else count_docs(toc_tree)
    session.status_message = f"文档选择已更新: {'已选 ' + str(len(selected)) + ' 篇' if selected else '全部文档'}"
    session.dirty = True
    return format_rate_limit(client.last_rate_limit), True
