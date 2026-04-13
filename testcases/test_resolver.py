from core_modules.export.resolver import resolve_repo_input


def test_resolve_repo_input_from_url() -> None:
    repo = resolve_repo_input("https://www.yuque.com/cyberangel/rg9gdm")
    assert repo.group_login == "cyberangel"
    assert repo.book_slug == "rg9gdm"


def test_resolve_repo_input_from_short_form() -> None:
    repo = resolve_repo_input("cyberangel/rg9gdm")
    assert repo.group_login == "cyberangel"
    assert repo.book_slug == "rg9gdm"
