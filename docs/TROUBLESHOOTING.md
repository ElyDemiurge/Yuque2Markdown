# 排障说明

## 适用范围

这份文档主要覆盖以下排查场景：

- Token 无效、Cookie 无效或无法访问语雀
- 代理配置错误或网络不可达
- 导出过程中资源下载失败
- Lake 转 Markdown 时出现警告或异常
- 导出中断后如何恢复
- 转换逻辑修复后如何批量根据 `.lake` 重新生成 Markdown

想快速开始先看 [../README.md](../README.md)；定位测试失败时再配合 [TESTING.md](TESTING.md)。

## 先看哪些文件

排查时优先看这些文件：

- `output/<知识库>/export.log`
  导出过程的主日志，包含每篇文档的开始、转换、资源下载、完成、警告和错误。
- `output/<知识库>/regenerate.log`
  重新生成 Markdown 的日志。执行 `python regenerate_md.py` 后生成或追加。
  如果本地已有 `assets/`，脚本会优先复用这些图片并改写 Markdown 链接。
- `output/<知识库>/_export_checkpoint.json`
  导出断点文件，用于记录已完成、失败和处理中状态。
- 某篇文档目录下的：
  - `文档名.md`
  - `文档名.yuque.json`
  - `文档名.lake`
  - `assets/`

建议顺序：

1. 先看 `export.log` 或 `regenerate.log` 中是否有明确的警告或错误。
2. 再看具体文档目录下的 `.md`、`.lake` 和 `.yuque.json` 是否一致。
3. 最后再回到代码和测试定位具体模块。

## Token、Cookie 或连接失败

### 常见表现

- 控制台提示 Token 或 Cookie 无效
- 无法读取知识库列表
- API 请求返回未授权或连接失败

### 排查步骤

1. 如果使用 Token 登录，先确认 Token 是否来自语雀“账户设置” -> “Token 管理”。
2. 如果使用 Cookie 登录，先用“从浏览器读取 Cookie”重新获取一次。
3. 确认 Token 或 Cookie 没有被清空。
4. 在控制台中重新执行连接测试或刷新连接状态。
5. 如果同时配置了代理，优先确认代理是否真的可用。

补充说明：

- 当前项目仅支持个人语雀知识库导出。
- 当前版本仅支持 macOS 运行。
- 非当前登录账号的知识库暂不支持导出，如受邀协作知识库。
- 如果某本知识库在列表里是灰色的，说明它不属于当前登录账号，当前版本不能导出。
- 如果知识库列表里可以移动但无法确认，先确认本地版本是否已包含 Enter 兼容修复；当前实现应同时兼容 `getch()` 与 `get_wch()` 的 Enter 返回形式。

### 进一步定位

如果只在请求这一步报错，优先检查：

- 当前网络是否能访问语雀
- 是否有公司代理、本地代理或抓包工具影响 HTTPS 请求
- 是否触发了限流，而不是鉴权失败
- 如果不是在 macOS 上运行，启动时会直接提示当前版本不支持该平台

## 代理配置错误或网络异常

### 常见表现

- 测试代理失败
- 导出卡在连接阶段
- 请求语雀 API 超时
- 资源下载持续失败

### 排查步骤

1. 确认代理地址、端口、用户名密码是否正确。
2. 如果配置了 `test_url`，优先使用 HTTPS 地址。
3. 不确定代理状态时，先暂时关闭代理再测试一次。
4. 如果只有资源下载失败，而文档 API 正常，说明问题可能出在资源域名访问而不是 API 访问。
5. 如果使用 Token 登录，语雀附件不会下载；这是当前版本的预期行为。

### 排查建议

- 临时网络波动时先重试，不必马上改代码。
- 如果代理只对部分域名可达，需要同时验证语雀 API 域名和资源 CDN 域名。

## 导出过程中资源下载失败

### 常见表现

`export.log` 中出现类似信息：

```text
资源下载失败: <url>
```

或者单篇文档显示：

```text
1 个资源下载失败
```

### 排查步骤

1. 先从 `export.log` 中拿到失败的具体 URL。
2. 判断该 URL 是：
   - 图片资源
   - 附件资源
   - 误判为附件的普通网页链接
3. 查看对应 `.md` 中该链接最终是否仍是远程地址。
4. 检查该文档目录的 `assets/` 中是否已生成对应文件。

### 常见原因

- 网络不可达或代理问题
- 远程资源地址失效
- 语雀附件当前没有稳定的官方导出接口支持
- 某个普通网页 URL 被错误识别成可下载附件
- 文件名或路径生成逻辑导致写入失败

### 建议

- 单个外部 URL 失败时，先确认它是否真的需要下载到本地。
- 使用 Token 登录时，语雀附件会保留原始链接；使用 Cookie 登录时可按扩展名下载附件。
- 批量图片失败时，优先检查代理和网络环境。
- 如果 Markdown 已生成但图片链接没有改成本地路径，可重点查看 `localizer.py` 并运行对应测试。

## 知识库或文档过滤异常

### 常见表现

- 从列表选择知识库时，输入过滤词后方向键无法在输入框内移动光标。
- 文档树过滤输入和底部状态行重叠。
- 过滤目录名后，只看到目录本身，看不到目录里的文档。
- 过滤词命中折叠目录内的文档，但界面没有显示出来。

### 当前版本的预期行为

- 知识库列表过滤支持中英文混合输入，`←` / `→` 可在过滤词中移动光标。
- 文档树过滤为实时刷新，不需要按 Enter 才更新结果。
- 命中过滤目录名时，目录会自动展开并显示其子文档。
- 命中过滤折叠目录内的文档时，上层路径会自动展开显示。

### 建议排查步骤

1. 先确认当前版本是否为 `v0.4.2`。
2. 运行：

```bash
python -m pytest testcases/test_console_menu.py testcases/test_repo_handler.py testcases/test_selector.py
```

3. 如果只是终端显示错位，先检查窗口尺寸是否达到程序最低要求。
4. 如果行为与上述预期不一致，再回看 `core_modules/console/menu_unix.py` 和 `core_modules/console/selector.py`。

## Lake 转 Markdown 出现警告

### 常见表现

`export.log` 中会出现类似警告：

```text
Lake 转换遇到未处理的标签: <tag>
HTML 表格解析失败
未支持 card 类型: xxx
```

### 说明

- `未处理的标签`
  通常表示原始 Lake 中出现了转换器尚未支持的 HTML/Lake 标签。
- `HTML 表格解析失败`
  通常与表格 card 中的 HTML 结构、void 元素、自定义属性或转义内容有关。
- `未支持 card 类型`
  表示该 card 不在当前转换器支持范围内。

### 排查步骤

1. 从日志定位具体文档标题。
2. 打开该文档目录下的 `.lake` 文件，搜索对应标签或 card。
3. 再打开 `.md` 文件，确认最终缺失的是哪一段内容。
4. 如果是修复后再次出现的问题，先运行：

```bash
python -m pytest testcases/test_markdown_converter.py
```

5. 如果是资源或链接改写问题，再补跑：

```bash
python -m pytest testcases/test_localizer.py testcases/test_export_flow.py
```

### 建议

- Lake 相关问题优先写最小复现测试，不要直接依赖完整导出样本。
- 如果只修了转换逻辑，可用 `regenerate_md.py` 根据 `.lake` 重新生成 Markdown，不必重新拉取全部文档。

## 导出中断后如何恢复

### 断点文件位置

默认断点文件名为：

```text
_export_checkpoint.json
```

它通常位于知识库导出目录下。

### 文件作用

断点文件会记录：

- 当前知识库信息
- 导出开始时间
- 已完成文档 ID
- 失败文档 ID
- 每篇文档的阶段状态

### 排查步骤

1. 如果导出中断，先检查 `_export_checkpoint.json` 是否存在。
2. 确认其中是否记录了已经完成的文档。
3. 重新进入程序后按原知识库和配置继续导出。
4. 如果断点文件损坏，再考虑删除后重新导出。

### 注意

只有在确认断点文件异常、且接受重新导出时，才建议删除它。默认应优先保留。

## 什么时候使用 `regenerate_md.py` 根据 `.lake` 重新生成 Markdown

适合这些场景：

- 你已经导出了 `.lake` 和 `.yuque.json`
- 只是 Lake 转 Markdown 逻辑修复了
- 不想重新请求语雀 API 和重新下载全部资源

执行方式：

```bash
python regenerate_md.py
```

### 脚本行为

- 遍历 `output/` 下的 `.lake` 文件
- 找到同目录下对应的 `.yuque.json`
- 调用 `render_doc_markdown()` 重新生成 Markdown
- 覆盖写回对应 `.md`
- 将过程记录到 `regenerate.log`

### 注意事项

- `regenerate.log` 采用追加写入，旧警告可能仍会保留。
- 判断本次是否修复成功时，应重点看最新一轮日志尾部。

## 如何判断问题属于哪类模块

### 更像配置或环境问题

特征：

- 启动失败
- Token 校验失败
- 无法读取知识库列表
- 所有文档都下载失败
- 所有资源都无法访问

优先看：

- `../README.md`
- `配置文件说明.md`
- 代理与 Token 配置

### 更像导出流程问题

特征：

- 某些文档没有写出
- 目录层级不对
- 断点恢复异常
- 导出统计和实际文件不一致
- 选择了部分文档，但最终实际导出的数量更少

常见原因：

- 选中的内容里包含非当前登录账号的知识库文档，如受邀协作知识库
- 某些文档已删除，或当前账号对该文档没有导出权限

优先看：

- `export.log`
- `_export_checkpoint.json`
- `testcases/test_export_flow.py`
- `testcases/test_checkpoint.py`

### 更像 Lake 转换问题

特征：

- Markdown 结构异常
- 表格、代码块、卡片丢失
- 警告主要集中在转换阶段

优先看：

- `.lake`
- `.md`
- `testcases/test_markdown_converter.py`
- [语雀lake格式解析.md](语雀lake格式解析.md)

### 更像资源处理问题

特征：

- 图片没有下载
- Markdown 里仍是远程链接
- 内部文档链接未改为相对路径

优先看：

- `assets/`
- `.md`
- `testcases/test_localizer.py`
- `testcases/test_export_flow.py`

## 推荐的最小排查命令

查看全量测试：

```bash
python -m pytest testcases/
```

只看转换相关：

```bash
python -m pytest testcases/test_markdown_converter.py
```

只看资源处理与导出过程：

```bash
python -m pytest testcases/test_localizer.py testcases/test_export_flow.py
```

重新生成已有 Markdown：

```bash
python regenerate_md.py
```

## 相关文档

- [../README.md](../README.md)：项目总览与常用入口
- [ARCHITECTURE.md](ARCHITECTURE.md)：模块职责与主要执行顺序
- [TESTING.md](TESTING.md)：测试运行方式与覆盖范围
- [配置文件说明.md](配置文件说明.md)：配置字段说明
- [语雀lake格式解析.md](语雀lake格式解析.md)：Lake 转换规则
