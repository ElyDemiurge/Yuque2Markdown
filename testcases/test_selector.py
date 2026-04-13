from core_modules.export.models import TocNode
from core_modules.selector import (
    _SelectorState,
    _build_footer_line,
    _collect_expandable_keys,
    _flatten_visible,
    _node_key,
    select_doc_ids,
)


def test_selector_helpers_importable() -> None:
    node = TocNode(uuid=None, node_type="DOC", title="A", doc_id=1)
    assert node.doc_id == 1


def test_selector_accepts_initial_selected() -> None:
    defaults = select_doc_ids.__defaults__
    assert defaults is not None
    assert len(defaults) == 2
    assert defaults[0] is None
    assert defaults[1] is None


def test_selector_can_flatten_with_collapsed_directory() -> None:
    child = TocNode(uuid="doc-1", node_type="DOC", title="A", doc_id=1)
    root = TocNode(uuid="dir-1", node_type="TITLE", title="目录", children=[child])
    items = _flatten_visible([root], expanded_keys=set())
    assert len(items) == 1
    assert items[0].node.title == "目录"


def test_selector_filter_keeps_matching_doc() -> None:
    child = TocNode(uuid="doc-1", node_type="DOC", title="Alpha 文档", doc_id=1)
    root = TocNode(uuid="dir-1", node_type="TITLE", title="目录", children=[child])
    items = _flatten_visible([root], expanded_keys={_node_key(root)}, filter_text="alpha")
    assert len(items) == 2
    assert items[1].node.title == "Alpha 文档"


def test_selector_expandable_keys_include_directory() -> None:
    child = TocNode(uuid="doc-1", node_type="DOC", title="A", doc_id=1)
    root = TocNode(uuid="dir-1", node_type="TITLE", title="目录", children=[child])
    keys = _collect_expandable_keys([root])
    assert _node_key(root) in keys


def test_selector_state_can_expand_directory() -> None:
    child = TocNode(uuid="doc-1", node_type="DOC", title="A", doc_id=1)
    root = TocNode(uuid="dir-1", node_type="TITLE", title="目录", children=[child])
    state = _SelectorState(root_nodes=[root], expanded_keys={_node_key(root)}, summary_lines=["知识库: demo"])
    state.items = _flatten_visible(state.root_nodes, state.expanded_keys)
    assert len(state.items) == 2
    assert state.summary_lines == ["知识库: demo"]


def test_selector_footer_line_includes_counts() -> None:
    child = TocNode(uuid="doc-1", node_type="DOC", title="A", doc_id=1)
    root = TocNode(uuid="dir-1", node_type="TITLE", title="目录", children=[child])
    state = _SelectorState(root_nodes=[root], expanded_keys={_node_key(root)}, selected={1}, filter_text="a")
    state.items = _flatten_visible(state.root_nodes, state.expanded_keys, filter_text="a")
    footer = _build_footer_line(state)
    assert "已选 1 篇" in footer
    assert "过滤: a" in footer
