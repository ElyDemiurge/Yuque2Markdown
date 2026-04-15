"""控制台菜单工具测试。"""
import sys
sys.path.insert(0, ".")

from core_modules.console.menu import MenuItem, _first_focusable_index, _move_focus


def test_first_focusable_index_skips_readonly_and_section() -> None:
    items = [
        MenuItem("section", "连接", item_type="section", focusable=False),
        MenuItem("status", "状态", item_type="readonly", focusable=False),
        MenuItem("token", "设置 Token"),
    ]

    assert _first_focusable_index(items, preferred=0) == 2


def test_move_focus_skips_non_focusable_items() -> None:
    items = [
        MenuItem("section", "连接", item_type="section", focusable=False),
        MenuItem("token", "设置 Token"),
        MenuItem("status", "状态", item_type="readonly", focusable=False),
        MenuItem("save", "保存配置"),
    ]

    assert _move_focus(items, 1, 1) == 3
    assert _move_focus(items, 3, -1) == 1
