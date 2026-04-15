# Yuque2Markdown

将语雀知识库导出为本地 Markdown 文件的交互式命令行工具。

当前版本：`v0.2`

## 作者

- Cyberangel：项目作者（纯 Vibe Coding 编程）
- OpenAI Codex、Claude Code：编写代码、协作整理、重构与测试补强

## 功能特性

- 交互式控制台：基于 `curses` 的终端界面，尽量减少命令行参数记忆成本
- 知识库选择：自动列出当前 Token 可访问的知识库，支持搜索过滤
- 文档选择：以目录树方式选择导出范围，按需导出单篇、分支或整个知识库
- 断点续导：支持中断后继续，避免重复请求与重复下载
- Lake 格式转换：将语雀 `body_lake` 转为本地 Markdown
- 资源本地化：默认下载 Markdown 中的图片资源并改写为本地相对路径
- 内部链接处理：尽可能将语雀内部文档链接改写为本地相对路径
- 代理支持：支持通过本地代理访问语雀 API
- 限流处理：识别语雀 `429` 并自动等待后重试

## 附件导出说明

当前项目保留了语雀附件相关代码与配置字段，但**默认不下载语雀附件**。原因如下：

- 语雀官方 API 当前未提供附件导出能力
- 实际抓取附件链接时，常见情况是返回预览页或认证相关页面，而不是可直接保存的原始文件
- 因此当前导出结果是：**图片照常下载到本地，语雀附件保留原始链接**

导出日志中可能会看到：

```text
发现 N 个语雀附件链接，官方 API 暂不支持下载，已保留原始链接
```

这属于当前版本的预期行为。

## 运行要求

- Python >= 3.10
- 仅使用标准库，无需安装第三方依赖
- 需要在支持 UTF-8 和交互式终端的环境中运行

## 语雀会员限制说明

使用前建议先确认语雀账号权限：

- 非语雀会员：未经过测试，暂不确定是否能够申请 Token 以及调用 API。
- 语雀专业会员：可以申请 Token，但每天只有很少的 API 可用额度；超出后语雀 API 会返回 `429`。
- 语雀超级会员：不受上述限制。

## 快速开始

```bash
python yuque2markdown.py
```

程序启动后会进入交互式控制台，按提示完成 Token 配置、知识库选择和导出设置即可。

## 获取语雀 Token

1. 登录语雀。
2. 进入“账户设置” -> “Token 管理”。
3. 创建 Personal Access Token。
4. 在程序的“设置 Token”菜单中输入。

## 常用按键

| 按键 | 功能 |
| --- | --- |
| `↑` / `↓` | 移动选择 |
| `Enter` | 确认、进入子菜单、开始编辑 |
| `Space` | 切换开关项 |
| `s` | 保存配置 |
| `q` / `Esc` | 返回或退出 |

## 项目入口

- `yuque2markdown.py`：程序主入口，负责启动检查并进入交互式控制台
- `core_modules/console/`：终端菜单、状态展示和交互逻辑
- `core_modules/export/`：API 调用、导出编排、日志、断点续导、文件写入
- `core_modules/lake/`：Lake 转 Markdown、资源提取与本地化
- `testcases/`：pytest 测试目录
- `regenerate_md.py`：根据已导出的 `.lake` 文件重新写出 Markdown 文件的维护脚本

## 输出结果

导出结果默认位于 `output/` 目录，通常包含：

- 导出的 Markdown 文件
- 对应的 `.yuque.json` 原始数据
- 对应的 `.lake` 原始 Lake 内容
- `assets/` 资源目录（主要为图片等可直接离线化的资源）
- 导出日志（如 `export.log`）
- 重新写出 Markdown 文件的日志（如 `regenerate.log`）
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

A: 图片失败时，先检查网络和代理设置，再查看 `output/.../export.log`。当前版本会下载 Markdown 中的图片资源，但不会下载语雀附件；语雀附件链接会保留在 Markdown 中。更详细的定位方法见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

**Q: 某篇文档的 Markdown 转换效果不对？**

A: 先看导出日志中的转换警告；如果已经有 `.lake` 文件，只是转换逻辑更新了，可执行 `python regenerate_md.py` 根据 `.lake` 重新写出 Markdown 文件。详见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

**Q: 控制台显示异常或启动失败？**

A: 建议在真实终端中运行，并确保终端支持 UTF-8。程序不支持在非交互式终端中启动 `curses` 界面。

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
