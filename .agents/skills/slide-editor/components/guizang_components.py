"""Guizang PPT Skill 组件封装。

将 guizang-ppt-skill 的核心组件迁移为 slide-editor 可调用格式。
所有组件函数接收 data: dict，返回 {"html": "...", "css": "..."}。
"""

from __future__ import annotations

import html as html_lib
from typing import Any


def esc(value: Any) -> str:
    """转义组件文本，避免数据破坏 HTML 结构。"""
    return html_lib.escape(str(value), quote=True)


def editable_text(value: Any, path: str, tag: str = "span", class_name: str = "") -> str:
    """渲染可双击编辑的文本节点，附带数据路径。"""
    attrs = f' data-field-path="{path}"'
    if class_name:
        attrs += f' class="{class_name}"'
    return f"<{tag}{attrs}>{esc(value)}</{tag}>"


def component_color(data: dict[str, Any], key: str, default: str) -> str:
    """读取组件颜色字段。"""
    value = str(data.get(key, default) or default).strip()
    return value if value.startswith(("#", "rgb", "hsl")) else default


def normalize_items(data: dict[str, Any], limit: int = 8) -> list[dict[str, str]]:
    """把字符串或对象形式的 items 统一为组件可用数据。"""
    raw_items = data.get("items") or data.get("steps") or []
    if not isinstance(raw_items, list):
        raise ValueError("items/steps 必须是数组")
    items: list[dict[str, str]] = []
    for index, item in enumerate(raw_items[:limit], start=1):
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or f"Item {index}"
            body = item.get("body") or item.get("caption") or item.get("text") or ""
        else:
            label = item
            body = ""
        items.append({"label": str(label), "body": str(body)})
    return items


# ============================================================================
# 1. Typography 组件 — 字体分工体系
# ============================================================================

def render_guizang_typography(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格排版组件。
    
    数据字段：
    - text: 文本内容（必填）
    - role: 角色类型 title|body|meta|kicker|lead|quote（默认 body）
    - fontFamily: 可选覆盖字体
    - fontSize: 可选覆盖字号（px）
    - fontWeight: 可选覆盖字重
    - color: 可选覆盖颜色
    """
    role = str(data.get("role", "body") or "body").lower()
    text = esc(data.get("text", ""))
    
    # guizang 字体分工 → px 映射（适配 960x540 画布）
    typography_map = {
        "title": {
            "fontFamily": '"Noto Serif SC", "Playfair Display", serif',
            "fontSize": 42,
            "fontWeight": "700",
            "lineHeight": 1.2,
            "letterSpacing": "0",
        },
        "subtitle": {
            "fontFamily": '"Noto Serif SC", serif',
            "fontSize": 28,
            "fontWeight": "600",
            "lineHeight": 1.3,
        },
        "lead": {
            "fontFamily": '"Noto Serif SC", serif',
            "fontSize": 20,
            "fontWeight": "400",
            "lineHeight": 1.5,
        },
        "body": {
            "fontFamily": '"Noto Sans SC", sans-serif',
            "fontSize": 16,
            "fontWeight": "400",
            "lineHeight": 1.6,
        },
        "meta": {
            "fontFamily": '"JetBrains Mono", "IBM Plex Mono", monospace',
            "fontSize": 12,
            "fontWeight": "500",
            "lineHeight": 1.3,
            "textTransform": "uppercase",
            "letterSpacing": "0.08em",
        },
        "kicker": {
            "fontFamily": '"JetBrains Mono", "IBM Plex Mono", monospace',
            "fontSize": 11,
            "fontWeight": "600",
            "lineHeight": 1.2,
            "textTransform": "uppercase",
            "letterSpacing": "0.1em",
            "color": "#66665f",
        },
        "quote": {
            "fontFamily": '"Noto Serif SC", "Playfair Display", serif',
            "fontSize": 32,
            "fontWeight": "700",
            "lineHeight": 1.3,
            "fontStyle": "italic",
        },
        "big-num": {
            "fontFamily": '"Playfair Display", "Noto Serif SC", serif',
            "fontSize": 72,
            "fontWeight": "800",
            "lineHeight": 0.95,
        },
    }
    
    style = typography_map.get(role, typography_map["body"]).copy()
    
    # 允许覆盖
    if data.get("fontFamily"):
        style["fontFamily"] = data["fontFamily"]
    if data.get("fontSize"):
        style["fontSize"] = data["fontSize"]
    if data.get("fontWeight"):
        style["fontWeight"] = str(data["fontWeight"])
    if data.get("color"):
        style["color"] = data["color"]
    
    style_str = "; ".join(f"{k}: {v}" for k, v in style.items())
    html = f'<div class="gz-typography gz-role-{role}" style="{style_str}">{editable_text(text, "text", "span", "")}</div>'
    
    css = """
.gz-typography {
  box-sizing: border-box;
  color: #0a0a0b;
}
.gz-typography .en {
  font-family: "Playfair Display", serif;
  font-style: italic;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 2. Callout 引用框组件
# ============================================================================

def render_guizang_callout(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格引用框。
    
    数据字段：
    - quote: 引用内容（必填）
    - cite: 引用来源（可选）
    - accent: 强调色（默认 #0a0a0b）
    """
    quote = esc(data.get("quote", ""))
    cite = data.get("cite", "")
    cite_html = editable_text(cite, "cite", "span", "gz-cite") if cite else ""
    
    html = (
        '<div class="gz-callout">'
        f'{editable_text(quote, "quote", "div", "gz-q-big")}'
        f"{cite_html}"
        "</div>"
    )
    
    css = """
.gz-callout {
  box-sizing: border-box;
  height: 100%;
  padding: 28px 32px;
  border-left: 4px solid var(--accent, #0a0a0b);
  background: rgba(0,0,0,0.03);
  font-family: "Noto Serif SC", serif;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
}
.gz-q-big {
  font-size: 22px;
  line-height: 1.45;
  font-weight: 600;
  color: #0a0a0b;
}
.gz-q-big .en {
  font-family: "Playfair Display", serif;
  font-style: italic;
  font-weight: 700;
}
.gz-cite {
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  color: #66665f;
  letter-spacing: 0.05em;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 3. Stat 数字矩阵组件
# ============================================================================

def render_guizang_stat_grid(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格数字矩阵。
    
    数据字段：
    - items: 数据项数组 [{label, value, caption}]
    - columns: 列数（默认 3）
    - accent: 强调色（默认 #C5E803）
    """
    raw_items = data.get("items") or data.get("metrics") or []
    if not isinstance(raw_items, list):
        raise ValueError("items/metrics 必须是数组")
    
    items = []
    for index, item in enumerate(raw_items[:8], start=1):
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or f"Stat {index}"
            value = item.get("value") or item.get("number") or item.get("body") or "0"
            caption = item.get("caption") or item.get("text") or ""
        else:
            label = str(item)
            value = "0"
            caption = ""
        items.append({"label": str(label), "value": str(value), "caption": str(caption)})
    
    if not items:
        items = [
            {"label": "Duration", "value": "64天", "caption": "从 0 到现在"},
            {"label": "Revenue", "value": "1.2M", "caption": "年度营收"},
            {"label": "Growth", "value": "340%", "caption": "同比增长"},
        ]
    
    cols = int(data.get("columns", 3) or 3)
    cols = max(1, min(cols, 4))
    accent = component_color(data, "accent", "#C5E803")
    
    stat_items = []
    for index, item in enumerate(items):
        stat_items.append(
            '<div class="gz-stat">'
            f'{editable_text(item["label"], f"items.{index}.label", "span", "gz-stat-label")}'
            f'{editable_text(item["value"], f"items.{index}.value", "span", "gz-stat-value")}'
            f'{editable_text(item.get("caption", ""), f"items.{index}.caption", "span", "gz-stat-caption")}'
            "</div>"
        )
    
    html = (
        f'<div class="gz-stat-grid" style="--cols:{cols};--accent:{accent};">'
        f'<div class="gz-stat-items">{"".join(stat_items)}</div>'
        "</div>"
    )
    
    css = """
.gz-stat-grid {
  box-sizing: border-box;
  height: 100%;
  color: #0a0a0b;
  font-family: "Noto Sans SC", sans-serif;
}
.gz-stat-items {
  display: grid;
  grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
  gap: 16px;
  height: 100%;
}
.gz-stat {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px 0;
  border-top: 3px solid var(--accent);
}
.gz-stat-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #66665f;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.gz-stat-value {
  font-family: "Playfair Display", "Noto Serif SC", serif;
  font-size: 40px;
  line-height: 1;
  font-weight: 700;
  margin: 8px 0;
}
.gz-stat-caption {
  font-size: 13px;
  line-height: 1.4;
  color: #4b4b45;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 4. Pillar 支柱卡组件
# ============================================================================

def render_guizang_pillar(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格支柱卡。
    
    数据字段：
    - items: 支柱项数组 [{icon, label, description}]
    - columns: 列数（默认 3）
    - accent: 强调色（默认 #C5E803）
    """
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("items 必须是数组")
    
    items = []
    for index, item in enumerate(raw_items[:6], start=1):
        if isinstance(item, dict):
            icon = item.get("icon") or f"{index:02d}"
            label = item.get("label") or item.get("title") or f"Pillar {index}"
            desc = item.get("description") or item.get("body") or ""
        else:
            icon = f"{index:02d}"
            label = str(item)
            desc = ""
        items.append({"icon": str(icon), "label": str(label), "description": str(desc)})
    
    if not items:
        items = [
            {"icon": "01", "label": "判断力", "description": "决策和方向的权威"},
            {"icon": "02", "label": "执行力", "description": "高效交付的能力"},
            {"icon": "03", "label": "复盘力", "description": "持续优化的闭环"},
        ]
    
    cols = int(data.get("columns", 3) or 3)
    cols = max(1, min(cols, 4))
    accent = component_color(data, "accent", "#C5E803")
    
    pillar_items = []
    for index, item in enumerate(items):
        icon_is_number = item["icon"].isdigit()
        icon_html = (
            f'<div class="gz-pillar-num">{esc(item["icon"])}</div>'
            if icon_is_number
            else f'<i data-lucide="{esc(item["icon"])}" class="gz-pillar-icon"></i>'
        )
        pillar_items.append(
            '<div class="gz-pillar">'
            f'{icon_html}'
            f'{editable_text(item["label"], f"items.{index}.label", "div", "gz-pillar-title")}'
            f'{editable_text(item["description"], f"items.{index}.description", "div", "gz-pillar-desc")}'
            "</div>"
        )
    
    html = (
        f'<div class="gz-pillar-grid" style="--cols:{cols};--accent:{accent};">'
        f'<div class="gz-pillar-items">{"".join(pillar_items)}</div>'
        "</div>"
    )
    
    css = """
.gz-pillar-grid {
  box-sizing: border-box;
  height: 100%;
  color: #0a0a0b;
  font-family: "Noto Sans SC", sans-serif;
}
.gz-pillar-items {
  display: grid;
  grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
  gap: 20px;
  height: 100%;
}
.gz-pillar {
  padding: 24px 20px;
  border: 1px solid rgba(10,10,11,0.15);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gz-pillar-num {
  font-family: "Playfair Display", serif;
  font-size: 32px;
  font-weight: 700;
  color: var(--accent, #C5E803);
  line-height: 1;
}
.gz-pillar-icon {
  width: 32px;
  height: 32px;
  color: var(--accent, #C5E803);
}
.gz-pillar-title {
  font-family: "Noto Serif SC", serif;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
}
.gz-pillar-desc {
  font-size: 14px;
  line-height: 1.6;
  color: #4b4b45;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 5. Rowline 表格行组件
# ============================================================================

def render_guizang_rowline(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格表格行列表。
    
    数据字段：
    - items: 行项数组 [{keyword, value, tag}]
    - columns: 列数（默认 3，支持 2 列模式）
    """
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("items 必须是数组")
    
    items = []
    for index, item in enumerate(raw_items[:8], start=1):
        if isinstance(item, dict):
            keyword = item.get("keyword") or item.get("key") or f"Item {index}"
            value = item.get("value") or item.get("body") or ""
            tag = item.get("tag") or item.get("meta") or ""
        else:
            keyword = str(item)
            value = ""
            tag = ""
        items.append({"keyword": str(keyword), "value": str(value), "tag": str(tag)})
    
    if not items:
        items = [
            {"keyword": "CLAUDE.md", "value": "你该怎么做事", "tag": "EMPLOYEE HANDBOOK"},
            {"keyword": "SKILL.md", "value": "行为规则与工作偏好", "tag": "KNOWLEDGE"},
            {"keyword": "RULES.md", "value": "护栏文件", "tag": "GUARDRAILS"},
        ]
    
    cols = int(data.get("columns", 3) or 3)
    cols = max(2, min(cols, 3))
    
    row_items = []
    for index, item in enumerate(items):
        tag_html = editable_text(item["tag"], f"items.{index}.tag", "span", "gz-rowline-tag") if item["tag"] else ""
        row_items.append(
            '<div class="gz-rowline">'
            f'{editable_text(item["keyword"], f"items.{index}.keyword", "span", "gz-rowline-key")}'
            f'{editable_text(item["value"], f"items.{index}.value", "span", "gz-rowline-val")}'
            f"{tag_html}"
            "</div>"
        )
    
    col_template = "1fr 3fr 1fr" if cols == 3 else "1fr 3fr"
    html = (
        f'<div class="gz-rowline-list" style="--cols:{col_template};">'
        f'<div class="gz-rowline-items">{"".join(row_items)}</div>'
        "</div>"
    )
    
    css = """
.gz-rowline-list {
  box-sizing: border-box;
  height: 100%;
  color: #0a0a0b;
  font-family: "Noto Sans SC", sans-serif;
}
.gz-rowline-items {
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100%;
}
.gz-rowline {
  display: grid;
  grid-template-columns: var(--cols);
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(10,10,11,0.12);
  align-items: baseline;
}
.gz-rowline:first-child {
  border-top: 1px solid rgba(10,10,11,0.12);
}
.gz-rowline-key {
  font-family: "Noto Serif SC", serif;
  font-size: 16px;
  font-weight: 600;
}
.gz-rowline-val {
  font-size: 15px;
  line-height: 1.5;
  color: #4b4b45;
}
.gz-rowline-tag {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #66665f;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  text-align: right;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 6. Figure 图片框组件
# ============================================================================

def render_guizang_figure(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格图片框。
    
    数据字段：
    - src: 图片路径（必填）
    - caption: 图片说明（可选）
    - platform: 平台名称（可选）
    - value: 数值标签（可选）
    - aspectRatio: 比例 16:10|4:3|3:2|1:1（默认 16:10）
    """
    src = esc(data.get("src", data.get("image", "")))
    if not src:
        raise ValueError("figure 需要 src 字段")
    
    caption = data.get("caption", "")
    platform = data.get("platform", "")
    value = data.get("value", "")
    
    aspect_ratio_map = {
        "16:10": "16/10",
        "4:3": "4/3",
        "3:2": "3/2",
        "1:1": "1/1",
        "16:9": "16/9",
    }
    ratio = aspect_ratio_map.get(str(data.get("aspectRatio", "16:10")), "16/10")
    
    caption_parts = []
    if platform:
        caption_parts.append(editable_text(platform, "platform", "span", "gz-figure-pf"))
    if value:
        caption_parts.append(editable_text(value, "value", "span", "gz-figure-nb"))
    if caption:
        caption_parts.append(editable_text(caption, "caption", "span", "gz-figure-text"))
    
    caption_html = ""
    if caption_parts:
        caption_html = f'<figcaption class="gz-figure-cap">{"".join(caption_parts)}</figcaption>'
    
    html = (
        f'<figure class="gz-figure">'
        f'<div class="gz-figure-img" style="aspect-ratio:{ratio};">'
        f'<img src="{src}" alt="">'
        f"</div>"
        f"{caption_html}"
        "</figure>"
    )
    
    css = """
.gz-figure {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gz-figure-img {
  flex: 1;
  min-height: 0;
  background: #f3f3ee;
  border: 1px solid #d9d9d2;
  overflow: hidden;
  display: grid;
  place-items: center;
}
.gz-figure-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top center;
  display: block;
}
.gz-figure-img.fit-contain img {
  object-fit: contain;
}
.gz-figure-cap {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 12px;
  line-height: 1.3;
}
.gz-figure-pf {
  font-weight: 600;
  color: #0a0a0b;
}
.gz-figure-nb {
  font-family: "JetBrains Mono", monospace;
  font-weight: 600;
  color: var(--accent, #C5E803);
}
.gz-figure-text {
  color: #66665f;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 7. Platform 平台卡组件
# ============================================================================

def render_guizang_platform(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格平台卡。
    
    数据字段：
    - sub: 平台英文小标题（如 "Weibo"）
    - name: 平台中文名（如 "微博"）
    - value: 数值（如 "289K"）
    - caption: 补充说明（可选）
    - accent: 强调色（默认 #C5E803）
    """
    sub = esc(data.get("sub", "Platform"))
    name = esc(data.get("name", "平台名称"))
    value = esc(data.get("value", "0"))
    caption = data.get("caption", "")
    accent = component_color(data, "accent", "#C5E803")
    
    caption_html = ""
    if caption:
        caption_html = editable_text(caption, "caption", "div", "gz-plat-caption")
    
    html = (
        '<div class="gz-platform-card" style="--accent:{accent};">'
        f'{editable_text(sub, "sub", "div", "gz-plat-sub")}'
        f'{editable_text(name, "name", "div", "gz-plat-name")}'
        f'{editable_text(value, "value", "div", "gz-plat-value")}'
        f"{caption_html}"
        "</div>"
    ).format(accent=accent)
    
    css = """
.gz-platform-card {
  box-sizing: border-box;
  height: 100%;
  padding: 20px 22px;
  border-top: 4px solid var(--accent);
  background: #f3f3ee;
  color: #0a0a0b;
  font-family: "Noto Sans SC", sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.gz-plat-sub {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #66665f;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.gz-plat-name {
  font-family: "Noto Serif SC", serif;
  font-size: 20px;
  font-weight: 600;
  margin: 8px 0;
}
.gz-plat-value {
  font-family: "Playfair Display", "Noto Serif SC", serif;
  font-size: 36px;
  font-weight: 700;
  line-height: 1;
  color: var(--accent, #C5E803);
}
.gz-plat-caption {
  font-size: 12px;
  color: #66665f;
  margin-top: 8px;
  opacity: 0.7;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 8. Ghost 巨型背景字组件
# ============================================================================

def render_guizang_ghost(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格巨型背景装饰字。
    
    数据字段：
    - text: 背景文字（必填）
    - position: 定位位置 top-right|bottom-left|center（默认 top-right）
    - opacity: 透明度 0-1（默认 0.06）
    - fontStyle: italic|normal（默认 italic）
    """
    text = esc(data.get("text", "BUT"))
    position = str(data.get("position", "top-right")).lower()
    opacity = float(data.get("opacity", 0.06) or 0.06)
    font_style = str(data.get("fontStyle", "italic")).lower()
    
    position_map = {
        "top-right": "right:-6vw;top:-8vh;",
        "bottom-left": "left:-8vw;bottom:-18vh;",
        "center": "left:50%;top:50%;transform:translate(-50%,-50%);",
        "top-left": "left:-6vw;top:-8vh;",
        "bottom-right": "right:-6vw;bottom:-18vh;",
    }
    pos_style = position_map.get(position, position_map["top-right"])
    
    html = (
        f'<div class="gz-ghost" '
        f'style="{pos_style}opacity:{opacity};font-style:{font_style};">'
        f'{editable_text(text, "text", "span", "")}'
        "</div>"
    )
    
    css = """
.gz-ghost {
  position: absolute;
  font-family: "Playfair Display", "Noto Serif SC", serif;
  font-size: clamp(120px, 34vw, 320px);
  font-weight: 700;
  color: #0a0a0b;
  line-height: 1;
  pointer-events: none;
  z-index: 0;
  white-space: nowrap;
}
""".strip()
    
    return {"html": html, "css": css}


# ============================================================================
# 组件注册表
# ============================================================================

def render_guizang_pillar_card(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格单体支柱卡片 HTML/CSS 组件。"""
    accent = component_color(data, "accent", "#C5E803")
    icon = esc(data.get("icon", "01"))
    label = esc(data.get("label", "支柱卡片标题"))
    description = esc(data.get("description", data.get("body", "支柱描述细节。")))
    
    icon_is_number = icon.isdigit()
    icon_html = (
        f'<div class="gz-pillar-num">{icon}</div>'
        if icon_is_number
        else f'<i data-lucide="{icon}" class="gz-pillar-icon"></i>'
    )
    
    html = (
        f'<div class="gz-pillar-card" style="--accent:{accent};">'
        f'{icon_html}'
        f'{editable_text(label, "label", "div", "gz-pillar-title")}'
        f'{editable_text(description, "description", "div", "gz-pillar-desc")}'
        "</div>"
    )
    css = """
.gz-pillar-card {
  box-sizing: border-box;
  height: 100%;
  padding: 24px 20px;
  border: 1px solid rgba(10,10,11,0.15);
  background: #fafaf8;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: #0a0a0b;
  font-family: "Noto Sans SC", sans-serif;
}
.gz-pillar-num {
  font-family: "Playfair Display", serif;
  font-size: 32px;
  font-weight: 700;
  color: var(--accent, #C5E803);
  line-height: 1;
}
.gz-pillar-icon {
  width: 32px;
  height: 32px;
  color: var(--accent, #C5E803);
}
.gz-pillar-title {
  font-family: "Noto Serif SC", serif;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
}
.gz-pillar-desc {
  font-size: 14px;
  line-height: 1.6;
  color: #4b4b45;
  flex: 1;
}
""".strip()
    return {"html": html, "css": css}


def render_guizang_stat_card(data: dict[str, Any]) -> dict[str, str]:
    """渲染 guizang 风格单体数据卡片 HTML/CSS 组件。"""
    accent = component_color(data, "accent", "#C5E803")
    label = esc(data.get("label", "Duration"))
    value = esc(data.get("value", "64天"))
    caption = esc(data.get("caption", "从 0 到现在"))
    
    html = (
        f'<div class="gz-stat-card" style="--accent:{accent};">'
        f'<span class="gz-stat-label">{label}</span>'
        f'<span class="gz-stat-value">{value}</span>'
        f'<span class="gz-stat-caption">{caption}</span>'
        "</div>"
    )
    css = """
.gz-stat-card {
  box-sizing: border-box;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px 20px;
  background: #fafaf8;
  border-top: 3px solid var(--accent);
  border-left: 1px solid rgba(10,10,11,0.08);
  border-right: 1px solid rgba(10,10,11,0.08);
  border-bottom: 1px solid rgba(10,10,11,0.08);
  color: #0a0a0b;
  font-family: "Noto Sans SC", sans-serif;
}
.gz-stat-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #66665f;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.gz-stat-value {
  font-family: "Playfair Display", "Noto Serif SC", serif;
  font-size: 40px;
  line-height: 1;
  font-weight: 700;
  margin: 8px 0;
}
.gz-stat-caption {
  font-size: 13px;
  line-height: 1.4;
  color: #4b4b45;
}
""".strip()
    return {"html": html, "css": css}


GUIZANG_COMPONENTS = [
    {
        "name": "guizang-typography",
        "description": "Guizang 风格排版组件，支持 title/body/meta/kicker/quote 等角色。",
        "renderer": render_guizang_typography,
    },
    {
        "name": "guizang-callout",
        "description": "Guizang 风格引用框，适合金句、观点、他人引言。",
        "renderer": render_guizang_callout,
    },
    {
        "name": "guizang-stat-card",
        "description": "Guizang 风格单体数据卡片，支持独立指标名称、数值及描述。",
        "renderer": render_guizang_stat_card,
    },
    {
        "name": "guizang-stat-grid",
        "description": "Guizang 风格数字矩阵，支持 3×2/2×2 网格展示数据。",
        "renderer": render_guizang_stat_grid,
    },
    {
        "name": "guizang-pillar-card",
        "description": "Guizang 风格单体支柱卡片，支持独立图标、标题与描述，可自由排版。",
        "renderer": render_guizang_pillar_card,
    },
    {
        "name": "guizang-pillar",
        "description": "Guizang 风格支柱卡，适合概念并列、三支柱等权页面。",
        "renderer": render_guizang_pillar,
    },
    {
        "name": "guizang-rowline",
        "description": "Guizang 风格表格行列表，适合条目式展示。",
        "renderer": render_guizang_rowline,
    },
    {
        "name": "guizang-figure",
        "description": "Guizang 风格图片框，带 caption 和 standard 比例控制。",
        "renderer": render_guizang_figure,
    },
    {
        "name": "guizang-platform",
        "description": "Guizang 风格平台卡，适合社交平台/渠道展示。",
        "renderer": render_guizang_platform,
    },
    {
        "name": "guizang-ghost",
        "description": "Guizang 风格巨型背景装饰字，杂志感极强。",
        "renderer": render_guizang_ghost,
    },
]
