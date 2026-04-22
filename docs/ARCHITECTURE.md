# Yuque2Markdown 架构文档

## 概览

Yuque2Markdown 是一个将个人语雀知识库导出为本地 Markdown 的交互式终端工具。主线流程是“控制台交互 -> 导出流程 -> Lake 转换 -> 写入文件”：

- 在终端中完成配置、知识库选择和导出控制
- 通过语雀 OpenAPI 或网页端接口拉取知识库、目录和文档详情
- 将 `body_lake` 转为可读的 Markdown
- 下载图片资源并改写为本地链接，同时保留语雀附件原始链接
- 记录日志与断点，支持中断恢复和问题排查

核心流程：

```text
用户操作
  ↓
yuque2markdown.py
  ↓
core_modules.console.app
  ↓
core_modules.export.cli
  ↓
core_modules.export.exporter
  ├─ core_modules.export.client       访问语雀 API
  ├─ core_modules.lake.converter      body_lake -> Markdown
  ├─ core_modules.lake.localizer      资源下载与链接改写
  ├─ core_modules.export.writer       写入 Markdown / JSON / lake / 资源
  └─ core_modules.export.checkpoint   保存导出进度
```

## 根目录入口与辅助文件

- `yuque2markdown.py`
  程序主入口。执行启动前检查，然后进入交互式控制台。
- `regenerate_md.py`
  维护脚本。遍历 `output/` 中已有的 `.lake` 与 `.yuque.json`，重新生成对应 Markdown；本地已有 `assets/` 时优先复用，缺失图片且当前配置里有 Token 时再补充下载。
- `pytest.ini`
  pytest 统一入口配置，约定测试目录为 `testcases/`。
- `output/`
  导出产物目录，包含 Markdown、原始数据、资源、日志与断点文件。

## 模块组成

### `core_modules/config/`

该目录用于配置模型、配置读写和配置校验。

- `models.py`：配置与运行时数据结构
- `store.py`：配置文件读写
- `validator.py`：配置校验规则

### `core_modules/auth/`

该目录用于登录凭据相关处理。

- `browser_cookies.py`：从本机浏览器读取语雀 Cookie，并处理解密

### `core_modules/console/`

该目录用于交互式终端界面和菜单流程。

- `app.py`：主循环与主菜单入口
- `menu.py`：按平台分发菜单实现；当前版本实际使用 `menu_unix.py`
- `menu_unix.py`：macOS 交互式菜单实现
- `menu_windows.py`：Windows 菜单待实现占位，当前版本不会启用
- `selector.py`：文档树选择器
- `controllers/`：导出设置、运行设置、高级设置等子菜单控制器
- `handlers/`：知识库连接、知识库选择、导出执行、配置更新等业务处理
- `state/`：运行状态整理与状态栏展示辅助函数
- `helpers.py`：控制台共享工具函数

子目录分工如下：

- `controllers/` 更偏菜单组织与交互流程
- `handlers/` 更偏业务动作与状态更新
- `state/` 负责将运行时数据整理成可显示文本

当前控制台交互细节：

- 主菜单和子菜单统一使用 `Esc` 返回，当前版本已不再使用 `q` 作为返回键。
- 知识库列表支持输入过滤与 `/` 过滤模式，过滤词支持方向键编辑。
- 文档树过滤为实时刷新；命中目录名时会自动展开目录，命中折叠目录内文档时也会显示路径。
- 导出进度界面支持区块切换和滚动查看；导出结束后可聚焦“返回”按钮退出。

### `core_modules/export/`

该目录用于导出执行、API 调用、断点恢复、日志和文件写入。

- `client.py`：语雀 OpenAPI / 网页端接口客户端
- `cli.py`：导出服务入口，连接控制台层与导出层
- `exporter.py`：导出流程控制器，负责遍历 TOC、拉取文档、转换并写入文件
- `checkpoint.py`：断点保存与恢复
- `file_naming.py`：安全文件名与路径处理
- `logger.py`：导出日志记录
- `progress.py`：导出进度 UI
- `writer.py`：文件写入
- `resolver.py`：知识库输入解析
- `toc_builder.py`：目录树构建
- `models.py`：导出相关数据结构
- `errors.py`：导出错误类型

### `core_modules/lake/`

该目录用于 Lake 解析、资源提取、图片下载和链接改写。

- `converter.py`：Lake -> Markdown
- `resource_parser.py`：从 Markdown 中提取图片、附件、文档链接等资源引用
- `localizer.py`：图片下载、本地路径生成、链接替换，以及语雀附件保留方式
- `models.py`：Lake 转换过程中的数据结构

Lake 格式的详细规则、卡片类型和警告规则见 [语雀lake格式解析.md](语雀lake格式解析.md)。

当前版本里，文档树选择器位于 `core_modules/console/selector.py`。

## 主要执行顺序

### 1. 启动阶段

- `yuque2markdown.py` 执行启动检查
- 非 macOS 平台会在这里直接返回“不支持”
- `config/store.py` 加载配置文件
- `console/app.py` 初始化 `SessionState`
- 控制台主菜单开始接收用户操作

### 2. 连接检查阶段

- 用户触发 Token 刷新或知识库读取
- `console` 层调用 `export/cli.py` 构建客户端
- `export/client.py` 请求语雀 API
- 返回结果写回 `SessionState`
- 状态栏和菜单根据 `SessionState` 更新显示

当前版本里，控制台中的“刷新连接状态”默认走异步刷新，避免在网络请求期间阻塞菜单界面。

### 3. 导出阶段

- 用户选择知识库与文档范围
- `console/handlers/export.py` 组织导出参数
- `export/cli.py` 发起导出执行
- `export/exporter.py` 遍历 TOC、读取文档详情
- `lake/converter.py` 转换 `body_lake`
- `lake/resource_parser.py` 提取资源与链接
- `lake/localizer.py` 下载资源、改写本地路径
- `export/writer.py` 写出 Markdown、原始 JSON、`.lake` 和资源文件
- `checkpoint.py` 在导出过程中记录进度

### 4. 根据 `.lake` 重新生成 Markdown 阶段

- 用户执行 `python regenerate_md.py`
- 脚本遍历 `output/` 中的 `.lake` 和 `.yuque.json`
- 重新调用 `render_doc_markdown()` 生成 Markdown
- 将结果覆盖写回对应 `.md`
- 在 `regenerate.log` 中记录本次重新生成的结果

## 关键状态对象

### `AppConfig`

保存到 `yuque2markdown.config.json` 的配置，主要包含：

- Token
- 默认导出配置
- 代理配置
- UI 偏好设置

更完整字段说明见 [配置文件说明.md](配置文件说明.md)。

当前版本仅支持个人语雀知识库导出，不支持企业版自定义 Cookie key。
非当前登录账号的知识库会在选择界面灰显，且暂不支持导出，如受邀协作知识库。

### `SessionState`

运行时状态，仅在当前会话内生效。重点字段包括：

- `token_status_message`：Token 与连接状态
- `network_test_message`：网络测试状态
- `status_message`：普通提示信息
- `connection_ok`：连接是否成功
- `dirty`：配置是否存在未保存修改

## 输出目录与文件

导出后，`output/` 下通常会按知识库和目录树生成本地层级。单篇文档目录常见文件包括：

- `文档名.md`
- `文档名.yuque.json`
- `文档名.lake`
- `assets/` 资源目录

同时，导出过程还会生成：

- `export.log`：导出过程日志
- `regenerate.log`：重新生成 Markdown 的日志
- checkpoint 文件：用于中断恢复

## 测试结构

项目测试统一放在 `testcases/` 目录，并通过 `pytest.ini` 作为统一入口。当前大致分为：

- 配置与校验：`test_config_store.py`、`test_config_validator.py`
- 控制台与菜单：`test_console_app.py`、`test_console_menu.py`
- 知识库与文档选择：`test_repo_handler.py`、`test_selector.py`
- 导出与文件处理：`test_export_flow.py`、`test_file_naming.py`、`test_logger.py`、`test_writer.py`、`test_checkpoint.py`
- Lake 转换与资源处理：`test_markdown_converter.py`、`test_localizer.py`
- 目录树与选择器：`test_resolver.py`、`test_selector.py`、`test_toc_builder.py`
- 进度展示：`test_progress.py`

详细测试说明见 [TESTING.md](TESTING.md)。

## 设计原则

### 1. 配置与运行时状态分离

- `AppConfig` 管保存到文件的配置
- `SessionState` 管会话状态和界面提示

### 2. 控制台层与导出层分离

- `console/` 处理交互、状态和菜单
- `export/` 处理 API、导出流程和文件写入

### 3. 导出流程可恢复

- 使用 `checkpoint.py` 保存文档级别进度
- 支持中断后继续，减少重复工作

### 4. 安全约束

- `file_naming.py` 对文件名做清洗
- `safe_join()` 防止路径遍历
- `validator.py` 校验配置范围和格式

### 5. 转换与下载分离

- `converter.py` 专注文本转换
- `resource_parser.py` 负责识别资源
- `localizer.py` 负责资源下载与本地路径替换

## 维护时的关注点

1. 新增配置字段时，要同步更新：
   - `config/models.py`
   - `config/store.py`
   - `config/validator.py`
   - 对应测试
2. 新增 Lake card 类型时，要同步更新：
   - `lake/converter.py`
   - 必要的转换测试
   - 如涉及资源，还要更新 `resource_parser.py` 或 `localizer.py`
3. 新增导出状态或进度展示时，要同步更新：
   - `export/progress.py`
   - 对应测试
4. 修改路径生成逻辑时，要优先验证：
   - 路径清洗
   - 相对路径改写
   - 断点恢复与重复导出

## 相关文档

- [../README.md](../README.md)：项目总览与快速开始
- [TESTING.md](TESTING.md)：测试运行与覆盖范围
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)：常见问题与排查方法
- [配置文件说明.md](配置文件说明.md)：配置字段参考
- [语雀lake格式解析.md](语雀lake格式解析.md)：Lake 转换规则
- [语雀官方接口说明.md](语雀官方接口说明.md)：语雀 API 参考
