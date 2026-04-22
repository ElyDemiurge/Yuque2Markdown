from __future__ import annotations

import html
import json
import re
import zlib
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from core_modules.lake.models import MarkdownRenderResult
from core_modules.lake.resource_parser import collect_resources


def render_doc_markdown(
    doc_data: dict,
    *,
    prepend_title: bool = True,
) -> MarkdownRenderResult:
    title = str(doc_data.get("title") or "无标题")
    base_url = doc_data.get("url")
    warnings: list[str] = []

    content, lake_warnings = lake_to_markdown(doc_data)
    warnings.extend(lake_warnings)
    body_lake = str(doc_data.get("body_lake") or "").strip()

    if not content.strip():
        body = str(doc_data.get("body") or "").strip()
        web_content = str(doc_data.get("content") or "").strip()
        if not body_lake and body:
            content = body
            warnings.append("文档未返回 lake 正文，已回退到 body 字段（可能丢失部分格式）")
        elif not body_lake and web_content:
            content = web_content
            warnings.append("文档未返回 lake 正文，已回退到 content 字段（可能丢失部分格式）")
        elif body_lake:
            warnings.append("正文仅含空段落或占位节点，请核对语雀原文以防文档丢失")
        else:
            warnings.append("接口未返回正文，请核对语雀原文以防文档丢失")

    content = maybe_prepend_title(content, title, prepend_title=prepend_title)
    resources = collect_resources(content, "lake", base_url=base_url)
    return MarkdownRenderResult(markdown=f"{content.rstrip()}\n", resources=resources, warnings=warnings)


def convert_doc_to_markdown(doc_data: dict) -> str:
    """便捷包装：直接返回 Markdown 字符串。"""
    return render_doc_markdown(doc_data).markdown


def maybe_prepend_title(content: str, title: str, *, prepend_title: bool) -> str:
    """在内容前添加文档标题（H1），如果内容首行已有匹配的标题则不重复添加。

    注意：lake 内容中的标题已递增一层（原 h1 → h2），所以这里检测 h2 标题。
    """
    normalized = content.strip()
    if not prepend_title:
        return normalized
    lines = [line for line in normalized.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""

    # 检测是否已有 H1 标题匹配文档名（来自其他来源，如 body 字段）
    if first_line.startswith("# ") and first_line[2:].strip() == title.strip():
        return normalized

    # 检测是否已有 H2 标题匹配文档名（来自 lake 原始 H1，已递增为 H2）
    if first_line.startswith("## ") and first_line[3:].strip() == title.strip():
        # 移除重复的 H2 标题，保留后续内容
        remaining = "\n".join(lines[1:]) if len(lines) > 1 else ""
        return f"# {title}\n\n{remaining}" if remaining else f"# {title}"

    # 无匹配标题，正常添加 H1 文档标题
    return f"# {title}\n\n{normalized}" if normalized else f"# {title}"


def lake_to_markdown(doc_data: dict) -> tuple[str, list[str]]:
    """转换语雀 lake 格式文档为 Markdown。"""
    warnings: list[str] = []
    body_lake = str(doc_data.get("body_lake") or "").strip()

    if not body_lake:
        return "", warnings

    board_content, board_warnings = _render_lakeboard_document(body_lake)
    if board_content:
        warnings.extend(board_warnings)
        residual_warnings = _check_lake_conversion_completeness(board_content)
        warnings.extend(residual_warnings)
        return board_content, warnings

    sheet_content, sheet_warnings = _render_lakesheet_document(body_lake)
    if sheet_content:
        warnings.extend(sheet_warnings)
        residual_warnings = _check_lake_conversion_completeness(sheet_content)
        warnings.extend(residual_warnings)
        return sheet_content, warnings

    content, parse_warnings = _render_lake_document(body_lake)
    warnings.extend(parse_warnings)

    residual_warnings = _check_lake_conversion_completeness(content)
    warnings.extend(residual_warnings)
    return content, warnings


def _render_lake_document(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    source = text.replace("\r\n", "\n").replace("\r", "\n")
    source = _strip_invalid_xml_chars(source)
    source = re.sub(r"<!doctype\s+lake>", "", source, flags=re.I)
    source = re.sub(r"<meta\b[^>]*/?>", "", source, flags=re.I)
    source = re.sub(r"<br\s*/?>", "<br />", source, flags=re.I)

    # void HTML 元素转自闭合形式，避免 XML 解析错误
    void_elements = "|".join(["area", "base", "col", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"])
    source = re.sub(rf"<({void_elements})\b([^>]*)(?<!/)>", r"<\1\2/>", source, flags=re.I)

    wrapped = f"<lake-root>{source}</lake-root>"

    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        warnings.append("lake 文档解析失败，请结合 .lake 文件检查")
        return "", warnings

    blocks: list[str] = []
    for child in root:
        rendered = _render_lake_block(child, warnings=warnings)
        if rendered:
            blocks.append(rendered)

    content = "\n\n".join(block.strip() for block in blocks if block.strip())
    content = content.replace("\u200b", "")
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip(), warnings


def _render_lakeboard_document(text: str) -> tuple[str, list[str]]:
    """转换顶层 lakeboard JSON 文档。"""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return "", []
    try:
        payload = json.loads(stripped)
    except Exception:
        return "", []
    if not isinstance(payload, dict):
        return "", []
    if str(payload.get("format") or "").strip().lower() != "lakeboard":
        return "", []
    if str(payload.get("type") or "").strip().lower() != "board":
        return "", []
    content = _render_lake_board(payload)
    warnings: list[str] = []
    if content.strip():
        warnings.append("检测到思维导图（lakeboard），已按 Markdown 列表降级导出")
    return content.strip(), warnings


def _render_lakesheet_document(text: str) -> tuple[str, list[str]]:
    """转换顶层 lakesheet JSON 文档。"""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return "", []
    try:
        payload = json.loads(stripped)
    except Exception:
        return "", []
    if not isinstance(payload, dict):
        return "", []
    if str(payload.get("format") or "").strip().lower() != "lakesheet":
        return "", []
    raw_sheet = payload.get("sheet")
    if not isinstance(raw_sheet, str) or not raw_sheet:
        return "", ["检测到电子表格（lakesheet），但缺少可解析的 sheet 数据"]
    try:
        sheet_bytes = raw_sheet.encode("latin1")
        decoded = zlib.decompress(sheet_bytes).decode("utf-8")
        sheets = json.loads(decoded)
    except Exception:
        return "", ["检测到电子表格（lakesheet），但 sheet 数据解压失败"]
    content = _render_lakesheet_tables(sheets)
    return content.strip(), []


def _render_lake_block(element: ET.Element, *, warnings: list[str], list_indent: int = 0) -> str:
    tag = _lake_tag_name(element)
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        # 标题层级递增：文档标题为 H1，内容中的标题从 H2 开始
        # 原 h1 → h2，原 h2 → h3，以此类推
        original_level = int(tag[1])
        level = original_level + 1
        text = _render_lake_inline(element, warnings=warnings).strip()
        if level > 6:
            # 约定：超出 Markdown H6 能力范围时，不丢弃标题文本，也不继续输出非法标题级别；
            # 保留一条 warning，并将该标题降级为无序列表。这是有意保留的兼容行为。
            warnings.append(f'标题层级超出 H6 最大限制："{text}"（原 h{original_level} → h{level}，已改为无序列表）')
            return f"- {text}" if text else ""
        return f"{'#' * level} {text}" if text else ""

    if tag == "p":
        # 检测是否整个段落都是 <strong> 包裹（连续的 strong 或 code+strong 序列）
        # 这种情况应合并为一个 Markdown 加粗块
        if _is_all_strong_wrapped(element):
            text = _extract_merged_strong_content(element, warnings=warnings).strip()
            return f"**{text}**" if text else ""
        text = _render_lake_inline(element, warnings=warnings).strip()
        return text

    if tag == "blockquote":
        parts: list[str] = []
        for child in element:
            rendered = _render_lake_block(child, warnings=warnings, list_indent=list_indent)
            if rendered:
                parts.extend(line for line in rendered.splitlines() if line.strip())
        if not parts:
            inline = _render_lake_inline(element, warnings=warnings).strip()
            parts = [inline] if inline else []
        return "\n".join(f"> {line}" for line in parts)

    if tag in {"ol", "ul"}:
        return _render_lake_list(element, warnings=warnings, parent_indent=list_indent)

    if tag == "card":
        return _render_lake_card(element, warnings=warnings)

    if tag == "br":
        return ""

    if tag == "a":
        href = element.attrib.get("href") or ""
        text = _render_lake_inline(element, warnings=warnings).strip() or href
        return f"[{text}]({href})" if href else text

    if tag == "span":
        # span 标签直接渲染为行内内容，保留颜色等样式
        return _render_lake_inline(element, warnings=warnings, _wrap_tags=True)

    if tag == "table":
        # 将 HTML 表格转换为 Markdown 表格
        html_content = ET.tostring(element, encoding="unicode") if hasattr(ET, "tostring") else ""
        return _html_table_to_markdown(html_content, warnings=warnings)

    # 表格相关的子标签（tr、td、th、tbody 等）由 table 的递归处理覆盖
    # 静默忽略，不产生警告
    if tag in {"tbody", "thead", "tfoot", "tr", "td", "th", "colgroup", "caption"}:
        parts: list[str] = []
        for child in element:
            rendered = _render_lake_block(child, warnings=warnings, list_indent=list_indent)
            if rendered.strip():
                parts.append(rendered)
        return "\n\n".join(parts)

    if tag == "u":
        # Markdown 不原生支持下划线，保留为 HTML <u> 标签
        text = _render_lake_inline(element, warnings=warnings, _wrap_tags=False).strip()
        return f"<u>{text}</u>" if text else ""


def _render_lake_list(element: ET.Element, *, warnings: list[str], parent_indent: int = 0) -> str:
    ordered = _lake_tag_name(element) == "ol"
    indent_level = parent_indent + int(element.attrib.get("data-lake-indent") or 0)
    start = int(element.attrib.get("start") or 1)
    lines: list[str] = []
    index = start

    for child in element:
        if _lake_tag_name(child) != "li":
            continue
        item_lines = _render_lake_list_item(child, warnings=warnings, indent_level=indent_level)
        if not item_lines:
            continue
        marker = f"{index}." if ordered else "-"
        prefix = "   " * indent_level
        lines.append(f"{prefix}{marker} {item_lines[0]}")
        continuation_prefix = f"{prefix}   "
        for extra in item_lines[1:]:
            lines.append(f"{continuation_prefix}{extra}")
        if ordered:
            index += 1

    return "\n".join(lines)


def _render_lake_list_item(element: ET.Element, *, warnings: list[str], indent_level: int) -> list[str]:
    lines: list[str] = []
    inline_parts: list[str] = []

    if element.text and element.text.strip():
        inline_parts.append(html.unescape(element.text.strip()))

    for child in element:
        tag = _lake_tag_name(child)
        if tag in {"ol", "ul"}:
            if inline_parts:
                line = " ".join(part for part in inline_parts if part).strip()
                if line:
                    lines.append(line)
                inline_parts = []
            nested = _render_lake_list(child, warnings=warnings, parent_indent=indent_level + 1)
            if nested:
                lines.extend(nested.splitlines())
            continue

        if tag in {"p", "blockquote", "card"}:
            rendered = _render_lake_block(child, warnings=warnings, list_indent=indent_level + 1).strip()
            if rendered:
                if inline_parts:
                    line = " ".join(part for part in inline_parts if part).strip()
                    if line:
                        lines.append(line)
                    inline_parts = []
                lines.extend(rendered.splitlines())
        else:
            rendered = _render_lake_inline(child, warnings=warnings)
            if rendered.strip():
                inline_parts.append(rendered.strip())

        if child.tail and child.tail.strip():
            inline_parts.append(html.unescape(child.tail.strip()))

    if inline_parts:
        line = " ".join(part for part in inline_parts if part).strip()
        if line:
            lines.append(line)

    return [line for line in lines if line.strip()]


def _render_lake_inline(element: ET.Element, *, warnings: list[str], _wrap_tags: bool = True) -> str:
    """渲染行内元素及其子元素。

    Args:
        element: 要渲染的 XML 元素
        warnings: 警告列表
        _wrap_tags: 是否在末尾根据元素标签包装输出（内部参数）
    """
    tag = _lake_tag_name(element)

    # <code> 元素特殊处理：内部不应有格式标记，只取纯文本和颜色
    # 直接返回，不递归处理子元素
    if tag == "code":
        code_color = _extract_color_style(element) or _extract_nested_color(element)
        code_text = _get_element_text(element).strip()
        if code_color:
            return f'<span style="color: {code_color}">`{code_text}`</span>' if code_text else ""
        return f"`{code_text}`" if code_text else ""

    parts: list[str] = []

    if element.text:
        parts.append(html.unescape(element.text))

    for child in element:
        child_tag = _lake_tag_name(child)
        if child_tag == "br":
            parts.append("\n")
        elif child_tag == "span":
            # 检查是否有颜色样式，保留为 HTML span 标签
            color = _extract_color_style(child)
            if color:
                inner_text = _get_element_text(child)
                parts.append(f'<span style="color: {color}">{inner_text}</span>')
            else:
                parts.append(_render_lake_inline(child, warnings=warnings, _wrap_tags=True))
        elif child_tag == "a":
            href = child.attrib.get("href") or ""
            text = _render_lake_inline(child, warnings=warnings, _wrap_tags=True).strip() or href
            parts.append(f"[{text}]({href})" if href else text)
        elif child_tag == "card":
            parts.append(_render_lake_card(child, warnings=warnings))
        else:
            # 其他标签递归处理（包括 strong、em、code 等）
            parts.append(_render_lake_inline(child, warnings=warnings, _wrap_tags=True))
        if child.tail:
            parts.append(html.unescape(child.tail))

    text = "".join(parts)
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)

    # 根据当前元素标签包装输出（仅当 _wrap_tags=True 时）
    if _wrap_tags:
        text = text.strip()
        if tag == "strong":
            return f"**{text}**" if text else ""
        if tag in {"em", "i"}:
            return f"*{text}*" if text else ""
        if tag == "u":
            # Markdown 不原生支持下划线，保留为 HTML <u> 标签
            return f"<u>{text}</u>" if text else ""

    return text


def _render_lake_card(element: ET.Element, *, warnings: list[str]) -> str:
    name = str(element.attrib.get("name") or "").strip().lower()
    value = element.attrib.get("value") or ""

    # hr card 不需要 payload，直接渲染
    if name == "hr":
        return "---\n"

    # mention card 直接从属性获取用户名，不需要解码 payload
    if name == "mention":
        user_name = element.attrib.get("data-name") or ""
        if user_name:
            return f"@{user_name}"
        return ""

    # bookmarklink card 从属性获取链接
    if name == "bookmarklink":
        href = element.attrib.get("href") or ""
        title = element.attrib.get("title") or href
        if href:
            return f"[{title}]({href})"
        return ""

    # lockedtext card 是加密内容，静默跳过
    if name == "lockedtext":
        return ""

    payload = _decode_lake_card_value(value, warnings=warnings, name=name)

    if payload is None:
        return ""

    if name == "image":
        src = str(payload.get("src") or "").strip()
        if not src:
            original_type = str(payload.get("originalType") or "").strip().lower()
            link = str(payload.get("link") or "").strip()
            if original_type == "url" and link:
                src = link
        alt = str(payload.get("name") or payload.get("title") or "").strip()
        if not src:
            message = str(payload.get("message") or "").strip()
            suffix = f"（{message}）" if message else ""
            warnings.append(f"Lake image card 缺少 src{suffix}")
            return _render_missing_image_placeholder(payload, alt)
        return f"![{alt}]({src})"

    if name == "codeblock":
        code = str(payload.get("code") or "")
        language = str(payload.get("mode") or "").strip()
        return _render_code_block(language, code)

    if name == "table":
        return _render_lake_table(element, warnings=warnings)

    if name == "video":
        return _render_lake_video(element, warnings=warnings)

    if name == "math":
        return _render_lake_math(payload)

    if name == "bookmarkinline":
        return _render_lake_bookmarkinline(element, payload)

    if name == "board":
        return _render_lake_board(payload)

    if name in {"file", "localdoc"}:
        src = str(payload.get("src") or payload.get("source") or "").strip()
        fname = str(payload.get("name") or payload.get("title") or "").strip()
        link_text = fname or src
        if src:
            return f"[{link_text}]({src})"
        # 只有在有文件名时才输出占位符，否则静默跳过
        if fname:
            return f"[{fname}]"
        return ""

    if name in {"yuque", "yuqueinline"}:
        url = str(payload.get("url") or payload.get("src") or "").strip()
        detail = payload.get("detail", {})
        title = str(detail.get("title") or payload.get("title") or url or "").strip()
        link_text = title or url
        if url:
            return f"[{link_text}]({url})"
        warnings.append(f"Lake {name} card 缺少链接")
        return ""

    warnings.append(f"Lake 转换未支持 card 类型: {name or 'unknown'}")
    return ""


def _render_code_block(language: str, code: str) -> str:
    """渲染代码块，保留原始字符。

    在 Markdown fenced code block（```...```）内部，< > & 等字符
    不需要 HTML 转义，解析器会原样显示代码内容。
    """
    # 只解码已有的 HTML 实体（语雀可能已编码），然后保持原始字符
    unescaped = html.unescape(code)
    return f"```{language}\n{unescaped.rstrip()}\n```"


def _decode_lake_card_value(value: str, *, warnings: list[str], name: str) -> dict | None:
    raw = value.strip()
    if raw.startswith("data:"):
        raw = raw[5:]
    # 跳过空值和 undefined（hr card 常用 data:undefined）
    if not raw or raw == "undefined":
        return None
    try:
        decoded = unquote(raw)
        data = json.loads(decoded)
    except Exception:
        warnings.append(f"Lake card value 无法解码: {name or 'unknown'}")
        return None
    return data if isinstance(data, dict) else None


def _check_lake_conversion_completeness(content: str) -> list[str]:
    warnings: list[str] = []
    # 检查真正的转换遗留：未处理的 card 标签和 data-lake-id 属性
    # 注意：不检查 p/span 等标签的正则匹配，因为这些可能是文章正文中出现的 HTML 标签文本（如"请看上面的 <P> 标签"）
    residual_patterns = [r"<card\b", r"data-lake-id="]
    if not any(re.search(pattern, content, flags=re.I) for pattern in residual_patterns):
        return warnings
    # 排除代码块内的匹配
    safe = re.sub(r"```[\s\S]*?```", "", content)
    if any(re.search(pattern, safe, flags=re.I) for pattern in residual_patterns):
        warnings.append("Lake 转换后仍残留原始标签，请结合 .lake 文件检查")
    return warnings


def _lake_tag_name(element: ET.Element) -> str:
    """从 XML 元素提取标签名（去除命名空间前缀）。"""
    return element.tag.split("}")[-1].lower()


def _get_element_text(element: ET.Element) -> str:
    """获取元素的纯文本内容，忽略所有子标签的格式标记。

    用于 <code> 等不应包含格式标记的元素。
    """
    parts: list[str] = []
    if element.text:
        parts.append(html.unescape(element.text))
    for child in element:
        parts.append(_get_element_text(child))
        if child.tail:
            parts.append(html.unescape(child.tail))
    return "".join(parts)


def _extract_color_style(element: ET.Element) -> str | None:
    """从元素的 style 属性中提取颜色值。

    返回颜色值如 '#E8323C' 或 'rgb(255,0,0)'，无颜色时返回 None。
    """
    style = element.attrib.get("style") or ""
    if not style:
        return None
    # 解析 style 属性，查找 color 定义
    for part in style.split(";"):
        part = part.strip()
        if part.startswith("color:"):
            color = part[6:].strip()
            if color:
                return color
    return None


def _is_all_strong_wrapped(element: ET.Element) -> bool:
    """检查段落是否全部由 <strong> 或 <code><strong> 序列组成。

    这种情况需要合并为一个 Markdown 加粗块，避免输出断开的 `**...**` 序列。
    """
    has_strong = False
    for child in element:
        child_tag = _lake_tag_name(child)
        if child_tag == "strong":
            has_strong = True
            continue
        if child_tag == "code":
            # code 内部是否有 strong
            inner_strong = any(_lake_tag_name(c) == "strong" for c in child)
            if inner_strong:
                has_strong = True
                continue
        # 有非 strong/code 元素，或者纯 code（无内部 strong），则不合并
        return False
    # 段落开头/结尾的纯文本也应该参与判断
    if element.text and element.text.strip():
        return False
    return has_strong


def _extract_merged_strong_content(element: ET.Element, *, warnings: list[str]) -> str:
    """从全部 strong 包裹的段落中提取合并的内容。

    输出格式：`文本 `代码` 文本`（内部代码用行内代码标记，外部整体加粗）
    """
    return _extract_strong_sequence_content(element, warnings=warnings)


def _extract_strong_sequence_content(element: ET.Element, *, warnings: list[str]) -> str:
    """提取 strong/code 序列的内容，保留 code 的反引号标记和 span 的颜色样式。"""
    parts: list[str] = []
    if element.text:
        parts.append(html.unescape(element.text))
    for child in element:
        child_tag = _lake_tag_name(child)
        if child_tag == "strong":
            # strong 内部可能嵌套 code/span，需要递归处理
            parts.append(_extract_strong_sequence_content(child, warnings=warnings))
        elif child_tag == "code":
            # code 内部可能有带颜色的 span（如 <code><strong><span style="color: ...">）
            code_color = _extract_nested_color(child)
            code_text = _get_element_text(child).strip()
            if code_text:
                if code_color:
                    parts.append(f'<span style="color: {code_color}">`{code_text}`</span>')
                else:
                    parts.append(f"`{code_text}`")
        elif child_tag == "span":
            # span 可能有颜色样式
            color = _extract_color_style(child)
            if color:
                inner_text = _get_element_text(child)
                parts.append(f'<span style="color: {color}">{inner_text}</span>')
            else:
                parts.append(_get_element_text(child))
        else:
            # 其他元素取纯文本
            parts.append(_get_element_text(child))
        if child.tail:
            parts.append(html.unescape(child.tail))
    return "".join(parts)


def _extract_nested_color(element: ET.Element) -> str | None:
    """从嵌套元素中提取颜色样式（如 <code><strong><span style="color: ...">）。"""
    # 直接检查当前元素
    color = _extract_color_style(element)
    if color:
        return color
    # 递归检查子元素
    for child in element:
        child_color = _extract_nested_color(child)
        if child_color:
            return child_color
    return None


def _render_lake_table(element: ET.Element, *, warnings: list[str]) -> str:
    """转换 lake table card 为 Markdown 表格。"""
    value = element.attrib.get("value") or ""
    if value.startswith("data:"):
        raw = value[5:]
    else:
        raw = value

    if not raw or raw == "undefined":
        return ""

    try:
        payload = json.loads(unquote(raw))
    except Exception:
        warnings.append("Lake table card 无法解析")
        return ""

    html_content = payload.get("html") or ""
    # JSON 中引号用 \" 转义，替换为普通引号以便 XML 解析
    html_content = html_content.replace('\\"', '"')
    return _html_table_to_markdown(html_content, warnings=warnings)


def _html_table_to_markdown(html: str, *, warnings: list[str]) -> str:
    """将 HTML 表格转换为 Markdown 表格。"""
    # 预处理 HTML：移除 data-lake-id 属性，处理 void 元素
    html = re.sub(r'\s+data-lake-id="[^"]*"', '', html)
    html = re.sub(r'\s+id="[^"]*"', '', html)  # 移除所有 id 属性

    # 处理 void 元素（col 等），确保自闭合
    void_elements = "|".join(["area", "base", "br", "col", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"])
    html = re.sub(rf"<({void_elements})\b([^>]*)(?<!/)>", r"<\1\2/>", html, flags=re.I)

    try:
        # 用 ElementTree 解析 HTML 表格
        tree = ET.fromstring(f"<root>{html}</root>")
    except Exception:
        warnings.append("HTML 表格解析失败")
        return ""

    # 提取所有 tr
    rows: list[list[str]] = []
    for tr in tree.iter():
        if _lake_tag_name(tr) == "tr":
            cells: list[str] = []
            for td in tr:
                tag = _lake_tag_name(td)
                if tag in ("td", "th"):
                    # 提取单元格纯文本
                    text = _get_element_text(td).strip()
                    cells.append(text)
            if cells:
                rows.append(cells)

    if not rows:
        return ""

    # 构建 Markdown 表格
    lines: list[str] = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _render_lake_video(element: ET.Element, *, warnings: list[str]) -> str:
    """转换 lake video card 为 Markdown 链接。"""
    value = element.attrib.get("value") or ""
    if value.startswith("data:"):
        raw = value[5:]
    else:
        raw = value

    if not raw or raw == "undefined":
        return ""

    try:
        payload = json.loads(unquote(raw))
    except Exception:
        warnings.append("Lake video card 无法解析")
        return ""

    url = str(payload.get("url") or payload.get("src") or "").strip()
    title = str(payload.get("title") or payload.get("name") or "视频").strip()
    if url:
        return f"[{title}]({url})"
    return f"[视频]"


def _render_lake_board(payload: dict) -> str:
    """转换 board card，优先输出思维导图文本，再保留整图链接。"""
    outline = _render_board_outline(payload.get("diagramData", {}).get("body", []))
    src = str(payload.get("src") or "").strip()
    parts: list[str] = []
    if outline:
        parts.append(outline)
    if src:
        parts.append(f"![board]({src})")
    return "\n\n".join(part for part in parts if part)


def _render_lake_math(payload: dict) -> str:
    """转换 math card 为 Markdown 公式。"""
    code = str(payload.get("code") or "").strip()
    src = str(payload.get("src") or "").strip()
    if code:
        compact = " ".join(code.split())
        if "\n" in code:
            return f"$$\n{code}\n$$"
        return f"${compact}$"
    if src:
        return f"![公式]({src})"
    return ""


def _render_lake_bookmarkinline(element: ET.Element, payload: dict) -> str:
    """转换 bookmarkinline card 为普通链接。"""
    href = (
        str(payload.get("href") or payload.get("url") or payload.get("src") or "").strip()
        or str(element.attrib.get("href") or "").strip()
    )
    title = (
        str(payload.get("title") or payload.get("name") or "").strip()
        or str(element.attrib.get("title") or "").strip()
    )
    if href:
        return f"[{title or href}]({href})"
    return title


def _strip_invalid_xml_chars(text: str) -> str:
    """移除 XML 1.0 不允许的控制字符。"""
    return "".join(
        ch
        for ch in text
        if ch in "\t\n\r" or ord(ch) >= 0x20
    )


def _render_board_outline(nodes: list[dict], depth: int = 0) -> str:
    """将 board/mindmap 结构降级为 Markdown 列表。"""
    lines: list[str] = []
    for node in nodes:
        text = _normalize_board_text(node.get("html"))
        if text:
            lines.append(f"{'  ' * depth}- {text}")
        children = node.get("children") or []
        if isinstance(children, list) and children:
            child_lines = _render_board_outline(children, depth + 1)
            if child_lines:
                lines.append(child_lines)
    return "\n".join(line for line in lines if line.strip())


def _normalize_board_text(value: object) -> str:
    """清洗 board 节点文本。"""
    text = str(value or "")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)

    def _replace_link(match: re.Match[str]) -> str:
        href = html.unescape((match.group(1) or "").strip())
        label = re.sub(r"<[^>]+>", "", match.group(2) or "")
        label = html.unescape(label).strip()
        if href:
            return f"[{label or href}]({href})"
        return label

    text = re.sub(
        r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        _replace_link,
        text,
        flags=re.I | re.S,
    )
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u200b", "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _render_missing_image_placeholder(payload: dict, alt: str) -> str:
    """为无法恢复的图片卡保留一个可见占位，避免正文内容直接断掉。"""
    name = str(payload.get("name") or "").strip()
    original_type = str(payload.get("originalType") or "").strip().lower()
    error_message = str(payload.get("errorMessage") or "").strip()
    if original_type == "binary":
        return f"（图片缺失：导出 {name or '该图片'} 时缺少 url）"
    if original_type == "url":
        detail = f"，LakeErrorMessage={error_message}" if error_message else ""
        return f"（图片缺失：导出外链图片时缺少 url{detail}）"
    label = alt.strip()
    if label:
        return f"（图片缺失：{label}）"
    return "（图片缺失）"


def _render_lakesheet_tables(sheets: object) -> str:
    """将 lakesheet 数据降级为 Markdown 表格。"""
    if not isinstance(sheets, list):
        return ""
    parts: list[str] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        table = _render_lakesheet_table(sheet)
        if not table:
            continue
        name = str(sheet.get("name") or "").strip()
        if name:
            parts.append(f"## {name}\n\n{table}")
        else:
            parts.append(table)
    return "\n\n".join(parts)


def _render_lakesheet_table(sheet: dict) -> str:
    data = sheet.get("data")
    if not isinstance(data, dict) or not data:
        return ""
    row_keys = sorted((int(k) for k in data.keys() if str(k).isdigit()))
    if not row_keys:
        return ""
    rows: list[list[str]] = []
    max_col = -1
    for row_key in row_keys:
        row_data = data.get(str(row_key), {})
        if not isinstance(row_data, dict):
            continue
        for col_key in row_data.keys():
            if str(col_key).isdigit():
                max_col = max(max_col, int(col_key))
    if max_col < 0:
        return ""

    for row_key in row_keys:
        row_data = data.get(str(row_key), {})
        rendered_row: list[str] = []
        has_content = False
        for col in range(max_col + 1):
            cell = row_data.get(str(col), {}) if isinstance(row_data, dict) else {}
            value = _extract_lakesheet_cell_text(cell)
            rendered_row.append(value)
            if value:
                has_content = True
        if has_content:
            rows.append(rendered_row)
    if not rows:
        return ""

    header = rows[0]
    width = len(header)
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in normalized_rows[1:]:
        lines.append("| " + " | ".join(row[:width]) + " |")
    return "\n".join(lines)


def _extract_lakesheet_cell_text(cell: object) -> str:
    if not isinstance(cell, dict):
        return ""
    value = cell.get("v")
    if value is None:
        value = cell.get("m")
    text = str(value or "").strip()
    text = html.unescape(text)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("|", "\\|")
    return text
