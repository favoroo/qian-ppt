"""内置 HTML/CSS 组件。

组件函数只负责把结构化 data 渲染成 html/css，不直接访问 API。
"""

from __future__ import annotations

import html as html_lib
import math
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


def normalize_metrics(data: dict[str, Any], limit: int = 6) -> list[dict[str, str]]:
    """把 KPI 数据统一为 label/value/unit/caption。"""
    raw_items = data.get("metrics") or data.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("metrics/items 必须是数组")
    metrics: list[dict[str, str]] = []
    for index, item in enumerate(raw_items[:limit], start=1):
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or f"KPI {index}"
            value = item.get("value") or item.get("number") or item.get("body") or "0"
            unit = item.get("unit") or ""
            caption = item.get("caption") or item.get("body") or item.get("text") or ""
        else:
            label = f"KPI {index}"
            value = item
            unit = ""
            caption = ""
        metrics.append({"label": str(label), "value": str(value), "unit": str(unit), "caption": str(caption)})
    return metrics


def render_metric_card(data: dict[str, Any]) -> dict[str, str]:
    """渲染指标卡 HTML/CSS 组件。"""
    accent = component_color(data, "accent", "#C5E803")
    label = esc(data.get("label", "关键指标"))
    value = esc(data.get("value", "42"))
    unit = esc(data.get("unit", ""))
    caption = esc(data.get("caption", data.get("body", "核心变化一眼读完")))
    html = (
        '<div class="se-metric-card">'
        f'{editable_text(label, "label", "div", "se-metric-label")}'
        '<div class="se-metric-main">'
        f'{editable_text(value, "value", "span", "se-metric-value")}'
        f'{editable_text(unit, "unit", "span", "se-metric-unit")}'
        "</div>"
        f'{editable_text(caption, "caption", "div", "se-metric-caption")}'
        "</div>"
    )
    css = f"""
.se-metric-card {{
  box-sizing: border-box;
  height: 100%;
  padding: 20px 22px;
  border: 1px solid #d9d9d2;
  background: #fafaf8;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}
.se-metric-card::before {{
  content: "";
  width: 42px;
  height: 5px;
  background: {accent};
  display: block;
}}
.se-metric-label {{
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}}
.se-metric-main {{
  display: flex;
  align-items: baseline;
  gap: 8px;
}}
.se-metric-value {{
  font-size: 58px;
  line-height: 0.95;
  font-weight: 250;
}}
.se-metric-unit {{
  font-size: 18px;
  font-weight: 600;
}}
.se-metric-caption {{
  font-size: 14px;
  line-height: 1.45;
  color: #4b4b45;
}}
""".strip()
    return {"html": html, "css": css}


def render_grid_list(data: dict[str, Any]) -> dict[str, str]:
    """渲染网格列表 HTML/CSS 组件。"""
    items = normalize_items(data, limit=8) or [
        {"label": "结构化", "body": "信息按固定网格组织"},
        {"label": "可扫描", "body": "标题、编号和正文层级清晰"},
        {"label": "易扩展", "body": "传入 JSON 即可生成列表"},
    ]
    accent = component_color(data, "accent", "#C5E803")
    cols = int(data.get("columns", 2) or 2)
    cols = max(1, min(cols, 4))
    title = esc(data.get("title", ""))
    title_html = editable_text(title, "title", "div", "se-grid-title") if title else ""
    cards = []
    for index, item in enumerate(items, start=1):
        i = index - 1
        cards.append(
            '<div class="se-grid-item">'
            f'<div class="se-grid-index">{index:02d}</div>'
            f'{editable_text(item["label"], f"items.{i}.label", "div", "se-grid-label")}'
            f'{editable_text(item["body"], f"items.{i}.body", "div", "se-grid-body")}'
            "</div>"
        )
    html = f'<div class="se-grid-list" style="--cols:{cols};--accent:{accent};">{title_html}<div class="se-grid-items">{"".join(cards)}</div></div>'
    css = """
.se-grid-list {
  box-sizing: border-box;
  height: 100%;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.se-grid-title {
  font-size: 20px;
  line-height: 1.2;
  font-weight: 650;
}
.se-grid-items {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
  gap: 12px;
}
.se-grid-item {
  box-sizing: border-box;
  min-width: 0;
  border-top: 5px solid var(--accent);
  background: #f3f3ee;
  padding: 13px 14px 15px;
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 7px;
}
.se-grid-index {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #66665f;
}
.se-grid-label {
  font-size: 17px;
  line-height: 1.25;
  font-weight: 700;
}
.se-grid-body {
  font-size: 13px;
  line-height: 1.45;
  color: #4b4b45;
}
""".strip()
    return {"html": html, "css": css}


def render_circular_flow(data: dict[str, Any]) -> dict[str, str]:
    """渲染循环流程 HTML/CSS 组件。"""
    items = normalize_items(data, limit=6) or [
        {"label": "输入", "body": "收集素材"},
        {"label": "处理", "body": "生成结构"},
        {"label": "验证", "body": "校验版面"},
        {"label": "输出", "body": "导出预览"},
    ]
    accent = component_color(data, "accent", "#C5E803")
    center = esc(data.get("center", data.get("title", "循环")))
    count = len(items)
    nodes = []
    for index, item in enumerate(items):
        angle = -math.pi / 2 + (math.tau * index / count)
        x = 50 + math.cos(angle) * 35
        y = 50 + math.sin(angle) * 32
        nodes.append(
            f'<div class="se-flow-node" style="left:{x:.2f}%;top:{y:.2f}%;">'
            f'<div class="se-flow-num">{index + 1:02d}</div>'
            f'{editable_text(item["label"], f"items.{index}.label", "div", "se-flow-label")}'
            f'{editable_text(item["body"], f"items.{index}.body", "div", "se-flow-body")}'
            "</div>"
        )
    center_html = editable_text(center, "center", "div", "se-flow-center")
    html = f'<div class="se-circular-flow" style="--accent:{accent};"><div class="se-flow-ring"></div>{center_html}{"".join(nodes)}</div>'
    css = """
.se-circular-flow {
  box-sizing: border-box;
  position: relative;
  height: 100%;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
  overflow: hidden;
}
.se-flow-ring {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 48%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border: 2px solid #cfcfc7;
  border-radius: 50%;
}
.se-flow-ring::after {
  content: "";
  position: absolute;
  right: 7%;
  top: 9%;
  width: 16px;
  height: 16px;
  background: var(--accent);
}
.se-flow-center {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 128px;
  height: 128px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: #0a0a0a;
  color: #fafaf8;
  display: grid;
  place-items: center;
  text-align: center;
  font-size: 22px;
  line-height: 1.15;
  font-weight: 650;
  padding: 14px;
}
.se-flow-node {
  position: absolute;
  width: 142px;
  min-height: 74px;
  transform: translate(-50%, -50%);
  background: #fafaf8;
  border: 1px solid #d9d9d2;
  box-sizing: border-box;
  padding: 10px 12px;
}
.se-flow-num {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #66665f;
}
.se-flow-label {
  margin-top: 4px;
  font-size: 15px;
  line-height: 1.2;
  font-weight: 700;
}
.se-flow-body {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.35;
  color: #4b4b45;
}
""".strip()
    return {"html": html, "css": css}


def render_compare_columns(data: dict[str, Any]) -> dict[str, str]:
    """渲染双栏对比 HTML/CSS 组件。"""
    accent = component_color(data, "accent", "#C5E803")
    left = data.get("left") if isinstance(data.get("left"), dict) else {}
    right = data.get("right") if isinstance(data.get("right"), dict) else {}
    if not left and not right:
        items = normalize_items(data, limit=2)
        left = items[0] if len(items) > 0 else {"label": "Before", "body": "旧方式的主要限制"}
        right = items[1] if len(items) > 1 else {"label": "After", "body": "新方式的关键改进"}
    title = esc(data.get("title", ""))
    title_html = editable_text(title, "title", "div", "se-compare-title") if title else ""
    html = f"""
<div class="se-compare" style="--accent:{accent};">
  {title_html}
  <div class="se-compare-grid">
    <section class="se-compare-col">
      {editable_text(left.get("kicker", "A"), "left.kicker", "div", "se-compare-kicker")}
      {editable_text(left.get("label", left.get("title", "Before")), "left.label", "h3", "")}
      {editable_text(left.get("body", left.get("caption", "")), "left.body", "p", "")}
    </section>
    <section class="se-compare-col se-compare-col-accent">
      {editable_text(right.get("kicker", "B"), "right.kicker", "div", "se-compare-kicker")}
      {editable_text(right.get("label", right.get("title", "After")), "right.label", "h3", "")}
      {editable_text(right.get("body", right.get("caption", "")), "right.body", "p", "")}
    </section>
  </div>
</div>
""".strip()
    css = """
.se-compare {
  box-sizing: border-box;
  height: 100%;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.se-compare-title {
  font-size: 22px;
  line-height: 1.18;
  font-weight: 650;
}
.se-compare-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 0;
}
.se-compare-col {
  min-width: 0;
  border-top: 6px solid #0a0a0a;
  background: #f3f3ee;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.se-compare-col-accent {
  border-top-color: var(--accent);
  background: #0a0a0a;
  color: #fafaf8;
}
.se-compare-kicker {
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: #66665f;
}
.se-compare-col-accent .se-compare-kicker {
  color: var(--accent);
}
.se-compare h3 {
  margin: 18px 0 10px;
  font-size: 26px;
  line-height: 1.12;
  font-weight: 300;
}
.se-compare p {
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
  color: #4b4b45;
}
.se-compare-col-accent p {
  color: #d9d9d2;
}
""".strip()
    return {"html": html, "css": css}


def render_kpi_strip(data: dict[str, Any]) -> dict[str, str]:
    """渲染横向 KPI 指标组 HTML/CSS 组件。"""
    metrics = normalize_metrics(data, limit=5) or [
        {"label": "效率", "value": "3.2", "unit": "x", "caption": "端到端提速"},
        {"label": "成本", "value": "-28", "unit": "%", "caption": "单次交付下降"},
        {"label": "质量", "value": "96", "unit": "%", "caption": "校验通过率"},
    ]
    accent = component_color(data, "accent", "#C5E803")
    cards = []
    for index, metric in enumerate(metrics):
        cards.append(
            '<div class="se-kpi-item">'
            f'{editable_text(metric["label"], f"metrics.{index}.label", "div", "se-kpi-label")}'
            '<div class="se-kpi-main">'
            f'{editable_text(metric["value"], f"metrics.{index}.value", "span", "se-kpi-value")}'
            f'{editable_text(metric["unit"], f"metrics.{index}.unit", "span", "se-kpi-unit")}'
            '</div>'
            f'{editable_text(metric["caption"], f"metrics.{index}.caption", "div", "se-kpi-caption")}'
            '</div>'
        )
    html = f'<div class="se-kpi-strip" style="--accent:{accent};">{"".join(cards)}</div>'
    css = """
.se-kpi-strip {
  box-sizing: border-box;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
  gap: 12px;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
}
.se-kpi-item {
  min-width: 0;
  border-top: 5px solid var(--accent);
  background: #f3f3ee;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.se-kpi-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: #66665f;
}
.se-kpi-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.se-kpi-value {
  font-size: 42px;
  line-height: .95;
  font-weight: 250;
}
.se-kpi-unit {
  font-size: 15px;
  font-weight: 650;
}
.se-kpi-caption {
  font-size: 12px;
  line-height: 1.35;
  color: #4b4b45;
}
""".strip()
    return {"html": html, "css": css}


def render_screenshot_frame(data: dict[str, Any]) -> dict[str, str]:
    """渲染截图包装 HTML/CSS 组件。"""
    src = esc(data.get("src", data.get("image", "")))
    if not src:
        raise ValueError("screenshot-frame 需要 src 字段，通常是 upload 返回的 /static/uploads/... 路径")
    accent = component_color(data, "accent", "#C5E803")
    title = esc(data.get("title", data.get("label", "Preview")))
    caption = esc(data.get("caption", ""))
    caption_html = editable_text(caption, "caption", "div", "se-shot-caption") if caption else ""
    html = f"""
<figure class="se-shot" style="--accent:{accent};">
  <div class="se-shot-bar">
    <span></span><span></span><span></span>
    {editable_text(title, "title", "strong", "")}
  </div>
  <div class="se-shot-body"><img src="{src}" alt="{title}"></div>
  {caption_html}
</figure>
""".strip()
    css = """
.se-shot {
  box-sizing: border-box;
  height: 100%;
  margin: 0;
  padding: 18px;
  background:
    linear-gradient(135deg, rgba(197,232,3,.18), transparent 44%),
    #f3f3ee;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 10px;
  overflow: hidden;
}
.se-shot-bar {
  height: 30px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  background: #0a0a0a;
  color: #fafaf8;
}
.se-shot-bar span {
  width: 8px;
  height: 8px;
  background: var(--accent);
  display: block;
}
.se-shot-bar strong {
  margin-left: 6px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.se-shot-body {
  min-height: 0;
  background: #ffffff;
  border: 1px solid #d9d9d2;
  display: grid;
  place-items: center;
  overflow: hidden;
}
.se-shot img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.se-shot-caption {
  font-size: 12px;
  line-height: 1.35;
  color: #4b4b45;
}
""".strip()
    return {"html": html, "css": css}


def render_grid_card(data: dict[str, Any]) -> dict[str, str]:
    """渲染单体网格卡片 HTML/CSS 组件。"""
    accent = component_color(data, "accent", "#C5E803")
    index = esc(data.get("index", "01"))
    label = esc(data.get("label", "单体网格卡片标题"))
    body = esc(data.get("body", "卡片正文描述内容，可以自由调整。"))
    html = (
        f'<div class="se-grid-card" style="--accent:{accent};">'
        f'<div class="se-grid-index">{index}</div>'
        f'{editable_text(label, "label", "div", "se-grid-label")}'
        f'{editable_text(body, "body", "div", "se-grid-body")}'
        "</div>"
    )
    css = """
.se-grid-card {
  box-sizing: border-box;
  height: 100%;
  border-top: 5px solid var(--accent);
  background: #f3f3ee;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #0a0a0a;
  font-family: Inter, "Noto Sans SC", sans-serif;
}
.se-grid-index {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #66665f;
}
.se-grid-label {
  font-size: 17px;
  line-height: 1.25;
  font-weight: 700;
}
.se-grid-body {
  font-size: 13px;
  line-height: 1.45;
  color: #4b4b45;
  flex: 1;
}
""".strip()
    return {"html": html, "css": css}


BUILTIN_COMPONENTS = [
    {
        "name": "metric-card",
        "description": "单个关键指标卡，适合数据页或仪表盘式摘要。",
        "renderer": render_metric_card,
    },
    {
        "name": "grid-card",
        "description": "单体网格卡片，可任意拖拽组合，支持独立序号、标题和正文描述。",
        "renderer": render_grid_card,
    },
    {
        "name": "grid-list",
        "description": "网格列表，适合能力清单、要点组、对比项。",
        "renderer": render_grid_list,
    },
    {
        "name": "circular-flow",
        "description": "循环流程图，适合闭环、迭代流程、生态关系。",
        "renderer": render_circular_flow,
    },
    {
        "name": "compare-columns",
        "description": "双栏对比版式，适合 before/after、方案 A/B、S08 类页面。",
        "renderer": render_compare_columns,
    },
    {
        "name": "kpi-strip",
        "description": "横向 KPI 指标组，适合 S22 图片页下方指标或数据摘要。",
        "renderer": render_kpi_strip,
    },
    {
        "name": "screenshot-frame",
        "description": "截图美化框，适合把已上传截图包装成演示用主视觉。",
        "renderer": render_screenshot_frame,
    },
]
