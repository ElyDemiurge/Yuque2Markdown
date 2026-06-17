# 贡献指南

## 开发环境

```bash
git clone https://github.com/ElyDemiurge/Yuque2Markdown.git
cd Yuque2Markdown
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Windows 激活虚拟环境：

```powershell
.venv\Scripts\activate
```

## 常用命令

```bash
python -m pytest testcases/
python -m pytest testcases/test_markdown_converter.py
python -m pytest --cov=core_modules --cov-report=html testcases/
```

## 代码约定

- Python >= 3.10。
- 使用 4 空格缩进和类型注解。
- 公共函数、类需要简短 docstring；私有函数只在约束不明显时写注释。
- 注释只补充边界、取舍和非显而易见的上下文。
- 不在测试文件里手写 `sys.path.insert(...)`；导入路径由 `testcases/conftest.py` 处理。

## 测试约定

- 测试文件放在 `testcases/`，命名为 `test_*.py`。
- 新功能或 bug 修复要补对应测试。
- Lake 转换问题用最小 `body_lake` 构造样本。
- 导出流程测试使用 `FakeClient` 这类测试替身，不依赖真实网络。
- 跨模块改动直接跑全量测试。

常见补测范围：

- `core_modules/lake/converter.py` -> `testcases/test_markdown_converter.py`
- `core_modules/lake/localizer.py` -> `testcases/test_localizer.py`
- `core_modules/export/exporter.py` -> `testcases/test_export_flow.py`
- `core_modules/config/validator.py` -> `testcases/test_config_validator.py`
- `core_modules/console/` -> `testcases/test_console_app.py testcases/test_console_menu.py testcases/test_repo_handler.py testcases/test_selector.py`

## 提交信息

使用简短、可搜索的提交信息：

```text
feat: 支持附件扩展名过滤
fix: 修复文档树过滤后目录未展开
docs: 精简接口说明
test: 补充 Cookie 附件下载测试
```

常用类型：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`。

## PR 检查

提交前确认：

- 相关测试已通过。
- 文档和示例配置已同步。
- 没有提交 `output/`、日志、Cookie、Token 或本地 IDE 文件。
