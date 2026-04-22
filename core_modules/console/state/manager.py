"""控制台会话状态辅助函数。"""

from __future__ import annotations

from core_modules.config.models import SessionState


def remember_menu_index(session: SessionState, menu_key: str, items: list, action: str) -> None:
    """记住菜单当前选中的索引。"""
    for index, item in enumerate(items):
        if item.key == action:
            session.menu_index_map[menu_key] = index
            return
        inline_choices = getattr(item, "inline_choices", None) or []
        for choice in inline_choices:
            if getattr(choice, "key", None) == action:
                session.menu_index_map[menu_key] = index
                return


def build_selected_docs_text(session: SessionState) -> str:
    """生成文档选择范围的展示文案。"""
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
