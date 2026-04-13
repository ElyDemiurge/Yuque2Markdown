# 排障说明

## 适用范围

这份文档用于排查以下几类常见问题：

- Token 无效或无法访问语雀 API
- 代理配置错误或网络不可达
- 导出过程中资源下载失败
- Lake 转 Markdown 时出现 warning 或异常
- 导出中断后如何恢复
- 转换逻辑修复后如何批量重生成 Markdown

如果你只是想快速开始使用项目，请先看 [../README.md](../README.md)。如果你在定位测试失败，请同时参考 [TESTING.md](TESTING.md)。

## 先看哪些文件

排查问题时，通常优先查看以下几类文件：

- `output/<知识库>/export.log`
  导出过程的主日志，包含每篇文档的开始、转换、资源下载、完成、warning 和 error。
- `output/<知识库>/regenerate.log`
  批量重转日志。只有在执行 `python regenerate_md.py` 后才会生成或追加。
- `output/<知识库>/_export_checkpoint.json`
  导出断点文件，用于记录已完成、失败和处理中状态。
- 某篇文档目录下的：
  - `文档名.md`
  - `文档名.yuque.json`
  - `文档名.lake`
  - `assets/`

建议排查顺序：

1. 先看 `export.log` 或 `regenerate.log` 中是否有明确 warning / error。
2. 再看具体文档目录下的 `.md`、`.lake` 和 `.yuque.json` 是否一致。
3. 最后再回到代码和测试定位具体模块。

## Token 或连接失败

### 常见表现

- 控制台提示 Token 无效
- 无法读取知识库列表
- API 请求返回未授权或连接失败

### 排查步骤

1. 确认 Token 是否来自语雀“账户设置” -> “Token 管理”。
2. 确认 Token 没有多余空格或换行。
3. 在控制台中重新执行连接测试或刷新 Token 状态。
4. 如果同时配置了代理，优先确认代理是否真的可用。
5. 如果近期更换了 Token，记得保存配置后再重新进入相关菜单。

### 进一步定位

如果错误只在请求阶段出现，而配置本身无误，优先检查：

- 当前网络是否能访问语雀
- 是否有公司代理、本地代理或抓包工具影响 HTTPS 请求
- 是否触发了限流，而不是鉴权失败

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

### 建议

- 如果只是临时网络波动，不建议马上修改代码，先重试导出。
- 如果代理只对部分域名可达，需要同时验证语雀 API 域名与资源 CDN 域名。

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
- 某个普通网页 URL 被错误识别成可下载附件
- 文件名或路径生成逻辑导致写入失败

### 建议

- 如果是单个外部 URL 失败，先确认它是否真的应该下载到本地。
- 如果是批量图片失败，优先检查代理和网络环境。
- 如果日志显示 Markdown 已生成但资源未本地化，可重点看 `localizer.py` 相关逻辑，并运行对应测试。

## Lake 转 Markdown 出现 warning

### 常见表现

`export.log` 中会出现类似 warning：

```text
Lake 转换遇到未专门处理的标签: <tag>
HTML 表格解析失败
未支持 card 类型: xxx
```

### 含义

- `未专门处理的标签`
  通常说明原始 Lake 中出现了转换器没有显式处理的 HTML/Lake 标签。
- `HTML 表格解析失败`
  通常与表格 card 中的 HTML 结构、void 元素、自定义属性或转义内容有关。
- `未支持 card 类型`
  表示该 card 不在当前转换器支持范围内。

### 排查步骤

1. 从日志定位具体文档标题。
2. 打开该文档目录下的 `.lake` 文件，搜索对应标签或 card。
3. 再打开 `.md` 文件，确认最终缺失的是哪一段内容。
4. 如果是回归问题，先运行：

```bash
python -m pytest testcases/test_markdown_converter.py
```

5. 如果是资源或链接改写问题，再补跑：

```bash
python -m pytest testcases/test_localizer.py testcases/test_export_flow.py
```

### 实用建议

- Lake 相关问题优先构造最小复现样例写进测试，而不是直接依赖完整导出样本。
- 如果你已经修复了转换逻辑，可以用 `regenerate_md.py` 对已有导出结果批量重转，而不必重新拉取所有文档。

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

只有在确认断点文件内容异常、且你接受重新导出时，才建议删除它。默认应优先保留，以免丢失已完成状态。

## 什么时候使用 `regenerate_md.py`

适合以下场景：

- 你已经导出了 `.lake` 和 `.yuque.json`
- 只是 Lake 转 Markdown 逻辑修复了
- 不想重新请求语雀 API 和重新下载全部资源

执行方式：

```bash
python regenerate_md.py
```

### 脚本行为

- 遍历 `output/公开知识库` 下的 `.lake` 文件
- 找到同目录下对应的 `.yuque.json`
- 调用 `render_doc_markdown()` 重新生成 Markdown
- 覆盖写回对应 `.md`
- 将过程记录到 `regenerate.log`

### 注意事项

- `regenerate.log` 采用追加写入，旧 warning 可能仍然保留在历史日志里。
- 判断本次是否修复成功时，应重点看最新一轮日志尾部，而不是只统计整个文件中的 warning 次数。

## 如何判断问题属于哪一层

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

### 更像导出编排问题

特征：

- 某些文档没有写出
- 路径层级不对
- 断点恢复异常
- 导出统计和实际文件不一致

优先看：

- `export.log`
- `_export_checkpoint.json`
- `testcases/test_export_flow.py`
- `testcases/test_checkpoint.py`

### 更像 Lake 转换问题

特征：

- Markdown 结构异常
- 表格、代码块、卡片丢失
- warning 集中出现在转换阶段

优先看：

- `.lake`
- `.md`
- `testcases/test_markdown_converter.py`
- [语雀lake格式解析.md](语雀lake格式解析.md)

### 更像资源本地化问题

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

只看本地化与导出链路：

```bash
python -m pytest testcases/test_localizer.py testcases/test_export_flow.py
```

重新生成已有 Markdown：

```bash
python regenerate_md.py
```

## 相关文档

- [../README.md](../README.md)：项目总览与常用入口
- [ARCHITECTURE.md](ARCHITECTURE.md)：模块职责与关键数据流
- [TESTING.md](TESTING.md)：测试运行方式与覆盖范围
- [配置文件说明.md](配置文件说明.md)：配置字段说明
- [语雀lake格式解析.md](语雀lake格式解析.md)：Lake 转换规则
