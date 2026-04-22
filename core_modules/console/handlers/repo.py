"""知识库与文档选择处理器。"""

from core_modules.config.models import AppConfig, SessionState, active_auth_value, auth_mode_label, normalize_auth_mode
from core_modules.console.helpers import filter_repos
from core_modules.console.menu import show_message, run_select_list
from core_modules.console.state.manager import build_selected_docs_text, count_docs
from core_modules.console.state.view import format_rate_limit
from core_modules.export.cli import fetch_repo_toc
from core_modules.console.selector import select_doc_ids


def _reset_doc_selection(session: SessionState, total_docs: int = 0) -> None:
    """切换知识库后清空旧的文档选择状态，避免沿用上一库的选择结果。"""
    session.selected_doc_ids = None
    session.selected_doc_count = total_docs


def _repo_owner_login(repo: dict) -> str:
    user = repo.get("user") or {}
    login = str(user.get("login") or "").strip()
    if login:
        return login
    namespace = str(repo.get("namespace") or "").strip()
    if "/" in namespace:
        return namespace.split("/", 1)[0]
    return ""


def _unsupported_shared_repo(repo: dict, current_user_login: str) -> bool:
    if not current_user_login:
        return False
    owner_login = _repo_owner_login(repo)
    return bool(owner_login and owner_login != current_user_login)


def handle_repo_input_inline(
    config: AppConfig,
    session: SessionState,
    value: str,
    *,
    build_client_from_config,
    append_console_log,
) -> bool:
    """校验并处理用户手动输入的知识库。"""
    credential = active_auth_value(config)
    label = auth_mode_label(normalize_auth_mode(config.auth_mode))
    if not session.connection_ok:
        session.token_status_message = f"{label} 无效，无法校验知识库"
        show_message(f"{label} 无效", [f"请先设置有效 {label} 并刷新连接状态。"])
        return False
    try:
        client = build_client_from_config(config, credential)
        repo, toc_tree = fetch_repo_toc(client, value)
    except Exception as exc:
        session.status_message = f"知识库校验失败: {exc}"
        append_console_log(f"知识库校验失败: 输入={value} 错误={exc}")
        show_message("知识库校验失败", [str(exc)])
        return False
    if session.current_user_login and repo.group_login != session.current_user_login:
        append_console_log(f"知识库校验拒绝: 输入={value} 原因=非当前账号知识库")
        show_message("暂不支持导出", ["当前项目仅支持导出当前账号自己的个人知识库。", "非当前登录账号的知识库暂不支持导出，如受邀协作知识库。"])
        return False
    previous_repo = session.repo_input
    session.repo_input = f"{repo.group_login}/{repo.book_slug}"
    session.repo_display_name = repo.name or repo.book_slug
    session.repo_namespace = repo.namespace or f"{repo.group_login}/{repo.book_slug}"
    session.repo_url = repo.url or ""
    if session.repo_input != previous_repo:
        _reset_doc_selection(session, count_docs(toc_tree))
    else:
        session.selected_doc_count = count_docs(toc_tree)
    session.status_message = f"知识库校验通过: {session.repo_namespace}"
    session.dirty = True
    append_console_log(f"知识库校验成功: 输入={value} 知识库={session.repo_input} 文档数={session.selected_doc_count}")
    return True


def handle_repo_selection(
    config: AppConfig,
    session: SessionState,
    repos: list[dict],
    rate_limit_summary: str,
    *,
    build_client_from_config,
    append_console_log,
) -> bool:
    """处理“从列表选择知识库”动作。"""
    if not repos:
        session.status_message = "暂无可选知识库，请先刷新连接"
        append_console_log("知识库选择失败: 当前没有可选知识库")
        show_message("暂无可选知识库", ["请先刷新连接状态，确认登录凭据有效且账号有可访问仓库。"])
        return False
    filtered_repos = filter_repos(repos, session.repo_filter)
    disabled_indexes = {
        index
        for index, repo in enumerate(filtered_repos)
        if _unsupported_shared_repo(repo, session.current_user_login)
    }
    repo_lines = []
    for repo in filtered_repos:
        line = f"{repo.get('name')} | https://www.yuque.com/{repo.get('namespace')}"
        if _unsupported_shared_repo(repo, session.current_user_login):
            line += "  （非当前登录账号的知识库暂不支持导出，如受邀协作知识库）"
        repo_lines.append(line)
    index, filter_text = run_select_list(
        "选择知识库",
        repo_lines,
        initial_index=session.repo_list_index,
        filter_text=session.repo_filter,
        empty_message="当前过滤条件下没有匹配的知识库",
        disabled_indexes=disabled_indexes,
    )
    session.repo_filter = filter_text
    if index is None:
        append_console_log(f"知识库选择取消: 过滤词={filter_text or '-'}")
        return False
    if not filtered_repos or index >= len(filtered_repos):
        return False
    repo = filtered_repos[index]
    session.repo_list_index = index
    namespace = repo.get("namespace")
    if not namespace:
        return False
    previous_repo = session.repo_input
    session.repo_input = namespace
    session.repo_display_name = repo.get("name") or namespace.split("/")[-1]
    session.repo_namespace = namespace
    session.repo_url = f"https://www.yuque.com/{namespace}"
    if session.repo_input != previous_repo:
        total_docs = 0
        credential = active_auth_value(config)
        if session.connection_ok and credential:
            try:
                client = build_client_from_config(config, credential)
                _, toc_tree = fetch_repo_toc(client, session.repo_input)
                total_docs = count_docs(toc_tree)
            except Exception:
                total_docs = 0
        _reset_doc_selection(session, total_docs)
    session.status_message = f"已选择知识库: {session.repo_display_name}"
    session.dirty = True
    append_console_log(f"知识库选择成功: 知识库={session.repo_input} 过滤词={filter_text or '-'} 文档数={session.selected_doc_count}")
    return True


def handle_doc_selection(
    config: AppConfig,
    session: SessionState,
    rate_limit_summary: str,
    *,
    build_client_from_config,
    append_console_log,
) -> tuple[str, bool]:
    """进入目录树选择器并更新文档选择结果。"""
    credential = active_auth_value(config)
    label = auth_mode_label(normalize_auth_mode(config.auth_mode))
    if not session.connection_ok:
        session.token_status_message = f"{label} 无效，无法读取目录"
        append_console_log("文档选择失败: 原因=登录状态无效")
        show_message(f"{label} 无效", [f"请先设置有效 {label} 并刷新连接状态。"])
        return rate_limit_summary, False
    if not session.repo_input:
        session.status_message = "请先设置知识库"
        append_console_log("文档选择失败: 原因=未选择知识库")
        show_message("缺少知识库", ["请先手动输入知识库，或从列表选择知识库。"])
        return rate_limit_summary, False
    client = None
    try:
        client = build_client_from_config(config, credential)
        _, toc_tree = fetch_repo_toc(client, session.repo_input)
        summary_lines = [
            f"知识库: {session.repo_display_name or session.repo_namespace or session.repo_input}",
            f"当前选择: {build_selected_docs_text(session)}",
        ]
        selected = select_doc_ids(toc_tree, initial_selected=session.selected_doc_ids, summary_lines=summary_lines)
    except Exception as exc:  # noqa: BLE001
        session.status_message = f"文档选择失败: {exc}"
        session.last_error_text = str(exc)
        append_console_log(f"文档选择失败: 知识库={session.repo_input} 错误={exc}")
        show_message("文档选择失败", [str(exc)])
        if client is not None:
            return format_rate_limit(getattr(client, "last_rate_limit", {}) or {}), False
        return rate_limit_summary, False
    session.selected_doc_ids = selected if selected else None
    session.selected_doc_count = len(selected) if selected else count_docs(toc_tree)
    session.status_message = f"文档选择已更新: {'已选 ' + str(len(selected)) + ' 篇' if selected else '全部文档'}"
    session.last_error_text = ""
    session.dirty = True
    append_console_log(f"文档选择成功: 知识库={session.repo_input} 已选={len(selected)} 总数={count_docs(toc_tree)}")
    return format_rate_limit(client.last_rate_limit), True
