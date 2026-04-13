from __future__ import annotations

from core_modules.export.models import TocNode


def build_toc_tree(raw_items: list[dict]) -> list[TocNode]:
    nodes_by_uuid: dict[str, TocNode] = {}
    ordered_nodes: list[TocNode] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        node_type = str(item.get("type") or item.get("node_type") or "DOC").upper()
        title = item.get("title") or item.get("name") or "未命名节点"
        visible = item.get("visible", 1) != 0
        doc_id = item.get("doc_id") or item.get("id")
        if not isinstance(doc_id, int):
            doc_id = None
        node = TocNode(
            uuid=item.get("uuid"),
            node_type=node_type,
            title=title,
            doc_id=doc_id,
            slug=item.get("slug"),
            url=item.get("url"),
            visible=visible,
            children=[],
        )
        ordered_nodes.append(node)
        if node.uuid:
            nodes_by_uuid[node.uuid] = node

    roots: list[TocNode] = []
    for item, node in zip(raw_items, ordered_nodes):
        parent_uuid = item.get("parent_uuid") or ""
        if parent_uuid and parent_uuid in nodes_by_uuid:
            nodes_by_uuid[parent_uuid].children.append(node)
        else:
            roots.append(node)

    return roots
