# Yuque2Markdown

通过语雀 API Token 或浏览器 Cookie 将个人语雀知识库导出为本地 Markdown 的交互式命令行工具。

当前版本：`v0.4`（由于各平台对`curses`支持不同，因此暂时仅支持 macOS）

## 作者

- Cyberangel：项目作者
- OpenAI Codex、Claude Code：编写代码、协作整理、重构与测试补强

## 功能特性

- 交互式控制台：基于 `curses` 的终端界面，尽量减少命令行参数记忆成本
- 知识库选择：自动列出当前登录凭据可访问的知识库，支持搜索过滤
- 文档选择：以目录树方式选择导出范围，按需导出单篇、分支或整个知识库
- 断点恢复：支持中断后继续导出，避免重复请求与重复下载
- Lake 格式转换：将语雀 `body_lake` 转为本地 Markdown
- 资源下载：默认下载 Markdown 中的图片资源，并改写为本地相对路径
- 附件下载：Token 登录时保留附件原始链接；Cookie 登录时可按扩展名下载附件
- 内部链接处理：尽可能将语雀内部文档链接改写为本地相对路径
- 代理支持：支持通过本地代理访问语雀 API
- 限流处理：识别语雀 `429` 并自动等待后重试

## 附件导出说明

语雀官方 OpenAPI 当前未提供附件导出能力，因此附件下载按登录方式区分：

- 使用 Token 登录：不下载语雀附件，附件链接会保留在 Markdown 中。
- 使用浏览器 Cookie 登录：开放附件下载设置，可选择全部附件或指定扩展名。
- 图片资源不受此限制，仍会按“离线资源”设置下载到本地。

导出日志中可能会看到：

```text
发现 N 个语雀附件链接，Token 登录无法下载附件，已保留原始链接；如需下载附件，请改用 Cookie 登录
```

这表示当前使用的是 Token 登录，属于预期行为。

会员权限也会影响 Token 模式是否可用，使用前建议一并确认：

- 非语雀会员：未经过测试，暂不确定是否能够申请 Token 以及调用 API。
- 语雀专业会员：可以申请 Token，但每天只有较少的 API 可用额度；超出后语雀 API 会返回 `429`。
- 语雀超级会员：不受上述限制。

## 适用范围

- 仅支持个人语雀知识库导出。
- 不支持企业版自定义 Cookie key。
- 非当前登录账号的知识库暂不支持导出，如受邀协作知识库。
- 当前版本仅支持 macOS 运行。

## 运行要求

- Python >= 3.10
- 仅支持 macOS
- 需要在支持 UTF-8 和交互式终端的环境中运行

## 快速开始

```bash
python yuque2markdown.py
```

程序启动后会进入交互式控制台，按提示选择登录方式、知识库和导出设置即可。

## 获取语雀 Token

1. 登录语雀。
2. 进入“账户设置” -> “Token 管理”。
3. 创建 Personal Access Token。
4. 在程序的“设置 Token”菜单中输入。

## 从浏览器读取 Cookie

1. 在浏览器中登录语雀。
2. 在控制台中将“登录方式”切换为“浏览器 Cookie”。
3. 使用“从浏览器读取 Cookie”自动获取 Cookie，再刷新连接状态。

对个人语雀知识库来说，实际鉴权主要依赖 `_yuque_session`。程序读取浏览器时会保留整串 Cookie，避免遗漏网页端接口需要的其他字段。

Cookie 登录可用于下载语雀附件。Cookie 属于敏感凭据，请不要泄露。

## 常用按键

| 按键 | 功能 |
| --- | --- |
| `↑` / `↓` | 移动选择 |
| `←` / `→` | 选择行内选项，或在文档树中展开/折叠目录 |
| `Enter` | 确认、进入子菜单、开始编辑 |
| `Space` | 切换开关项 |
| `PgUp` / `PgDn` | 在文档树或导出界面中快速翻页/滚动 |
| `/` | 进入过滤模式 |
| `Esc` | 取消输入或清空过滤 |
| `s` | 保存配置 |
| `q` | 返回或退出 |
| `Ctrl+C` | 在导出过程中触发退出确认 |

## 项目入口

- `yuque2markdown.py`：程序主入口，执行启动检查并进入交互式控制台
- `core_modules/auth/`：登录凭据处理，当前主要用于读取浏览器 Cookie
- `core_modules/console/`：终端菜单、状态展示和交互逻辑
  - `menu_unix.py`：当前版本实际使用的 macOS 菜单实现
  - `menu_windows.py`：Windows 菜单待实现占位，当前版本不会启用
  - `selector.py`：文档树选择器
- `core_modules/export/`：API 调用、导出流程、日志、断点恢复、文件写入
- `core_modules/lake/`：Lake 转 Markdown、资源提取与链接改写
- `testcases/`：pytest 测试目录
- `regenerate_md.py`：根据已导出的 `.lake` 文件重新生成 Markdown 的维护脚本

## 输出结果

导出结果默认位于 `output/` 目录，通常包含：

- 导出的 Markdown 文件
- 对应的 `.yuque.json` 原始数据
- 对应的 `.lake` 原始 Lake 内容
- `assets/` 资源目录（主要保存已下载到本地的图片）
- 导出日志（如 `export.log`）
- 重新生成 Markdown 的日志（如 `regenerate.log`）
- 断点文件（用于中断恢复）

## 测试与维护

常用命令：

```bash
python -m pytest testcases/
python -m pytest testcases/test_markdown_converter.py
python regenerate_md.py
```

如果你主要关注测试、维护脚本或排障，可直接看下面的文档导航。

## 文档导航

除 `README.md` 外，其余文档都在 `docs/` 目录。

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
  面向维护者的架构说明，介绍模块职责、主要执行顺序和输出目录结构。
- [docs/TESTING.md](docs/TESTING.md)
  测试运行方式、`testcases/` 覆盖范围和新增测试约定。
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
  常见问题排查，包括 Token、代理、资源下载、Lake 转换与日志定位。
- [docs/配置文件说明.md](docs/配置文件说明.md)
  配置字段说明、默认值和约束。
- [docs/语雀lake格式解析.md](docs/语雀lake格式解析.md)
  Lake 结构、卡片类型与 Markdown 转换规则。
- [docs/语雀官方接口说明.md](docs/语雀官方接口说明.md)
  语雀 API 参考整理。

## 常见问题

**Q: 提示“触发语雀限流 (429)”？**

A: 语雀 API 存在请求频率限制。程序会自动等待并重试，但如果频繁触发，建议适当增加“请求间隔”设置，例如 `0.1` 秒或更高。

**Q: 图片或附件下载失败？**

A: 图片失败时，先检查网络和代理设置，再查看 `output/.../export.log`。如果使用 Token 登录，语雀附件会保留原始链接；如果需要下载附件，请切换为浏览器 Cookie 登录。更详细的定位方法见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

**Q: 某篇文档的 Markdown 转换效果不对？**

A: 先看导出日志中的转换警告；如果已经有 `.lake` 文件，只是转换逻辑更新了，可执行 `python regenerate_md.py` 根据 `.lake` 重新生成 Markdown。详见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

**Q: 控制台显示异常或启动失败？**

A: 建议在真实终端中运行，并确保终端支持 UTF-8。程序不支持在非交互式终端中启动 `curses` 界面；当前版本仅支持 macOS 运行。

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
