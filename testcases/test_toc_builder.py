from core_modules.export.toc_builder import build_toc_tree


def test_build_toc_tree_with_title_and_doc() -> None:
    raw = [
        {"uuid": "dir-1", "type": "TITLE", "title": "父目录"},
        {"uuid": "doc-1", "parent_uuid": "dir-1", "type": "DOC", "title": "子文档", "doc_id": 1, "slug": "child-doc"},
    ]
    tree = build_toc_tree(raw)
    assert len(tree) == 1
    assert tree[0].node_type == "TITLE"
    assert len(tree[0].children) == 1
    assert tree[0].children[0].node_type == "DOC"
    assert tree[0].children[0].doc_id == 1
