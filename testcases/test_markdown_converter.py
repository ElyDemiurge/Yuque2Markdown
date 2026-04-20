"""Lake 转 Markdown 测试。"""
import json
import sys
sys.path.insert(0, ".")

from core_modules.lake.resource_parser import collect_resources, extract_yuque_doc_slug, is_attachment_url, is_image_url, is_yuque_doc_url
from core_modules.lake.converter import convert_doc_to_markdown, render_doc_markdown


def test_lake_basic():
    body_lake = (
        '<h1>章节标题</h1>'
        '<p>第一段正文</p>'
        '<h2>二级标题</h2>'
        '<p>包含<strong>加粗</strong>和<code>行内代码</code></p>'
    )
    result = render_doc_markdown({"title": "文档标题", "format": "lake", "body_lake": body_lake})
    content = result.markdown
    # 文档标题为 H1
    assert "# 文档标题" in content
    # lake h1 → H2，h2 → H3
    assert "## 章节标题" in content
    assert "### 二级标题" in content
    assert "第一段正文" in content
    assert "**加粗**" in content
    assert "`行内代码`" in content


def test_lake_blockquote():
    body_lake = "<blockquote><p>引用内容</p></blockquote>"
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "> 引用内容" in result.markdown


def test_lake_ordered_list():
    body_lake = "<ol><li>第一项</li><li>第二项</li><li>第三项</li></ol>"
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "1. 第一项" in result.markdown
    assert "2. 第二项" in result.markdown
    assert "3. 第三项" in result.markdown


def test_lake_unordered_list():
    body_lake = "<ul><li>苹果</li><li>香蕉</li></ul>"
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "- 苹果" in result.markdown
    assert "- 香蕉" in result.markdown


def test_lake_image_card():
    body_lake = '<card type="inline" name="image" value="data:%7B%22src%22%3A%22https%3A%2F%2Fexample.com%2Fpic.png%22%2C%22name%22%3A%22test.png%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "![test.png](https://example.com/pic.png)" in result.markdown


def test_lake_codeblock_card():
    body_lake = '<card type="inline" name="codeblock" value="data:%7B%22mode%22%3A%22python%22%2C%22code%22%3A%22print(%5C%22hello%5C%22)%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "```python" in result.markdown
    assert 'print("hello")' in result.markdown


def test_lake_link():
    body_lake = '<a href="https://example.com">示例链接</a>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "[示例链接](https://example.com)" in result.markdown


def test_lake_missing_body_lake_warns():
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": ""})
    assert "文档正文为空" in result.warnings[0]


def test_lake_placeholder_only_warns_empty_instead_of_fallback():
    body_lake = '<!doctype lake><meta name="doc-version" content="1" /><p><cursor /><br /></p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake, "content": body_lake})
    assert any("文档正文为空或只包含占位内容" in warning for warning in result.warnings)
    assert not any("已回退到 content 字段" in warning for warning in result.warnings)


def test_lake_unknown_card_warns():
    # audio card 类型尚未支持，应产生警告
    body_lake = '<card type="inline" name="audio" value="data:%7B%22url%22%3A%22https%3A%2F%2Fexample.com%2Faudio.mp3%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert any("未支持 card 类型" in w for w in result.warnings)


def test_lake_title_not_duplicated():
    """lake 内容中的 h1 标题匹配文档名时，应被移除，只保留 H1 文档标题。"""
    body_lake = "<h1>文档标题</h1><p>正文</p>"
    content = convert_doc_to_markdown({"title": "文档标题", "format": "lake", "body_lake": body_lake})
    assert content.count("# 文档标题") == 1
    # 原 h1 变成 h2 后被移除，不应出现 h2
    assert "## 文档标题" not in content


def test_lake_heading_levels_increment():
    """lake 内容中的标题层级应递增：h1→h2，h2→h3，h3→h4，以此类推。"""
    body_lake = "<h1>一级</h1><h2>二级</h2><h3>三级</h3><h4>四级</h4><h5>五级</h5><h6>六级</h6>"
    result = render_doc_markdown({"title": "文档", "format": "lake", "body_lake": body_lake})
    content = result.markdown
    assert "## 一级" in content
    assert "### 二级" in content
    assert "#### 三级" in content
    assert "##### 四级" in content
    assert "###### 五级" in content
    assert "- 六级" in content
    assert any("超出 H6" in w and "六级" in w for w in result.warnings)


def test_lake_document_title_is_h1():
    """文档标题应为唯一的 H1 标题。"""
    body_lake = "<h1>章节</h1><p>正文</p>"
    result = render_doc_markdown({"title": "我的文档", "format": "lake", "body_lake": body_lake})
    content = result.markdown
    # H1 文档标题
    assert content.startswith("# 我的文档")
    # 内容中的标题从 H2 开始
    assert "## 章节" in content
    # 整个文档只有一个 H1
    assert content.count("\n# ") == 0  # 没有其他 H1
    assert content.count("# 我的文档") == 1


def test_lake_collects_resources():
    body_lake = (
        '<card type="inline" name="image" value="data:%7B%22src%22%3A%22https%3A%2F%2Fexample.com%2Fa.png%22%2C%22name%22%3A%22a.png%22%7D"/>'
        '<a href="https://example.com/file.pdf">文件</a>'
    )
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    urls = {resource.normalized_url for resource in result.resources}
    assert "https://example.com/a.png" in urls
    assert "https://example.com/file.pdf" in urls


def test_yuque_doc_url_is_detected():
    url = "https://www.yuque.com/cyberangel/rg9gdm/doc-1"
    assert is_yuque_doc_url(url)
    assert extract_yuque_doc_slug(url) == "doc-1"


def test_lake_codeblock_preserves_angle_brackets():
    """代码块内容中的 < 和 > 应保留原始字符，不做 HTML 转义。

    Markdown fenced code block 会原样显示代码内容。
    """
    body_lake = '<card type="inline" name="codeblock" value="data:%7B%22mode%22%3A%22html%22%2C%22code%22%3A%22%3Chtml%3E%3Cbody%3E%3CP%3EHello%3C%2FP%3E%3CBODY%3E%3C%2FHTML%3E%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown
    assert "```html" in content
    # 应显示原始的 <html><body>... 而不是 HTML 实体编码
    assert "<html>" in content
    assert "<body>" in content
    assert "<P>Hello</P>" in content
    residual = [w for w in result.warnings if "残留" in w]
    assert len(residual) == 0, f"不应该有残留标签警告，但有: {residual}"


def test_lake_codeblock_preserves_html_entities():
    """代码块中的 HTML 实体应被解码为原始字符，不做二次转义。"""
    # 语雀 lake 中代码块内容：mysql&gt;（已编码的 >）
    # 注意：lake JSON 中的 code 字段是 URL 编码的，所以 %26gt%3B 是 &gt; 的 URL 编码
    body_lake = '<card type="inline" name="codeblock" value="data:%7B%22mode%22%3A%22sql%22%2C%22code%22%3A%22mysql%26gt%3B%20select%20count%28%2A%29%20from%20users%3B%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown
    assert "```sql" in content
    # &gt; 应被解码为原始的 >
    assert "mysql>" in content
    # 不应出现 HTML 实体编码
    assert "mysql&gt;" not in content


def test_lake_strong_with_inline_code_merged():
    """段落全部由 strong 包裹时，内部的 code 应合并为一个加粗块。

    语雀 lake 结构：<strong>文本</strong><code><strong>代码</strong></code><strong>文本</strong>
    期望输出：**文本 `代码` 文本**（一个完整的加粗块）
    """
    body_lake = '<p><strong><span>再次计算</span></strong><code><strong><span>floor(rand(0)*2)</span></strong></code><strong><span>，返回0</span></strong></p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown.strip()
    # 应为一个完整的加粗块
    assert content == '# 测试\n\n**再次计算`floor(rand(0)*2)`，返回0**'
    # 不应出现断开的 `**...**` 序列
    assert content.count('**') == 2  # 只有一对 **...**


def test_lake_strong_containing_code():
    """strong 内部直接包含 code 时，应保留 code 的反引号标记。

    语雀 lake 结构：<strong>文本<code>代码</code>文本</strong>
    期望输出：**文本 `代码` 文本**
    """
    body_lake = '<p><strong>加粗<code>代码</code>结尾</strong></p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown.strip()
    assert content == '# 测试\n\n**加粗`代码`结尾**'


def test_lake_color_preserved():
    """带颜色样式的 span 应保留为 HTML 标签。

    语雀 lake 结构：<span style="color: #E8323C">红色文字</span>
    期望输出：<span style="color: #E8323C">红色文字</span>
    """
    body_lake = '<p>普通文本<span style="color: #E8323C">红色文字</span>继续普通</p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown.strip()
    assert '<span style="color: #E8323C">红色文字</span>' in content


def test_lake_color_in_strong_sequence():
    """全部加粗的段落中，带颜色的 span 和 code 都应保留颜色样式。"""
    body_lake = '<p><strong><span style="color: #E8323C">红色加粗</span></strong><code><strong><span style="color: #E8323C">code</span></strong></code><strong><span style="color: #E8323C">结尾</span></strong></p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown.strip()
    # 应为一个完整的加粗块，内部包含颜色 span（包括 code 部分）
    assert content.startswith('# 测试\n\n**')
    assert content.endswith('**')
    assert '<span style="color: #E8323C">红色加粗</span>' in content
    assert '<span style="color: #E8323C">结尾</span>' in content
    # code 部分也应带颜色
    assert '<span style="color: #E8323C">`code`</span>' in content


def test_lake_hr_card():
    """hr card 应该渲染为 ---"""
    body_lake = '<card type="inline" name="hr" value="data:{}"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "---" in result.markdown


def test_lake_hr_card_undefined():
    """hr card value=data:undefined 不应产生警告"""
    body_lake = '<card type="inline" name="hr" value="data:undefined"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "---" in result.markdown
    assert not any("解码失败" in w or "无法解码" in w for w in result.warnings)


def test_lake_u_tag():
    """u 标签应该被保留为 HTML <u> 标签（Markdown 不原生支持下划线）"""
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": "<u>带下划线</u>"})
    assert "<u>带下划线</u>" in result.markdown


def test_lake_u_nested_strong():
    """u 标签嵌套 strong 时，应保留为 <u>**文本**</u> 格式"""
    body_lake = '<p><u><strong>每个</strong></u></p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    content = result.markdown.strip()
    # 下划线保留为 HTML，加粗用 Markdown 格式
    assert "<u>**每个**</u>" in content


def test_lake_file_card():
    """file card 应该渲染为链接"""
    body_lake = '<card type="inline" name="file" value="data:%7B%22src%22%3A%22https%3A%2F%2Fexample.com%2Ffile.pdf%22%2C%22name%22%3A%22file.pdf%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "[file.pdf](https://example.com/file.pdf)" in result.markdown


def test_lake_localdoc_card():
    """localdoc card 应该渲染为链接"""
    body_lake = '<card type="inline" name="localdoc" value="data:%7B%22src%22%3A%22https%3A%2F%2Fexample.com%2Fdoc.pdf%22%2C%22name%22%3A%22doc.pdf%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "[doc.pdf](https://example.com/doc.pdf)" in result.markdown


def test_lake_yuque_card():
    """yuque card 应该渲染为链接到语雀文档"""
    body_lake = '<card type="inline" name="yuque" value="data:%7B%22src%22%3A%22https%3A%2F%2Fwww.yuque.com%2Fcyberangel%2Ftest%22%2C%22url%22%3A%22https%3A%2F%2Fwww.yuque.com%2Fcyberangel%2Ftest%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "https://www.yuque.com/cyberangel/test" in result.markdown


def test_lake_no_residual_warnings_for_code_blocks():
    """代码块中的 HTML 标签不应该触发残留标签警告（代码块内容原样保留）。"""
    body_lake = '<h1>标题</h1><p>正文</p><card type="inline" name="codeblock" value="data:%7B%22mode%22%3A%22html%22%2C%22code%22%3A%22%3Chtml%3E%3Cbody%3E%3CP%3EHello%3C%2FP%3E%3CBODY%3E%3C%2FHTML%3E%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    residual = [w for w in result.warnings if "残留" in w]
    assert len(residual) == 0, f"残留标签警告: {residual}"
    # 代码块中应保留原始 HTML 标签
    assert "<html>" in result.markdown


def test_lake_void_element_col():
    """<col> void 元素不应导致解析错误"""
    body_lake = '<p>正文</p><col width="100"/><p>更多正文</p>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "正文" in result.markdown
    assert not any("解析失败" in w for w in result.warnings)


def test_lake_table_card():
    """table card 应渲染为 Markdown 表格"""
    # HTML 中的 " 使用 JSON 转义（\"），然后整个 JSON 做 URL 编码
    table_html_encoded = '%3Ctable%3E%3Ctbody%3E%3Ctr%3E%3Ctd%3E%3Cp%3E%E7%A7%8D%E7%B1%BB%3C%2Fp%3E%3C%2Ftd%3E%3Ctd%3E%3Cp%3E%E4%B8%BB%E6%89%A9%E5%B1%95%E5%90%8D%3C%2Fp%3E%3C%2Ftd%3E%3C%2Ftr%3E%3Ctr%3E%3Ctd%3E%3Cp%3E%E5%8F%AF%E6%89%A7%E8%A1%8C%E7%A8%8B%E5%BA%8F%3C%2Fp%3E%3C%2Ftd%3E%3Ctd%3E%3Cp%3E.exe%3C%2Fp%3E%3C%2Ftd%3E%3C%2Ftr%3E%3C%2Ftbody%3E%3C%2Ftable%3E'
    card_value = f"data:%7B%22rows%22%3A2%2C%22cols%22%3A2%2C%22html%22%3A%22{table_html_encoded}%22%7D"
    body_lake = f'<card type="inline" name="table" value="{card_value}"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "| 种类 | 主扩展名 |" in result.markdown
    assert "| --- | --- |" in result.markdown
    assert "| 可执行程序 | .exe |" in result.markdown
    assert not any("未支持 card 类型" in w and "table" in w for w in result.warnings)


def test_lake_table_card_complex():
    """table card 含 <colgroup> 和 <tbody> 等复杂结构"""
    # 含 colgroup 的真实格式（HTML 中引号用 JSON 转义 \"，整体 URL 编码）
    table_html_encoded = '%3Ctable%20class%3D%5C%22lake-table%5C%22%20style%3D%5C%22width%3A%20720px%3B%5C%22%3E%3Ccolgroup%3E%3Ccol%20width%3D%5C%22180%5C%22%20span%3D%5C%221%5C%22%20%2F%3E%3Ccol%20width%3D%5C%22180%5C%22%20span%3D%5C%221%5C%22%20%2F%3E%3C%2Fcolgroup%3E%3Ctbody%3E%3Ctr%3E%3Ctd%3E%3Cp%3E%E4%B8%BB%E6%89%A9%E5%B1%95%E5%90%8D%E6%97%A0%E6%B3%95%E8%AF%86%E5%88%AB%E7%9A%84%E7%A8%8B%E5%BA%8F%3C%2Fp%3E%3C%2Ftd%3E%3Ctd%3E%3Cp%3E.com%3C%2Fp%3E%3C%2Ftd%3E%3C%2Ftr%3E%3C%2Ftbody%3E%3C%2Ftable%3E'
    card_value = f"data:%7B%22rows%22%3A2%2C%22cols%22%3A2%2C%22html%22%3A%22{table_html_encoded}%22%7D"
    body_lake = f'<card type="inline" name="table" value="{card_value}"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert ".com" in result.markdown
    assert "主扩展名无法识别的程序" in result.markdown


def test_lake_video_card():
    """video card 应渲染为 Markdown 链接"""
    body_lake = '<card type="inline" name="video" value="data:%7B%22url%22%3A%22https%3A%2F%2Fexample.com%2Fvid.mp4%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "[视频](https://example.com/vid.mp4)" in result.markdown or "https://example.com/vid.mp4" in result.markdown
    assert not any("未支持 card 类型" in w and "video" in w for w in result.warnings)


def test_lake_math_card():
    """math card 应渲染为 Markdown 公式。"""
    body_lake = '<card type="inline" name="math" value="data:%7B%22code%22%3A%22log_%7B2%7Dx%22%2C%22src%22%3A%22https%3A%2F%2Fexample.com%2Fmath.svg%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "$log_{2}x$" in result.markdown
    assert not any("未支持 card 类型" in w and "math" in w for w in result.warnings)


def test_lake_board_card():
    """board card 应至少降级为可读列表，不再产生未支持警告。"""
    body_lake = '<card type="block" name="board" value="data:%7B%22diagramData%22%3A%7B%22body%22%3A%5B%7B%22html%22%3A%22Root%22%2C%22children%22%3A%5B%7B%22html%22%3A%22Child%201%22%2C%22children%22%3A%5B%5D%7D%2C%7B%22html%22%3A%22Child%202%22%2C%22children%22%3A%5B%5D%7D%5D%7D%5D%7D%2C%22src%22%3A%22https%3A%2F%2Fexample.com%2Fboard.jpeg%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "- Root" in result.markdown
    assert "  - Child 1" in result.markdown
    assert "![board](https://example.com/board.jpeg)" in result.markdown
    assert not any("未支持 card 类型" in w and "board" in w for w in result.warnings)


def test_lake_mention_card():
    """mention card 应渲染为 @用户名"""
    body_lake = '<card type="inline" name="mention" data-login="de8ug" data-name="de8ug" value="data:%7B%22login%22%3A%22de8ug%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "@de8ug" in result.markdown
    assert not any("未支持 card 类型" in w for w in result.warnings)


def test_lake_bookmarklink_card():
    """bookmarklink card 应渲染为链接"""
    body_lake = '<card type="inline" name="bookmarklink" href="https://example.com/page" title="Example"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "[Example](https://example.com/page)" in result.markdown
    assert not any("未支持 card 类型" in w for w in result.warnings)


def test_lake_bookmarkinline_card():
    """bookmarkinline card 应渲染为链接"""
    body_lake = '<card type="inline" name="bookmarkinline" value="data:%7B%22url%22%3A%22https%3A%2F%2Fexample.com%2Fpage%22%2C%22title%22%3A%22Inline Example%22%7D"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "[Inline Example](https://example.com/page)" in result.markdown
    assert not any("未支持 card 类型" in w and "bookmarkinline" in w for w in result.warnings)


def test_lake_lockedtext_card():
    """lockedtext card 是加密内容，应静默跳过"""
    body_lake = '<card type="inline" name="lockedtext" value="data:encrypted"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert not any("未支持 card 类型" in w for w in result.warnings)


def test_lake_table_with_data_lake_id():
    """表格 HTML 中带 data-lake-id 属性应正常解析"""
    # HTML 中的引号需要 JSON 转义（\"），然后整体 URL 编码
    table_html_encoded = '%3Ctable%20data-lake-id%3D%5C%22test123%5C%22%3E%3Ctbody%3E%3Ctr%20data-lake-id%3D%5C%22row1%5C%22%3E%3Ctd%3E%3Cp%3E%E5%86%85%E5%AE%B9%3C%2Fp%3E%3C%2Ftd%3E%3C%2Ftr%3E%3C%2Ftbody%3E%3C%2Ftable%3E'
    card_value = f"data:%7B%22rows%22%3A1%2C%22cols%22%3A1%2C%22html%22%3A%22{table_html_encoded}%22%7D"
    body_lake = f'<card type="inline" name="table" value="{card_value}"/>'
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "内容" in result.markdown
    assert not any("HTML 表格解析失败" in w for w in result.warnings)


def test_external_urls_not_downloaded():
    """外部 URL（如 GitHub）不应被当作附件下载"""
    # GitHub .py 文件（raw URL）
    assert not is_attachment_url("https://github.com/devttys0/ida/blob/master/plugins/mipsrop/mipsrop.py")
    # GitHub .zip 文件
    assert not is_attachment_url("https://github.com/ReFirmLabs/binwalk/archive/refs/tags/v2.3.3.zip")
    # 普通外部链接
    assert not is_attachment_url("https://www.example.com/file.pdf")
    # 语雀 CDN URL 应该被识别为附件
    assert is_attachment_url("https://cdn.nlark.com/yuque/0/2022/pdf/574026/xxx.pdf")
    assert is_attachment_url("https://yuque.com/attachments/yuque/0/2022/pdf/xxx.pdf")
    assert is_attachment_url("https://xxx.yuqueusercontent.com/xxx.pdf")
    assert is_attachment_url("https://xxx.aliyuncs.com/xxx.pdf")
    # 验证 collect_resources 对外部 URL 的处理（应归类为 link 而非 attachment）
    markdown = "<p>下载链接：https://github.com/user/repo/archive/v1.0.zip</p>"
    resources = collect_resources(markdown, "lake")
    kinds = {r.kind for r in resources}
    assert "attachment" not in kinds


def test_collect_resources_ignores_urls_in_fenced_code_block():
    markdown = """
```html
<img src="http://127.0.0.1/img/3.jpg">
<a href="https://example.com/file.pdf">link</a>
```
""".strip()
    resources = collect_resources(markdown, "lake")
    assert resources == []


def test_lake_strips_invalid_xml_control_chars():
    """lake 中混入的 XML 非法控制字符不应导致整个文档解析失败。"""
    body_lake = "<p>sym\x02bolic execution</p>"
    result = render_doc_markdown({"title": "测试", "format": "lake", "body_lake": body_lake})
    assert "symbolic execution" in result.markdown
    assert not any("解析失败" in w for w in result.warnings)
