# 语雀 Lake 格式解析

## 说明

Lake 是语雀编辑器内部使用的文档格式，存在 API 响应的 `body_lake` 字段里。本工具会解析 `body_lake`，再转成 Markdown。

转换过程：
```
API 响应 → body_lake (XML) → 解析器 → Markdown
                              ↓
                        Markdown + .lake (原始 XML 备份)
```

## 格式结构

### 顶层结构

```xml
<!doctype lake>
<meta name="doc-version" content="1" />
<meta name="viewport" content="adapt" />
<p>正文段落</p>
<h1>标题</h1>
<blockquote><p>引用内容</p></blockquote>
<ol><li>第一项</li><li>第二项</li></ol>
<card type="inline" name="image" value="data:..." />
```

解析前会先做这些预处理：
- 移除 `<!doctype lake>` 声明
- 移除 `<meta ... />` 元信息标签
- 将 `<br>` 统一转为 `<br />`（自闭合）
- 将 void HTML 元素（`area`, `base`, `br`, `col`, `hr`, `img`, `input`, `link`, `meta`, `param`, `source`, `track`, `wbr`）统一转为自闭合形式 `/>`
- 移除 `\x00` 空字符（XML 不允许）
- 用 `<lake-root>` 包裹后使用 `xml.etree.ElementTree` 解析

### 块级标签

| 标签 | 说明 | Markdown 输出 |
|------|------|---------------|
| `h1`~`h6` | 标题 | `#` ~ `######` |
| `p` | 段落 | 普通文本 |
| `blockquote` | 引用 | `> ...` |
| `ol` | 有序列表 | `1. ...` |
| `ul` | 无序列表 | `- ...` |
| `li` | 列表项 | 包含在 `ol`/`ul` 内，支持嵌套 |
| `card` | 富媒体卡片 | 见下节 |
| `br` | 换行 | 忽略 |
| `u` | 下划线文本 | `__text__` |
| `a` | 链接块 | `[text](href)` |

以下标签会递归展开子元素并发出警告（通常为表格类标签）：
`table`, `tbody`, `thead`, `tfoot`, `tr`, `td`, `th`, `colgroup`, `caption`

### 行内标签

| 标签 | 说明 | Markdown 输出 |
|------|------|---------------|
| `span` | 文本容器 | 递归展开 |
| `strong` | 加粗 | `**text**` |
| `em` / `i` | 斜体 | `*text*` |
| `code` | 行内代码 | `` `code` `` |
| `a` | 链接 | `[text](href)` |
| `br` | 换行 | `\n` |
| `u` | 下划线文本 | `__text__` |
| `card` | 行内富媒体 | 递归调用 card 渲染 |

### 常见属性

#### card 通用属性

- `type="inline"`：行内卡片标识
- `name`：卡片类型名，如 `image`、`codeblock`、`hr`、`file`
- `value`：URL 编码 JSON 数据，前缀 `data:`

#### 列表属性

- `data-lake-indent`：缩进层级（整数），用于嵌套列表
- `start`：有序列表起始编号（整数，默认 1）

#### 忽略属性

以下属性在解析时忽略：
- `data-lake-id`：节点唯一标识
- `id`：同 `data-lake-id`
- `list` / `fid`：列表组标识

## Card 格式

Lake 里的图片、代码块这类富文本内容，不是直接放 HTML 标签里，而是写在 `<card>` 节点里，内容是 URL 编码后的 JSON。

### card 结构

```xml
<card type="inline" name="image" value="data:%7B%22src%22%3A%22...%22%7D" />
```

- `name` 决定卡片类型
- `value` 是 `data:` + URL 编码 + JSON 的字符串

### 解码流程

```
value 字符串
  → 去掉 "data:" 前缀（如果存在）
  → urllib.parse.unquote() URL decode
  → json.loads() 解析为字典
```

解码失败时产生警告 `Lake card 解码失败: <type>`，卡片内容替换为空。

### 已支持的 card 类型

#### image

```json
{
  "src": "https://cdn.nlark.com/yuque/xxx.png",
  "name": "截图.png",
  "width": 1162,
  "height": 497,
  "size": 95701
}
```

输出：`![name](src)`

#### codeblock

```json
{
  "mode": "python",
  "code": "print('hello')",
  "lineNumbers": true
}
```

输出：
```markdown
```python
print('hello')
```
```

代码内容中的 `<`、`>`、`&` 会在 fenced code block 中按原样保留，避免破坏代码可读性。

#### hr

`value="data:{}"`（空 JSON）

输出：`---`

#### file

```json
{
  "src": "https://example.com/file.pdf",
  "name": "文档.pdf"
}
```

输出：`[name](src)`

#### localdoc

```json
{
  "src": "https://example.com/doc.pdf",
  "name": "本地文档.pdf"
}
```

输出：`[name](src)`

#### yuque / yuqueinline

```json
{
  "src": "https://www.yuque.com/xxx/yyy",
  "url": "https://www.yuque.com/xxx/yyy",
  "detail": {
    "title": "文档标题"
  }
}
```

输出：`[title](url)` 或 `[url](url)`

### 未支持的 card 类型

以下类型已识别但会产生警告 `Lake 转换未支持 card 类型: <type>`：

- `video`：视频
- `attachment`：附件（不同于 `file`）
- `formula` / `math`：数学公式
- `callout`：提示块
- `taskList`：任务列表
- `mermaid` / `diagram`：图表
- 其他自定义 card

> 注：`table` 已支持基本转换，但复杂结构仍可能因为原始 HTML 结构异常而产生解析警告。

## 转换后检查

解析完成后，工具会检查 Markdown 输出中是否残留以下模式：

- `<card`（未解析的 card 标签）
- `data-lake-id=`（未清理的标识属性）

检查前会先剔除 Markdown 代码块（`` ```...``` ``），避免代码内容中包含的合法 HTML 标签（如 `<P>`, `<BODY>`）触发误报。

若检测到残留，追加警告：`Lake 转换后仍残留原始标签，请结合 .lake 文件检查`

**注意**：`p`、`span`、`blockquote` 等普通标签的正则匹配**不在**检查范围内，因为文档正文中的“请看上面的 `<P>` 标签”这类文字可能会被误判。

## 警告类型汇总

| 场景 | 警告内容 |
|------|----------|
| `body_lake` / `body` / `content` 都为空 | `文档正文为空` |
| `body_lake` 为空但有 `body` | `文档未返回 lake 正文，已回退到 body 字段（可能丢失部分格式）` |
| `body_lake` 为空但有 `content` | `文档未返回 lake 正文，已回退到 content 字段（可能丢失部分格式）` |
| XML 解析失败 | `lake 文档解析失败，请结合 .lake 文件检查` |
| card 解码失败 | `Lake card 解码失败: <type>` |
| card value 解码失败 | `Lake card value 无法解码: <type>` |
| 未知 card 类型 | `Lake 转换未支持 card 类型: <type>` |
| 残留标签检测 | `Lake 转换后仍残留原始标签，请结合 .lake 文件检查` |
| 表格标签 | `Lake 转换遇到未处理的标签: <td/tr/tbody/table>` |
| 通用未处理标签 | `Lake 转换遇到未处理的标签: <xxx>` |
| 通用行内未处理标签 | `Lake 行内转换遇到未处理的标签: <xxx>` |
| yuque card 缺链接 | `Lake yuque card 缺少链接` |
| image card 缺 src | `Lake image card 缺少 src` |

## 导出文件

每篇文档导出时同时生成：

| 文件 | 说明 |
|------|------|
| `<name>.md` | 转换后的 Markdown |
| `<name>.yuque.json` | 语雀 API 原始响应（完整） |
| `<name>.lake` | `body_lake` 原始内容（便于追溯解析问题） |

## 与 HTML 格式的关系

API 响应中还存在 `body`（旧版 Markdown 格式）和 `body_html`（渲染后 HTML）。本工具仅使用 `body_lake` 作为转换来源。当 `body_lake` 完全为空时，工具会尝试回退使用 `body` 字段，并附带警告说明。

## 实现文件

- `core_modules/lake/converter.py`：核心解析逻辑
- `core_modules/lake/resource_parser.py`：资源提取（图片、文件链接）
- `core_modules/lake/localizer.py`：资源下载与链接改写
- `core_modules/lake/models.py`：数据类型定义

## 相关文档

- [../README.md](../README.md)：项目总览与使用入口
- [ARCHITECTURE.md](ARCHITECTURE.md)：模块组成与主要执行顺序
- [TESTING.md](TESTING.md)：测试覆盖与补测建议
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)：转换异常与日志排查
