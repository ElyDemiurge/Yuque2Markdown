"""Session state helpers for Yuque2Markdown console."""

from __future__ import annotations

from core_modules.config.models import SessionState


def remember_menu_index(session: SessionState, menu_key: str, items: list, action: str) -> None:
    """Remember selected index for a menu action."""
    for index, item in enumerate(items):
        if item.key == action:
            session.menu_index_map[menu_key] = index
            return


def build_selected_docs_text(session: SessionState) -> str:
    """Build text describing selected docs."""
    if session.selected_doc_ids:
        return f"已选 {len(session.selected_doc_ids)} 篇"
    if session.selected_doc_count:
        return f"全部（共 {session.selected_doc_count} 篇）"
    return "全部"


def count_docs(nodes) -> int:
    """递归统计目录树中的文档数量。"""
    total = 0
    for node in nodes:
        if getattr(node, "node_type", None) == "DOC" and getattr(node, "doc_id", None):
            total += 1
        total += count_docs(getattr(node, "children", []))
    return total


def reset_connection_related_state(session: SessionState) -> None:
    """Reset connection-dependent runtime state."""
    session.connection_ok = False
    session.current_user_label = "未检查"
    session.network_test_message = ""


def mark_token_changed(session: SessionState, has_token: bool) -> None:
    """Update session state after token changes."""
    reset_connection_related_state(session)
    session.last_error_text = ""
    session.token_status_message = "已重新设置 Token，请手动刷新" if has_token else "Token 已清空"


def mark_network_config_changed(session: SessionState) -> None:
    """Update session state after network config changes."""
    session.network_test_message = ""
    session.last_error_text = ""
    session.token_status_message = "网络配置已修改，请重新测试"
    session.dirty = True
