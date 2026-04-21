"""知识库选择处理测试。"""

from core_modules.config.models import AppConfig, SessionState
from core_modules.console.handlers.repo import handle_repo_input_inline, handle_repo_selection


def test_handle_repo_input_inline_resets_previous_doc_selection() -> None:
    config = AppConfig(token="demo-token")
    session = SessionState(
        connection_ok=True,
        repo_input="old-group/old-book",
        selected_doc_ids={1, 2},
        selected_doc_count=2,
    )

    def fake_build_client_from_config(_config, _token):
        return object()

    def fake_fetch_repo_toc(_client, value):
        from core_modules.export.models import RepoRef, TocNode

        return RepoRef(group_login="new-group", book_slug="new-book", name="新知识库"), [
            TocNode(uuid="1", node_type="DOC", title="A", doc_id=11),
            TocNode(uuid="2", node_type="DOC", title="B", doc_id=12),
        ]

    import core_modules.console.handlers.repo as repo_module

    original = repo_module.fetch_repo_toc
    repo_module.fetch_repo_toc = fake_fetch_repo_toc
    try:
        changed = handle_repo_input_inline(
            config,
            session,
            "new-group/new-book",
            build_client_from_config=fake_build_client_from_config,
            append_console_log=lambda _message: None,
        )
    finally:
        repo_module.fetch_repo_toc = original

    assert changed is True
    assert session.repo_input == "new-group/new-book"
    assert session.selected_doc_ids is None
    assert session.selected_doc_count == 2


def test_handle_repo_input_inline_rejects_shared_repo() -> None:
    config = AppConfig(token="demo-token")
    session = SessionState(connection_ok=True, current_user_login="cyberangel")

    def fake_build_client_from_config(_config, _token):
        return object()

    def fake_fetch_repo_toc(_client, value):
        from core_modules.export.models import RepoRef, TocNode

        return RepoRef(group_login="b1ue", book_slug="shared-book", name="共享知识库"), [
            TocNode(uuid="1", node_type="DOC", title="A", doc_id=11),
        ]

    captured = {}

    def fake_show_message(title, lines):
        captured["title"] = title
        captured["lines"] = lines

    import core_modules.console.handlers.repo as repo_module

    original_fetch = repo_module.fetch_repo_toc
    original_show = repo_module.show_message
    repo_module.fetch_repo_toc = fake_fetch_repo_toc
    repo_module.show_message = fake_show_message
    try:
        changed = handle_repo_input_inline(
            config,
            session,
            "b1ue/shared-book",
            build_client_from_config=fake_build_client_from_config,
            append_console_log=lambda _message: None,
        )
    finally:
        repo_module.fetch_repo_toc = original_fetch
        repo_module.show_message = original_show

    assert changed is False
    assert captured["title"] == "暂不支持导出"


def test_handle_repo_selection_resets_previous_doc_selection_and_refreshes_count() -> None:
    config = AppConfig(token="demo-token")
    session = SessionState(
        connection_ok=True,
        repo_input="old-group/old-book",
        selected_doc_ids={1, 2, 3},
        selected_doc_count=3,
    )
    repos = [{"name": "新知识库", "namespace": "new-group/new-book"}]

    def fake_run_select_list(*_args, **_kwargs):
        return 0, ""

    def fake_build_client_from_config(_config, _token):
        return object()

    def fake_fetch_repo_toc(_client, value):
        from core_modules.export.models import RepoRef, TocNode

        return RepoRef(group_login="new-group", book_slug="new-book", name="新知识库"), [
            TocNode(uuid="1", node_type="DOC", title="A", doc_id=21),
            TocNode(uuid="2", node_type="DOC", title="B", doc_id=22),
            TocNode(uuid="3", node_type="DOC", title="C", doc_id=23),
        ]

    import core_modules.console.handlers.repo as repo_module

    original_select = repo_module.run_select_list
    original_fetch = repo_module.fetch_repo_toc
    repo_module.run_select_list = fake_run_select_list
    repo_module.fetch_repo_toc = fake_fetch_repo_toc
    try:
        changed = handle_repo_selection(
            config,
            session,
            repos,
            "暂无",
            build_client_from_config=fake_build_client_from_config,
            append_console_log=lambda _message: None,
        )
    finally:
        repo_module.run_select_list = original_select
        repo_module.fetch_repo_toc = original_fetch

    assert changed is True
    assert session.repo_input == "new-group/new-book"
    assert session.selected_doc_ids is None
    assert session.selected_doc_count == 3


def test_handle_repo_selection_rejects_shared_repo() -> None:
    config = AppConfig(token="demo-token")
    session = SessionState(connection_ok=True, current_user_login="cyberangel")
    repos = [{"name": "共享知识库", "namespace": "b1ue/shared-book"}]

    captured = {}

    def fake_run_select_list(*args, **kwargs):
        assert kwargs["disabled_indexes"] == {0}
        captured["lines"] = args[1]
        return None, ""

    import core_modules.console.handlers.repo as repo_module

    original_select = repo_module.run_select_list
    repo_module.run_select_list = fake_run_select_list
    try:
        changed = handle_repo_selection(
            config,
            session,
            repos,
            "暂无",
            build_client_from_config=lambda *_args, **_kwargs: object(),
            append_console_log=lambda _message: None,
        )
    finally:
        repo_module.run_select_list = original_select

    assert changed is False
    assert "（非当前登录账号的知识库暂不支持导出，如受邀协作知识库）" in captured["lines"][0]
