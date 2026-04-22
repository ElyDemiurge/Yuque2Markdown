"""控制台会话状态辅助函数。

本模块只处理 ``SessionState`` 的轻量计算，不直接参与界面渲染。
"""

from __future__ import annotations

from core_modules.config.models import SessionState
from core_modules.export.models import TocNode


def remember_menu_index(session: SessionState, menu_key: str, items: list, action: str) -> None:
    """记录菜单上次命中的焦点索引。

    参数:
        session: 当前会话状态。
        menu_key: 菜单标识，用于区分主菜单、导出设置等不同页面。
        items: 当前菜单项列表。
        action: 本次触发的动作键。

    说明:
        当动作来自行内选项时，会把索引记录到所属菜单行，便于用户下次返回时保留焦点。
    """
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
    """生成人类可读的文档选择范围文案。

    参数:
        session: 当前会话状态。

    返回:
        ``已选 N 篇``、``全部（共 N 篇）`` 或 ``全部``。
    """
    if session.selected_doc_ids:
        return f"已选 {len(session.selected_doc_ids)} 篇"
    if session.selected_doc_count:
        return f"全部（共 {session.selected_doc_count} 篇）"
    return "全部"


def count_docs(nodes: list[TocNode]) -> int:
    """递归统计目录树中的文档数量。

    参数:
        nodes: 目录树根节点列表。

    返回:
        所有 ``DOC`` 节点的数量。
    """
    total = 0
    for node in nodes:
        if getattr(node, "node_type", None) == "DOC" and getattr(node, "doc_id", None):
            total += 1
        total += count_docs(getattr(node, "children", []))
    return total
