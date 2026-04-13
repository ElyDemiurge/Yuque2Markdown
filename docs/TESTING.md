# 测试说明

## 概览

项目测试统一放在 `testcases/` 目录，使用 `pytest` 作为执行入口。根目录中的 `pytest.ini` 已经约定：

- 测试目录为 `testcases/`
- 测试文件命名为 `test_*.py`
- 测试函数命名为 `test_*`

推荐优先使用 pytest 运行测试，而不是单独执行测试文件中的兼容入口。

## 常用命令

运行全量测试：

```bash
python -m pytest testcases/
```

运行单个测试文件：

```bash
python -m pytest testcases/test_markdown_converter.py
python -m pytest testcases/test_export_flow.py
```

运行单个测试函数：

```bash
python -m pytest testcases/test_markdown_converter.py::test_lake_table_card
```

只看简洁输出：

```bash
python -m pytest
```

## 测试目录覆盖范围

### 配置与配置校验

- `test_config_store.py`
  覆盖配置文件加载、保存和默认值行为。
- `test_config_validator.py`
  覆盖配置字段校验规则，包括路径、代理、知识库输入等边界场景。

### 控制台与菜单

- `test_console_app.py`
  覆盖控制台主流程中的纯函数与状态拼装逻辑。
- `test_console_menu.py`
  覆盖菜单项渲染、确认框和交互相关行为。

### 导出流程与文件处理

- `test_export_flow.py`
  覆盖导出主流程、文档写入、资源本地化和内部链接改写等关键行为。
- `test_checkpoint.py`
  覆盖断点文件创建、保存和恢复。
- `test_file_naming.py`
  覆盖文件名清洗、唯一命名和安全路径拼接。
- `test_logger.py`
  覆盖导出日志写入和格式化行为。
- `test_writer.py`
  覆盖文件写入工具函数。

### Lake 转换与资源本地化

- `test_markdown_converter.py`
  覆盖 `body_lake` 到 Markdown 的主要转换逻辑，是当前最核心的回归测试之一。
- `test_localizer.py`
  覆盖资源下载、本地路径替换、内部文档链接改写等逻辑。

### 目录解析与选择器

- `test_resolver.py`
  覆盖知识库输入解析和仓库定位逻辑。
- `test_selector.py`
  覆盖文档树选择器行为。
- `test_toc_builder.py`
  覆盖语雀 TOC 转本地树结构的构建逻辑。

### 进度展示

- `test_progress.py`
  覆盖进度文本裁剪、宽度计算和进度 UI 的基础行为。

## 建议的回归策略

如果你修改了以下模块，建议至少运行对应测试：

- `core_modules/lake/converter.py`
  运行 `testcases/test_markdown_converter.py`
- `core_modules/lake/localizer.py` 或 `core_modules/lake/resource_parser.py`
  运行 `testcases/test_localizer.py` 和 `testcases/test_export_flow.py`
- `core_modules/export/exporter.py`
  运行 `testcases/test_export_flow.py`、`testcases/test_checkpoint.py`
- `core_modules/config/validator.py`
  运行 `testcases/test_config_validator.py`
- `core_modules/console/`
  运行 `testcases/test_console_app.py`、`testcases/test_console_menu.py`
- `core_modules/export/progress.py`
  运行 `testcases/test_progress.py`

如果改动跨模块，建议直接运行全量测试。

## 新增测试时的约定

1. 新测试文件统一放在 `testcases/` 目录。
2. 文件名使用 `test_*.py`。
3. 函数名使用 `test_*`。
4. 优先写 pytest 风格测试，不新增额外的测试框架依赖。
5. 新增功能或修复 bug 时，优先补回归测试，避免以后重复回归。
6. 如果是 Lake 卡片或 Markdown 转换问题，优先用最小可复现输入构造测试，而不是依赖完整导出样本。
7. 如果是导出流程问题，优先通过 `FakeClient` 之类的受控桩对象构造稳定场景，避免真实网络请求。

## 编写测试的建议

- 尽量测试可观察行为，不要过度绑定内部实现细节。
- 对路径、链接改写、日志文本这类行为，优先断言最终输出。
- 对 Lake 转换问题，优先断言生成 Markdown 中的关键片段和 warning。
- 对配置校验问题，优先断言错误消息和边界输入是否被接受。

## 与维护脚本的关系

`regenerate_md.py` 主要用于在 Lake 转换逻辑更新后，对 `output/` 中已有导出结果批量重新生成 Markdown。它不是测试脚本，但在某些修复场景下可以作为人工验证补充：

1. 先运行对应的转换测试。
2. 再执行 `python regenerate_md.py`。
3. 最后检查 `regenerate.log` 和导出结果是否符合预期。

## 相关文档

- [../README.md](../README.md)：项目总览与常用入口
- [ARCHITECTURE.md](ARCHITECTURE.md)：模块职责与关键数据流
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)：测试失败或导出异常时的排查方法
