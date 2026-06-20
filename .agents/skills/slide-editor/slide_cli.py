"""EVKIT2 幻灯片命令行编辑工具。

通过本地 Flask API 查看、定位、编辑、校验和导出幻灯片。
所有坐标均使用 960x540 画布坐标系。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from components import component_help, render_component as render_registered_component


CANVAS_W = 960
CANVAS_H = 540
DEFAULT_BASE = os.environ.get("SLIDE_API_BASE", "http://127.0.0.1:5001")


COMPONENT_HELP: dict[str, str] = component_help()
BATCH_ACTIONS = {"add", "update", "delete"}
DEFAULT_FONT_FAMILY = "Inter, Noto Sans SC, sans-serif"


def project_root() -> Path:
    """返回项目根目录。"""
    return Path(__file__).resolve().parents[3]


def session_path() -> Path:
    """返回 CLI 本地会话配置路径。"""
    return project_root() / ".slide_cli_session.json"


def read_session() -> dict[str, Any]:
    """读取 CLI 本地会话配置，格式错误时按空配置处理。"""
    path = session_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def default_workspace() -> str:
    """按环境变量、本地会话、default 的顺序确定默认工作区。"""
    return os.environ.get("SLIDE_WORKSPACE") or str(read_session().get("workspace") or "default")


def with_workspace(args: argparse.Namespace, path: str) -> str:
    """给 API 路径追加 workspace 查询参数。"""
    workspace = getattr(args, "workspace", "default") or "default"
    parsed = urllib.parse.urlsplit(path)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("workspace", workspace)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def api(args: argparse.Namespace, method: str, path: str, data: Any | None = None) -> Any:
    """调用 JSON API，并在失败时给出可读错误。"""
    url = f"{args.base.rstrip('/')}{with_workspace(args, path)}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        fail(f"HTTP {exc.code}: {message}")
    except Exception as exc:
        fail(f"无法连接 {url}: {exc}")


def fail(message: str, code: int = 1) -> None:
    """打印错误并退出。"""
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def emit(data: Any, as_json: bool = False) -> None:
    """按需输出 JSON 或文本。"""
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def resolve_input_path(path_text: str, *, allow_at_prefix: bool = False) -> Path:
    """解析输入文件路径；需要时兼容 PowerShell 中误写的 @file。"""
    raw = path_text
    if allow_at_prefix and raw.startswith("@"):
        raw = raw[1:]
        print(f"Info: 已兼容 @ 文件前缀，实际读取 {raw}", file=sys.stderr)
    expanded = os.path.expandvars(os.path.expanduser(raw))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    if not candidate.exists():
        fail(f"文件不存在: {path_text} (解析为 {candidate})")
    return candidate


def normalize_batch_operations(payload: Any) -> list[dict[str, Any]]:
    """解析 batch JSON，兼容根节点数组，并给出可读的 Schema 错误。"""
    if isinstance(payload, list):
        operations = payload
    elif isinstance(payload, dict):
        if "operations" not in payload:
            fail("batch JSON 顶层必须是数组，或包含 operations 数组的对象")
        operations = payload.get("operations")
    else:
        fail("batch JSON 顶层必须是数组或对象")

    if not isinstance(operations, list):
        fail("batch JSON 的 operations 必须是数组")

    normalized: list[dict[str, Any]] = []
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            fail(f"batch operations[{index}] 必须是 JSON 对象")
        item = dict(op)
        if "action" not in item and item.get("type") in BATCH_ACTIONS:
            item["action"] = item["type"]
        if item.get("action") not in BATCH_ACTIONS:
            fail(
                f"batch operations[{index}] 缺少有效 action。"
                "格式示例: {\"action\":\"add\",\"element\":{\"type\":\"text\",...}}"
            )
        normalized.append(item)
    return normalized


def require_number_field(elem: dict[str, Any], field: str, index: int) -> None:
    """确认元素关键几何字段存在且可转为数字。"""
    if field not in elem:
        fail(f"batch operations[{index}] add.element 缺少字段: {field}")
    try:
        float(elem.get(field))
    except (TypeError, ValueError):
        fail(f"batch operations[{index}] add.element 字段 {field} 必须是数字")


def normalize_text_element(elem: dict[str, Any]) -> None:
    """为批量新增文本补齐稳定渲染字段和估算高度。"""
    elem.setdefault("fontSize", 18)
    elem.setdefault("fill", "#0a0a0a")
    elem.setdefault("fontFamily", DEFAULT_FONT_FAMILY)
    elem.setdefault("fontWeight", "400")
    elem.setdefault("lineHeight", 1.4)
    elem.setdefault("textAlign", "left")
    elem.setdefault("text", "")
    if "height" not in elem:
        metrics = estimate_text_metrics(elem)
        elem["height"] = max(1, int(round(metrics["estimatedHeight"] + 4)))
    meta = elem.setdefault("meta", {})
    if isinstance(meta, dict):
        meta.setdefault("role", "body")


def normalize_batch_for_agent(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为 Agent 手写 batch 补齐默认字段，但不猜测关键坐标和宽度。"""
    normalized = json.loads(json.dumps(operations, ensure_ascii=False))
    for index, op in enumerate(normalized):
        if op.get("action") != "add":
            continue
        elem = op.get("element")
        if not isinstance(elem, dict):
            fail(f"batch operations[{index}] add.element 必须是 JSON 对象")
        if "type" not in elem:
            fail(f"batch operations[{index}] add.element 缺少字段: type")
        for field in ("x", "y", "width"):
            require_number_field(elem, field, index)
        elem.setdefault("angle", 0)
        elem.setdefault("opacity", 1)
        elem.setdefault("locked", False)
        if elem.get("type") == "text":
            normalize_text_element(elem)
        else:
            require_number_field(elem, "height", index)
            if elem.get("type") in {"rect", "circle", "triangle", "polygon"}:
                elem.setdefault("fill", "#C5E803")
                elem.setdefault("stroke", "")
                elem.setdefault("strokeWidth", 0)
    return normalized


def get_all(args: argparse.Namespace) -> dict[str, Any]:
    """获取完整幻灯片数据。"""
    return api(args, "GET", "/api/slides")


def get_slide(data: dict[str, Any], slide_id: str) -> dict[str, Any]:
    """按 id 查找幻灯片，兼容数字和字符串 id。"""
    for slide in data.get("slides", []):
        if str(slide.get("id")) == str(slide_id):
            return slide
    fail(f"找不到幻灯片: {slide_id}")


def resolve_slide_index(data: dict[str, Any], slide_index: int) -> str:
    """把 0 基页序号解析为幻灯片 ID，支持 -1 表示最后一页。"""
    slides = data.get("slides", []) or []
    if not slides:
        fail("当前工作区没有幻灯片")
    index = slide_index
    if index < 0:
        index = len(slides) + index
    if index < 0 or index >= len(slides):
        fail(f"页序号越界: {slide_index}，当前共有 {len(slides)} 页，合法范围 0..{len(slides) - 1} 或负数倒数")
    slide_id = slides[index].get("id")
    if slide_id is None:
        fail(f"页序号 {slide_index} 对应幻灯片缺少 id")
    return str(slide_id)


def resolve_slide_token(args: argparse.Namespace, value: str) -> str:
    """解析 #0/#-1 形式的页序号，否则原样返回 slide_id。"""
    if not isinstance(value, str) or not value.startswith("#"):
        return value
    try:
        index = int(value[1:])
    except ValueError:
        fail(f"页序号格式错误: {value}，应使用 #0 或 #-1")
    return resolve_slide_index(get_all(args), index)


def resolve_slide_targets(args: argparse.Namespace) -> None:
    """在执行命令前把 --slide-index 统一转换为 slide_id 或 --slide。"""
    if not hasattr(args, "slide_index") or args.slide_index is None:
        if hasattr(args, "slide_id") and getattr(args, "slide_id", None):
            args.slide_id = resolve_slide_token(args, args.slide_id)
        elif hasattr(args, "slide") and getattr(args, "slide", ""):
            args.slide = resolve_slide_token(args, args.slide)
        return
    data = get_all(args)
    resolved = resolve_slide_index(data, args.slide_index)
    if hasattr(args, "slide_id"):
        if getattr(args, "slide_id", None):
            fail("slide_id 和 --slide-index 不能同时使用")
        args.slide_id = resolved
    elif hasattr(args, "slide"):
        if getattr(args, "slide", ""):
            fail("--slide 和 --slide-index 不能同时使用")
        args.slide = resolved


def find_element(slide: dict[str, Any], elem_id: str) -> tuple[int, dict[str, Any]]:
    """在幻灯片中按 id 查找元素。"""
    for index, elem in enumerate(slide.get("canvas_elements", []) or []):
        if str(elem.get("id")) == str(elem_id):
            return index, elem
    fail(f"找不到元素: {elem_id}")


def element_bbox(elem: dict[str, Any]) -> dict[str, float]:
    """计算元素未旋转包围盒。"""
    x = float(elem.get("x", 0) or 0)
    y = float(elem.get("y", 0) or 0)
    w = float(elem.get("width", 0) or 0)
    h = float(elem.get("height", 0) or 0)
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(w, 2),
        "height": round(h, 2),
        "right": round(x + w, 2),
        "bottom": round(y + h, 2),
        "centerX": round(x + w / 2, 2),
        "centerY": round(y + h / 2, 2),
    }


def elem_preview(elem: dict[str, Any], limit: int = 48) -> str:
    """生成元素内容预览。"""
    etype = elem.get("type", "?")
    if etype == "text":
        text = str(elem.get("text", "")).replace("\n", "\\n")
        return text[:limit]
    if etype == "image":
        src = str(elem.get("src", ""))
        return src.split("/")[-1][:limit]
    if etype == "html":
        html = str(elem.get("html", "")).replace("\n", " ")
        return html[:limit]
    return str(elem.get("fill", ""))[:limit]


def elem_role(elem: dict[str, Any]) -> str:
    """读取元素角色。"""
    meta = elem.get("meta") if isinstance(elem.get("meta"), dict) else {}
    return str(meta.get("role") or "").lower()


def elem_component(elem: dict[str, Any]) -> str:
    """读取元素所属组件名。"""
    meta = elem.get("meta") if isinstance(elem.get("meta"), dict) else {}
    return str(meta.get("component") or "")


def slide_title(slide: dict[str, Any]) -> str:
    """读取幻灯片标题，优先使用旧 content.title 作为摘要信息。"""
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    title = str(content.get("title") or "").strip()
    if title:
        return title
    for elem in slide.get("canvas_elements", []) or []:
        if elem.get("type") == "text" and elem_role(elem) in {"title", "heading"}:
            return elem_preview(elem, 36)
    return ""


def is_placeholder(elem: dict[str, Any]) -> bool:
    """识别可被替换或填充的占位元素。"""
    role = elem_role(elem)
    if role in {"placeholder", "slot", "image-slot", "text-slot", "upload-slot"}:
        return True
    elem_id = str(elem.get("id", "")).lower()
    if any(token in elem_id for token in ("placeholder", "slot", "drop", "upload", "replace", "image-slot")):
        return True
    text = str(elem.get("text", "")).strip().lower()
    if text in {"", "双击编辑文字"} and elem.get("type") == "text":
        return True
    if any(token in text for token in ("占位", "placeholder", "上传", "替换", "放置图片", "image here")):
        return True
    if elem.get("type") == "image" and not elem.get("src"):
        return True
    return False


def placeholder_kind(elem: dict[str, Any]) -> str:
    """推断占位槽更适合的内容类型。"""
    role = elem_role(elem)
    text = f"{elem.get('id', '')} {elem.get('text', '')} {role}".lower()
    if elem.get("type") == "image" or any(token in text for token in ("image", "photo", "pic", "截图", "图片")):
        return "image"
    if elem.get("type") == "text" or any(token in text for token in ("text", "title", "body", "标题", "正文")):
        return "text"
    return "any"


def near_matches(elem: dict[str, Any], near: str) -> bool:
    """判断元素是否位于指定语义区域。"""
    if not near:
        return True
    bbox = element_bbox(elem)
    cx = bbox["centerX"]
    cy = bbox["centerY"]
    normalized = {"middle": "center", "centre": "center"}.get(near.lower(), near.lower())
    if normalized == "center":
        return CANVAS_W * 0.33 <= cx <= CANVAS_W * 0.67 and CANVAS_H * 0.33 <= cy <= CANVAS_H * 0.67
    if normalized == "top":
        return cy <= CANVAS_H * 0.33
    if normalized == "bottom":
        return cy >= CANVAS_H * 0.67
    if normalized == "left":
        return cx <= CANVAS_W * 0.33
    if normalized == "right":
        return cx >= CANVAS_W * 0.67
    return True


def allow_overlap(elem: dict[str, Any]) -> bool:
    """判断元素是否声明允许重叠。"""
    meta = elem.get("meta") if isinstance(elem.get("meta"), dict) else {}
    return bool(meta.get("allowOverlap"))


def is_decor(elem: dict[str, Any]) -> bool:
    """判断元素是否更像装饰，不参与主要重叠告警。"""
    role = elem_role(elem)
    if role in {"decor", "placeholder", "background"}:
        return True
    elem_id = str(elem.get("id", "")).lower()
    if any(token in elem_id for token in ("bg", "background", "divider", "line", "bar", "accent")):
        return True
    if elem.get("type") in {"rect", "circle", "triangle", "polygon"}:
        fill = str(elem.get("fill", "")).lower()
        opacity = float(elem.get("opacity", 1) or 1)
        stroke_width = float(elem.get("strokeWidth", 0) or 0)
        if fill in {"", "transparent", "none"} or opacity <= 0.25 or stroke_width > 0:
            return True
        if fill.startswith("rgba("):
            alpha_text = fill.rstrip(")").split(",")[-1].strip()
            try:
                if float(alpha_text) <= 0.12:
                    return True
            except ValueError:
                pass
        bbox = element_bbox(elem)
        if bbox["width"] >= CANVAS_W * 0.65 and bbox["height"] >= CANVAS_H * 0.45:
            return True
        if bbox["width"] <= 8 or bbox["height"] <= 8:
            return True
    return False


def overlap_info(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float] | None:
    """计算两个元素的重叠面积。"""
    ba = element_bbox(a)
    bb = element_bbox(b)
    left = max(ba["x"], bb["x"])
    top = max(ba["y"], bb["y"])
    right = min(ba["right"], bb["right"])
    bottom = min(ba["bottom"], bb["bottom"])
    if right <= left or bottom <= top:
        return None
    area = (right - left) * (bottom - top)
    min_area = max(1.0, min(ba["width"] * ba["height"], bb["width"] * bb["height"]))
    ratio = area / min_area
    text_pair = a.get("type") == "text" or b.get("type") == "text"
    area_threshold = 12 if text_pair else 36
    ratio_threshold = 0.04 if text_pair else 0.12
    if area < area_threshold or ratio < ratio_threshold:
        return None
    return {"area": round(area, 2), "ratio": round(ratio, 3)}


def rect_overlap_area(a: dict[str, float], b: dict[str, float], padding: int = 0) -> float:
    """计算两个 bbox 的重叠面积；padding 用于给已有元素扩张安全距离。"""
    left = max(a["x"], b["x"] - padding)
    top = max(a["y"], b["y"] - padding)
    right = min(a["right"], b["right"] + padding)
    bottom = min(a["bottom"], b["bottom"] + padding)
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def bbox_from_xywh(x: float, y: float, width: float, height: float) -> dict[str, float]:
    """按 x/y/width/height 生成统一 bbox。"""
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(width, 2),
        "height": round(height, 2),
        "right": round(x + width, 2),
        "bottom": round(y + height, 2),
        "centerX": round(x + width / 2, 2),
        "centerY": round(y + height / 2, 2),
    }


def placement_obstacles(elements: list[dict[str, Any]], ignore_id: str = "") -> list[dict[str, Any]]:
    """返回自动布局需要避开的主要元素。"""
    rows = []
    for elem in elements:
        if ignore_id and str(elem.get("id", "")) == str(ignore_id):
            continue
        if allow_overlap(elem) or is_decor(elem):
            continue
        rows.append(elem)
    return rows


def preferred_point(near: str, width: float, height: float) -> tuple[float, float]:
    """返回语义区域对应的偏好坐标，用于空位排序。"""
    x = (CANVAS_W - width) / 2
    y = (CANVAS_H - height) / 2
    if near == "top":
        y = 40
    elif near == "bottom":
        y = CANVAS_H - height - 40
    elif near == "left":
        x = 60
    elif near == "right":
        x = CANVAS_W - width - 60
    elif near in {"center", "middle"}:
        pass
    return x, y


def near_penalty(bbox: dict[str, float], near: str) -> float:
    """计算 bbox 偏离语义区域的惩罚分。"""
    px, py = preferred_point(near, bbox["width"], bbox["height"])
    if near in {"left", "right"}:
        return abs(bbox["x"] - px)
    if near in {"top", "bottom"}:
        return abs(bbox["y"] - py)
    return abs(bbox["x"] - px) + abs(bbox["y"] - py)


def find_free_placements(
    slide: dict[str, Any],
    width: int,
    height: int,
    *,
    near: str = "center",
    gap: int = 12,
    margin: int = 40,
    snap: int = 4,
    limit: int = 8,
    ignore_id: str = "",
) -> list[dict[str, Any]]:
    """基于现有元素边界生成候选空位，按不重叠和区域偏好排序。"""
    width = max(1, int(width))
    height = max(1, int(height))
    if width > CANVAS_W or height > CANVAS_H:
        return []

    elements = slide.get("canvas_elements", []) or []
    obstacles = placement_obstacles(elements, ignore_id=ignore_id)
    x_seeds = {margin, (CANVAS_W - width) / 2, CANVAS_W - width - margin}
    y_seeds = {margin, (CANVAS_H - height) / 2, CANVAS_H - height - margin}
    pref_x, pref_y = preferred_point(near, width, height)
    x_seeds.add(pref_x)
    y_seeds.add(pref_y)

    for elem in obstacles:
        b = element_bbox(elem)
        x_seeds.update({b["x"], b["right"] + gap, b["x"] - width - gap})
        y_seeds.update({b["y"], b["bottom"] + gap, b["y"] - height - gap})

    def clamp_snap(value: float, max_value: int) -> int:
        value = min(max(0, value), max_value)
        if snap and snap > 1:
            value = round(value / snap) * snap
        return int(min(max(0, value), max_value))

    candidates: dict[tuple[int, int], dict[str, Any]] = {}
    for raw_x in x_seeds:
        for raw_y in y_seeds:
            x = clamp_snap(raw_x, CANVAS_W - width)
            y = clamp_snap(raw_y, CANVAS_H - height)
            bbox = bbox_from_xywh(x, y, width, height)
            overlaps = []
            overlap_area = 0.0
            for elem in obstacles:
                area = rect_overlap_area(bbox, element_bbox(elem), padding=gap)
                if area > 0:
                    overlaps.append(elem.get("id", ""))
                    overlap_area += area
            if overlaps:
                continue
            edge_score = min(x, y, CANVAS_W - bbox["right"], CANVAS_H - bbox["bottom"])
            candidates[(x, y)] = {
                "bbox": bbox,
                "score": round(near_penalty(bbox, near) - edge_score * 0.1 + overlap_area * 10, 2),
                "near": near,
                "gap": gap,
            }

    rows = sorted(candidates.values(), key=lambda item: (item["score"], item["bbox"]["y"], item["bbox"]["x"]))
    return rows[: max(1, limit)]


def choose_free_placement(
    slide: dict[str, Any],
    width: int,
    height: int,
    *,
    near: str = "center",
    gap: int = 12,
    margin: int = 40,
    snap: int = 4,
    ignore_id: str = "",
) -> dict[str, Any]:
    """选择一个可用空位，找不到时直接给出可读错误。"""
    rows = find_free_placements(
        slide,
        width,
        height,
        near=near,
        gap=gap,
        margin=margin,
        snap=snap,
        limit=1,
        ignore_id=ignore_id,
    )
    if not rows:
        fail(f"找不到 {width}x{height} 的无重叠空位；可减小尺寸、改 --near 或降低 --gap")
    return rows[0]


def choose_axis_constrained_placement(
    slide: dict[str, Any],
    bbox: dict[str, float],
    *,
    axis: str,
    gap: int,
    margin: int,
    snap: int,
    ignore_id: str = "",
) -> dict[str, Any] | None:
    """在只允许单轴移动时寻找不重叠位置。"""
    if axis not in {"x", "y"}:
        return None
    width = int(bbox["width"])
    height = int(bbox["height"])
    obstacles = placement_obstacles(slide.get("canvas_elements", []) or [], ignore_id=ignore_id)
    x_values = {bbox["x"]}
    y_values = {bbox["y"]}
    if axis == "x":
        x_values.update({margin, CANVAS_W - width - margin, (CANVAS_W - width) / 2})
        for elem in obstacles:
            other = element_bbox(elem)
            x_values.update({other["right"] + gap, other["x"] - width - gap})
    else:
        y_values.update({margin, CANVAS_H - height - margin, (CANVAS_H - height) / 2})
        for elem in obstacles:
            other = element_bbox(elem)
            y_values.update({other["bottom"] + gap, other["y"] - height - gap})

    def snap_value(value: float, maximum: int) -> int:
        value = min(max(0, value), maximum)
        if snap and snap > 1:
            value = round(value / snap) * snap
        return int(min(max(0, value), maximum))

    candidates: list[dict[str, Any]] = []
    for raw_x in x_values:
        for raw_y in y_values:
            x = snap_value(raw_x, CANVAS_W - width)
            y = snap_value(raw_y, CANVAS_H - height)
            candidate = bbox_from_xywh(x, y, width, height)
            overlap_area = 0.0
            overlaps: list[str] = []
            for elem in obstacles:
                area = rect_overlap_area(candidate, element_bbox(elem), padding=gap)
                if area > 0:
                    overlaps.append(elem.get("id", ""))
                    overlap_area += area
            if overlaps:
                continue
            shift = abs(candidate["x"] - bbox["x"]) + abs(candidate["y"] - bbox["y"])
            candidates.append({"bbox": candidate, "score": round(shift, 2), "overlaps": []})
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item["score"])[0]


def estimate_text_height(elem: dict[str, Any]) -> float:
    """保守估算文本渲染高度，用于发现明显溢出。"""
    return estimate_text_metrics(elem)["estimatedHeight"]


def estimate_text_metrics(elem: dict[str, Any]) -> dict[str, float]:
    """估算文本行数、渲染高度和不可断长词宽度。"""
    text = str(elem.get("text", ""))
    font_size = float(elem.get("fontSize", 18) or 18)
    line_height = float(elem.get("lineHeight", 1.4) or 1.4)
    width = max(float(elem.get("width", 1) or 1), 1)
    visual_lines = 0
    max_unbreakable_width = 0.0
    for raw_line in text.splitlines() or [""]:
        line_width = 0.0
        for char in raw_line:
            if char.isspace():
                line_width += font_size * 0.32
            elif ord(char) < 128:
                line_width += font_size * 0.52
            else:
                line_width += font_size * 0.95
        visual_lines += max(1, int((line_width + width - 1) // width))
        for token in re.split(r"\s+", raw_line):
            token_width = 0.0
            for char in token:
                token_width += font_size * (0.52 if ord(char) < 128 else 0.95)
            max_unbreakable_width = max(max_unbreakable_width, token_width)
    return {
        "visualLines": float(visual_lines),
        "estimatedHeight": round(visual_lines * font_size * line_height, 2),
        "maxUnbreakableWidth": round(max_unbreakable_width, 2),
        "boxWidth": round(width, 2),
    }


def inspect_slide(slide: dict[str, Any], include_overlaps: bool = False) -> dict[str, Any]:
    """生成单页元素检查摘要。"""
    elements = slide.get("canvas_elements", []) or []
    items = []
    warnings = []

    for index, elem in enumerate(elements):
        bbox = element_bbox(elem)
        item = {
            "index": index,
            "id": elem.get("id", ""),
            "type": elem.get("type", ""),
            "role": elem_role(elem),
            "bbox": bbox,
            "z": index,
            "locked": bool(elem.get("locked", False)),
            "preview": elem_preview(elem),
        }
        if elem.get("type") == "text":
            item["fontSize"] = elem.get("fontSize", 18)
            metrics = estimate_text_metrics(elem)
            item["estimatedTextHeight"] = metrics["estimatedHeight"]
            item["visualLines"] = int(metrics["visualLines"])
            item["maxUnbreakableWidth"] = metrics["maxUnbreakableWidth"]
        if elem.get("type") == "image":
            item["src"] = elem.get("src", "")
        if elem_component(elem):
            item["component"] = elem_component(elem)
        if is_placeholder(elem):
            item["placeholderKind"] = placeholder_kind(elem)
        items.append(item)

        if bbox["x"] < 0 or bbox["y"] < 0 or bbox["right"] > CANVAS_W or bbox["bottom"] > CANVAS_H:
            warnings.append(warn("bounds", elem, f"元素越界 bbox={bbox}"))
        if elem.get("type") == "text":
            metrics = estimate_text_metrics(elem)
            if metrics["estimatedHeight"] > float(elem.get("height", 0) or 0) + 4:
                warnings.append(warn("text-overflow", elem, f"文本高度疑似不足，估算 {metrics['estimatedHeight']}px"))
            if metrics["maxUnbreakableWidth"] > bbox["width"] + 4:
                warnings.append(warn("text-width", elem, f"存在不可断长词，估算宽 {metrics['maxUnbreakableWidth']}px"))

    if include_overlaps:
        warnings.extend(find_overlaps(elements))

    return {
        "slideId": slide.get("id"),
        "backgroundColor": slide.get("backgroundColor", "#fafaf8"),
        "elementCount": len(elements),
        "elements": items,
        "warnings": warnings,
    }


_WIREFRAME_LABELS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def render_ascii_wireframe(slide: dict[str, Any], cols: int = 80, rows: int = 24) -> str:
    """把幻灯片 canvas_elements 渲染成 ASCII 线框图，便于一眼看相对位置。"""
    elements = slide.get("canvas_elements", []) or []
    inner_cols = max(10, cols - 2)
    inner_rows = max(6, rows - 2)
    sx = inner_cols / CANVAS_W
    sy = inner_rows / CANVAS_H
    grid = [[" "] * inner_cols for _ in range(inner_rows)]
    legend_lines: list[str] = []
    for i, elem in enumerate(elements):
        bbox = element_bbox(elem)
        ch = _WIREFRAME_LABELS[i] if i < len(_WIREFRAME_LABELS) else "*"
        x0 = max(0, min(inner_cols - 1, int(bbox["x"] * sx)))
        y0 = max(0, min(inner_rows - 1, int(bbox["y"] * sy)))
        x1 = max(x0 + 1, min(inner_cols, int(round(bbox["right"] * sx))))
        y1 = max(y0 + 1, min(inner_rows, int(round(bbox["bottom"] * sy))))
        for r in range(y0, y1):
            for c in range(x0, x1):
                grid[r][c] = ch
        legend_lines.append(
            f"  {ch} #{i:02d} {elem.get('type', '?'):<5} id={elem.get('id', '') or '-':<20} "
            f"xy=({int(bbox['x'])},{int(bbox['y'])}) {int(bbox['width'])}x{int(bbox['height'])}  "
            f"{elem_preview(elem, 32)}"
        )
    border = "+" + "-" * inner_cols + "+"
    body = ["|" + "".join(row) + "|" for row in grid]
    header = f"canvas {CANVAS_W}x{CANVAS_H} -> ascii {inner_cols}x{inner_rows} ({len(elements)} elements)"
    return "\n".join([header, border] + body + [border] + legend_lines)


def render_inspect_summary(report: dict[str, Any], include_warnings: bool = False) -> str:
    """输出便于快速定位的紧凑元素摘要。"""
    lines = [
        f"Slide {report['slideId']} elements={report['elementCount']} bg={report['backgroundColor']}",
        "z    id                         type   role          xy        size       preview",
    ]
    for item in report["elements"]:
        b = item["bbox"]
        role = item.get("role") or "-"
        lines.append(
            f"{item['z']:02d}   {str(item['id'] or '-')[:26]:<26} "
            f"{str(item['type'] or '-')[:6]:<6} {role[:12]:<12} "
            + f"({int(b['x'])},{int(b['y'])})".ljust(11)
            + f"{int(b['width'])}x{int(b['height'])}".ljust(11)
            + f"{item['preview']}"
        )
    if include_warnings and report["warnings"]:
        lines.append("warnings:")
        for warning in report["warnings"]:
            lines.append(f"  ! {warning['kind']}: {warning.get('id') or warning.get('ids')} {warning['message']}")
    return "\n".join(lines)


def warn(kind: str, elem: dict[str, Any], message: str) -> dict[str, Any]:
    """创建统一告警对象。"""
    return {"kind": kind, "id": elem.get("id", ""), "type": elem.get("type", ""), "message": message}


def find_overlaps(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """查找非刻意重叠。"""
    warnings = []
    for i, a in enumerate(elements):
        if allow_overlap(a) or is_decor(a):
            continue
        for b in elements[i + 1 :]:
            if allow_overlap(b) or is_decor(b):
                continue
            info = overlap_info(a, b)
            if info:
                warnings.append({
                    "kind": "overlap",
                    "ids": [a.get("id", ""), b.get("id", "")],
                    "message": f"疑似重叠 area={info['area']} ratio={info['ratio']}",
                })
    return warnings


def validate_slide(slide: dict[str, Any]) -> dict[str, Any]:
    """校验单页数据结构和布局风险。"""
    elements = slide.get("canvas_elements", []) or []
    warnings = []
    errors = []
    seen: set[str] = set()

    for elem in elements:
        elem_id = str(elem.get("id", ""))
        etype = elem.get("type")
        if not elem_id:
            errors.append(warn("missing-id", elem, "元素缺少 id"))
        elif elem_id in seen:
            errors.append(warn("duplicate-id", elem, f"元素 id 重复: {elem_id}"))
        seen.add(elem_id)

        if etype not in {"text", "image", "rect", "circle", "triangle", "polygon", "html"}:
            errors.append(warn("bad-type", elem, f"未知元素类型: {etype}"))

        for field in ("x", "y", "width", "height"):
            if field not in elem:
                errors.append(warn("missing-field", elem, f"缺少字段: {field}"))

        bbox = element_bbox(elem)
        if bbox["width"] <= 0 or bbox["height"] <= 0:
            errors.append(warn("bad-size", elem, "width/height 必须大于 0"))
        if bbox["x"] < 0 or bbox["y"] < 0 or bbox["right"] > CANVAS_W or bbox["bottom"] > CANVAS_H:
            warnings.append(warn("bounds", elem, f"元素越界 bbox={bbox}"))

        if etype == "text":
            if "text" not in elem:
                errors.append(warn("missing-text", elem, "文本元素缺少 text"))
            else:
                metrics = estimate_text_metrics(elem)
                if metrics["estimatedHeight"] > float(elem.get("height", 0) or 0) + 4:
                    warnings.append(warn("text-overflow", elem, f"文本高度疑似不足，估算 {metrics['estimatedHeight']}px"))
                if metrics["maxUnbreakableWidth"] > bbox["width"] + 4:
                    warnings.append(warn("text-width", elem, f"存在不可断长词，估算宽 {metrics['maxUnbreakableWidth']}px"))
        if etype == "image" and not elem.get("src"):
            errors.append(warn("missing-src", elem, "图片元素缺少 src"))
        if etype == "html" and not elem.get("html"):
            warnings.append(warn("missing-html", elem, "html 元素缺少 html 内容"))

    warnings.extend(find_overlaps(elements))
    return {
        "slideId": slide.get("id"),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def parse_value(value: str) -> Any:
    """解析命令行属性值。"""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return json.loads(value)
    except Exception:
        pass
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def read_text_file(path_text: str) -> str:
    """读取文本文件内容，支持 ~ 和环境变量。"""
    expanded = os.path.expandvars(os.path.expanduser(path_text))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    if not candidate.exists():
        fail(f"文件不存在: {path_text} (解析为 {candidate})")
    return candidate.read_text(encoding="utf-8")


def parse_properties(props: list[str] | None) -> dict[str, Any]:
    """解析 key=value 属性列表。

    - 支持 `meta.role` 这类点路径。
    - 值以 `@` 开头时读取文件内容作为字符串值，便于注入长段 HTML/CSS。
    """
    result: dict[str, Any] = {}
    for prop in props or []:
        if "=" not in prop:
            fail(f"属性必须是 key=value 格式: {prop}")
        key, raw = prop.split("=", 1)
        target = result
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        if raw.startswith("@"):
            target[parts[-1]] = read_text_file(raw[1:])
        else:
            target[parts[-1]] = parse_value(raw)
    return result


def build_element(args: argparse.Namespace) -> dict[str, Any]:
    """根据 add/upload-place 参数构造元素。"""
    x = args.x
    y = args.y
    if getattr(args, "center_h", False):
        x = (CANVAS_W - args.width) // 2
    if getattr(args, "center_v", False):
        y = (CANVAS_H - args.height) // 2
    elem: dict[str, Any] = {
        "type": args.type,
        "x": x,
        "y": y,
        "width": args.width,
        "height": args.height,
        "angle": getattr(args, "angle", 0) or 0,
        "opacity": getattr(args, "opacity", 1) if getattr(args, "opacity", None) is not None else 1,
        "locked": bool(getattr(args, "locked", False)),
    }
    if getattr(args, "id", ""):
        elem["id"] = args.id
    meta = parse_properties(getattr(args, "meta", None))
    if meta:
        elem["meta"] = meta.get("meta", meta)

    if args.type == "text":
        raw_text = args.text or ""
        if "\\n" in raw_text:
            raw_text = raw_text.replace("\\n", "\n").replace("\\t", "\t")
        elem.update({
            "text": raw_text,
            "fontSize": args.font_size,
            "fill": args.fill or "#0a0a0a",
            "fontFamily": args.font_family or DEFAULT_FONT_FAMILY,
            "fontWeight": args.font_weight or "400",
            "lineHeight": args.line_height or 1.4,
            "textAlign": args.text_align or "left",
        })
    elif args.type == "image":
        elem.update({"src": args.src, "clipType": args.clip_type or "rect", "rx": args.rx or 0})
    elif args.type in {"rect", "circle", "triangle", "polygon"}:
        elem.update({
            "fill": args.fill or "#C5E803",
            "stroke": getattr(args, "stroke", "") or "",
            "strokeWidth": getattr(args, "stroke_width", 0) or 0,
            "rx": args.rx or 0,
            "ry": getattr(args, "ry", 0) or 0,
        })
    elif args.type == "html":
        elem.update({"html": args.html, "css": args.css or ""})
    elif args.type == "3d":
        from three_templates import build_3d_element
        custom_code = None
        if args.geometry == "custom":
            if args.custom_code and args.custom_file:
                fail("--custom-code 和 --custom-file 不能同时使用")
            if args.custom_code:
                custom_code = args.custom_code
            elif args.custom_file:
                custom_path = Path(os.path.expandvars(os.path.expanduser(args.custom_file)))
                if not custom_path.exists():
                    fail(f"自定义 3D 场景文件不存在: {args.custom_file}")
                custom_code = custom_path.read_text(encoding="utf-8")
            if not custom_code:
                fail("--geometry custom 时必须提供 --custom-code 或 --custom-file")
        three_elem = build_3d_element(
            geometry=args.geometry,
            color=args.fill or "#C5E803",
            auto_rotate=args.auto_rotate,
            rotate_speed=args.rotate_speed,
            metalness=args.metalness,
            roughness=args.roughness,
            wireframe=args.wireframe,
            background=args.bg,
            width=args.width,
            height=args.height,
            custom_code=custom_code,
        )
        elem.update(three_elem)
    return elem


def read_component_data(source: str) -> dict[str, Any]:
    """读取组件数据，支持 JSON 字符串、@文件和普通文件路径。"""
    if not source:
        return {}
    raw = source
    path_text = source[1:] if source.startswith("@") else source
    candidate = Path(os.path.expandvars(os.path.expanduser(path_text)))
    if candidate.exists():
        raw = candidate.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        data = parse_loose_object(raw)
        if data is None:
            fail(f"组件数据必须是 JSON 对象或 JSON 文件: {exc}")
    if not isinstance(data, dict):
        fail("组件数据顶层必须是 JSON 对象")
    return data


def parse_loose_object(raw: str) -> dict[str, Any] | None:
    """兼容 PowerShell 中容易丢失双引号的一层 key:value 对象。"""
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    body = text[1:-1].strip()
    if not body:
        return {}
    result: dict[str, Any] = {}
    for part in body.split(","):
        if ":" not in part:
            return None
        key, value = part.split(":", 1)
        key = key.strip().strip("\"'")
        value = value.strip().strip("\"'")
        if not key:
            return None
        result[key] = parse_value(value)
    return result


def upload_file(args: argparse.Namespace, filepath: str) -> dict[str, Any]:
    """使用标准库 multipart/form-data 上传文件。"""
    expanded = os.path.expandvars(os.path.expanduser(filepath))
    path = Path(expanded)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        fail(f"文件不存在: {filepath} (cwd={os.getcwd()}, 解析为 {path})")

    boundary = f"----slidecli-{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    file_bytes = path.read_bytes()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + file_bytes + tail

    req = urllib.request.Request(f"{args.base.rstrip('/')}{with_workspace(args, '/api/upload')}", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        fail(f"上传失败 HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
    except Exception as exc:
        fail(f"上传失败: {exc}")


def read_text_if_exists(path: Path) -> str:
    """读取文本文件，不存在时返回空字符串。"""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def collect_asset_index() -> dict[str, Any]:
    """从本地模板和静态目录提取字体、图标、颜色 token 和素材索引。"""
    root = Path.cwd()
    template_paths = [
        root / "templates" / "presentation.html",
        root / "templates" / "editor.html",
        root / "templates" / "editor_fixed.html",
    ]
    texts = {str(path.relative_to(root)): read_text_if_exists(path) for path in template_paths if path.exists()}
    combined = "\n".join(texts.values())

    font_faces: set[str] = set()
    generic_fonts = {"inherit", "sans-serif", "serif", "monospace", "system-ui", "ui-monospace"}
    for declaration in re.findall(r"font-family\s*:\s*([^;{}]+);", combined):
        if "{{" in declaration or "}}" in declaration:
            continue
        for name in declaration.split(","):
            cleaned = name.strip().strip("\"'")
            if not cleaned or cleaned in generic_fonts or cleaned.startswith("var("):
                continue
            font_faces.add(cleaned)
    google_fonts = sorted(set(re.findall(r"family=([^&\"']+)", combined)))
    css_tokens = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", combined):
        css_tokens.setdefault(name, value.strip())

    material_icons = sorted({
        icon for icon in re.findall(r"<span[^>]+material-symbols-rounded[^>]*>\s*([^<\s]+)\s*</span>", combined)
        if "$" not in icon and "{" not in icon
    })
    static_assets = []
    for base in [root / "static", root / "image"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                static_assets.append({
                    "path": rel,
                    "size": path.stat().st_size,
                    "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                })

    return {
        "fonts": {
            "fontFamiliesInCss": sorted(font_faces),
            "googleFamilies": [urllib.parse.unquote(item).replace("+", " ").split(":", 1)[0] for item in google_fonts],
            "recommendedText": "Inter, Noto Sans SC, sans-serif",
            "recommendedMono": "JetBrains Mono, monospace",
            "iconFont": "Material Symbols Rounded",
            "guizangFonts": {
                "serif": '"Noto Serif SC", "Playfair Display", serif',
                "sans": '"Noto Sans SC", sans-serif',
                "mono": '"JetBrains Mono", "IBM Plex Mono", monospace',
            },
        },
        "tokens": css_tokens,
        "guizangThemes": {
            "magazine": {
                "monocle": {"--ink": "#0a0a0b", "--paper": "#f1efea", "--paper-tint": "#e8e5de", "--ink-tint": "#18181a"},
                "indigo": {"--ink": "#0a1f3d", "--paper": "#f1f3f5", "--paper-tint": "#e4e8ec", "--ink-tint": "#152a4a"},
                "forest": {"--ink": "#1a2e1f", "--paper": "#f5f1e8", "--paper-tint": "#ece7da", "--ink-tint": "#253d2c"},
                "kraft": {"--ink": "#2a1e13", "--paper": "#eedfc7", "--paper-tint": "#e0d0b6", "--ink-tint": "#3a2a1d"},
                "dune": {"--ink": "#1f1a14", "--paper": "#f0e6d2", "--paper-tint": "#e3d7bf", "--ink-tint": "#2d2620"},
            },
            "swiss": {
                "ikb": {"--accent": "#1677FF", "--accent-on": "#ffffff"},
                "lemon-yellow": {"--accent": "#FFD500", "--accent-on": "#0a0a0a"},
                "lemon-green": {"--accent": "#C5E803", "--accent-on": "#0a0a0a"},
                "safety-orange": {"--accent": "#FF6B35", "--accent-on": "#ffffff"},
            },
        },
        "icons": {
            "library": "Material Symbols Rounded",
            "usedInTemplates": material_icons[:200],
            "guizangIcons": "Lucide Icons (via CDN, e.g. compass, target, share-2, users, workflow, bar-chart-3, etc.)",
        },
        "assets": static_assets,
        "templates": list(texts.keys()),
    }


def cmd_assets(args: argparse.Namespace) -> None:
    index = collect_asset_index()
    if args.json:
        emit(index, True)
        return

    print("Fonts:")
    for font in index["fonts"]["fontFamiliesInCss"][:20]:
        print(f"  - {font}")
    print("\nRecommended:")
    print(f"  text: {index['fonts']['recommendedText']}")
    print(f"  mono: {index['fonts']['recommendedMono']}")
    print(f"  icon: {index['fonts']['iconFont']}")
    
    gz_fonts = index["fonts"].get("guizangFonts")
    if gz_fonts:
        print("\nGuizang Fonts:")
        print(f"  serif: {gz_fonts['serif']}")
        print(f"  sans:  {gz_fonts['sans']}")
        print(f"  mono:  {gz_fonts['mono']}")
    
    print("\nCSS tokens:")
    for name in sorted(index["tokens"])[:80]:
        print(f"  {name}: {index['tokens'][name]}")
    
    gz_themes = index.get("guizangThemes")
    if gz_themes:
        print("\nGuizang Magazine Themes:")
        for name, tokens in gz_themes["magazine"].items():
            print(f"  {name}: ink={tokens['--ink']} paper={tokens['--paper']}")
        print("\nGuizang Swiss Themes:")
        for name, tokens in gz_themes["swiss"].items():
            print(f"  {name}: accent={tokens['--accent']}")
    
    print("\nIcons used in templates:")
    for icon in index["icons"]["usedInTemplates"][:80]:
        print(f"  - {icon}")
    
    gz_icons = index["icons"].get("guizangIcons")
    if gz_icons:
        print(f"\nGuizang Icons: {gz_icons}")
    
    print(f"\nAssets: {len(index['assets'])} files under static/ and image/")


def cmd_status(args: argparse.Namespace) -> None:
    data = get_all(args)
    slides = data.get("slides", [])
    elem_count = sum(len(s.get("canvas_elements", []) or []) for s in slides)
    emit({
        "base": args.base,
        "workspace": args.workspace,
        "version": data.get("_version"),
        "slides": len(slides),
        "elements": elem_count,
    }, args.json)


def cmd_list(args: argparse.Namespace) -> None:
    data = get_all(args)
    rows = []
    for index, slide in enumerate(data.get("slides", []), start=1):
        rows.append({
            "index": index,
            "id": slide.get("id"),
            "theme": slide.get("theme", ""),
            "backgroundColor": slide.get("backgroundColor", ""),
            "elements": len(slide.get("canvas_elements", []) or []),
            "title": (slide.get("content") or {}).get("title", ""),
        })
    if args.json:
        emit({"workspace": args.workspace, "slides": rows}, True)
    else:
        print(f"Workspace: {args.workspace}")
        for row in rows:
            print(f"[{row['index']}] id={row['id']} theme={row['theme']} bg={row['backgroundColor']} elements={row['elements']} title={row['title']}")


def compact_element(elem: dict[str, Any], index: int) -> dict[str, Any]:
    """输出适合 Agent 快速浏览的元素摘要。"""
    bbox = element_bbox(elem)
    item: dict[str, Any] = {
        "index": index,
        "id": elem.get("id", ""),
        "type": elem.get("type", ""),
        "role": elem_role(elem),
        "bbox": [bbox["x"], bbox["y"], bbox["width"], bbox["height"]],
        "preview": elem_preview(elem, 42),
    }
    if elem_component(elem):
        item["component"] = elem_component(elem)
    if is_placeholder(elem):
        item["slot"] = placeholder_kind(elem)
    return item


def cmd_overview(args: argparse.Namespace) -> None:
    """一次性输出全局或单页紧凑总览，减少多次 list/inspect。"""
    data = get_all(args)
    all_slides = data.get("slides", []) or []
    slides: list[tuple[int, dict[str, Any]]] = []
    for slide_index, slide in enumerate(all_slides, start=1):
        if args.slide and str(slide.get("id")) != str(args.slide):
            continue
        slides.append((slide_index, slide))
    if args.slide and not slides:
        get_slide(data, args.slide)
    rows = []
    for slide_index, slide in slides:
        elements = slide.get("canvas_elements", []) or []
        validation = validate_slide(slide) if args.warnings else {"errors": [], "warnings": [], "ok": True}
        row: dict[str, Any] = {
            "index": slide_index,
            "id": slide.get("id"),
            "title": slide_title(slide),
            "theme": slide.get("theme", ""),
            "backgroundColor": slide.get("backgroundColor", ""),
            "elements": len(elements),
            "placeholders": sum(1 for elem in elements if is_placeholder(elem)),
            "errors": len(validation["errors"]),
            "warnings": len(validation["warnings"]),
        }
        if args.slide or args.elements:
            limit = max(0, args.limit)
            row["items"] = [compact_element(elem, i) for i, elem in enumerate(elements[:limit])]
            if len(elements) > limit:
                row["itemsOmitted"] = len(elements) - limit
        if args.warnings:
            row["issues"] = validation["errors"] + validation["warnings"]
        rows.append(row)

    if args.json:
        emit({"workspace": args.workspace, "slides": rows}, True)
        return
    print(f"Workspace: {args.workspace}")
    for row in rows:
        print(
            f"[{row['index']}] id={row['id']} elems={row['elements']} "
            f"slots={row['placeholders']} issues={row['errors']}/{row['warnings']} title={row['title']}"
        )
        for item in row.get("items", []):
            x, y, w, h = item["bbox"]
            role = f" role={item['role']}" if item["role"] else ""
            slot = f" slot={item['slot']}" if item.get("slot") else ""
            print(f"  #{item['index']:02d} {item['id']} {item['type']}{role}{slot} xy=({x},{y}) {w}x{h} {item['preview']}")
        for issue in row.get("issues", []):
            print(f"  ! {issue['kind']}: {issue.get('id') or issue.get('ids')} {issue['message']}")


def cmd_inspect(args: argparse.Namespace) -> None:
    slide = get_slide(get_all(args), args.slide_id)
    report = inspect_slide(slide, include_overlaps=args.overlaps)
    wireframe = None
    if getattr(args, "ascii", False):
        wireframe = render_ascii_wireframe(slide, cols=args.cols, rows=args.rows)
    if args.json:
        if wireframe is not None:
            report["wireframe"] = wireframe
        report["workspace"] = args.workspace
        emit(report, True)
        return
    print(f"Workspace: {args.workspace}")
    if getattr(args, "summary", False):
        print(render_inspect_summary(report, include_warnings=args.warnings))
        if wireframe is not None:
            print()
            print(wireframe)
        return
    print(f"Slide {report['slideId']} bg={report['backgroundColor']} elements={report['elementCount']}")
    for item in report["elements"]:
        b = item["bbox"]
        print(f"  #{item['index']:02d} {item['id']} {item['type']} z={item['z']} xy=({b['x']},{b['y']}) size={b['width']}x{b['height']} {item['preview']}")
    for warning in report["warnings"]:
        print(f"  ! {warning['kind']}: {warning.get('id') or warning.get('ids')} {warning['message']}")
    if wireframe is not None:
        print()
        print(wireframe)


def cmd_find(args: argparse.Namespace) -> None:
    data = get_all(args)
    matches = []
    for slide_index, slide in enumerate(data.get("slides", []), start=1):
        if args.slide and str(slide.get("id")) != str(args.slide):
            continue
        for elem_index, elem in enumerate(slide.get("canvas_elements", []) or []):
            ok = True
            if args.id and args.id not in str(elem.get("id", "")):
                ok = False
            if args.type:
                # 3d 是 html + meta.role='3d' 的别名
                if args.type == "3d":
                    if elem.get("type") != "html" or elem_role(elem) != "3d":
                        ok = False
                elif args.type != elem.get("type"):
                    ok = False
            if args.role and args.role.lower() != elem_role(elem):
                ok = False
            if args.near and not near_matches(elem, args.near):
                ok = False
            if args.text:
                haystack = "\n".join(str(elem.get(k, "")) for k in ("text", "html", "src"))
                if args.text.lower() not in haystack.lower():
                    ok = False
            if ok:
                matches.append({
                    "slideIndex": slide_index,
                    "slideId": slide.get("id"),
                    "elementIndex": elem_index,
                    "id": elem.get("id"),
                    "type": elem.get("type"),
                    "role": elem_role(elem),
                    "bbox": element_bbox(elem),
                    "preview": elem_preview(elem),
                })
    emit(matches, args.json)


def cmd_slots(args: argparse.Namespace) -> None:
    """列出可填充占位槽，便于把文本或图片放到准确位置。"""
    data = get_all(args)
    rows = []
    for slide_index, slide in enumerate(data.get("slides", []), start=1):
        if args.slide and str(slide.get("id")) != str(args.slide):
            continue
        for elem_index, elem in enumerate(slide.get("canvas_elements", []) or []):
            if not is_placeholder(elem):
                continue
            kind = placeholder_kind(elem)
            if args.kind != "any" and kind not in {args.kind, "any"}:
                continue
            bbox = element_bbox(elem)
            rows.append({
                "slideIndex": slide_index,
                "slideId": slide.get("id"),
                "elementIndex": elem_index,
                "id": elem.get("id"),
                "type": elem.get("type"),
                "kind": kind,
                "role": elem_role(elem),
                "bbox": bbox,
                "preview": elem_preview(elem),
            })
    if args.json:
        emit(rows, True)
        return
    for row in rows:
        b = row["bbox"]
        print(
            f"slide={row['slideId']} #{row['elementIndex']:02d} id={row['id']} "
            f"type={row['type']} kind={row['kind']} xy=({b['x']},{b['y']}) {b['width']}x{b['height']} {row['preview']}"
        )


def cmd_space(args: argparse.Namespace) -> None:
    """查找指定尺寸的无重叠空位，减少手算坐标。"""
    slide = get_slide(get_all(args), args.slide_id)
    rows = find_free_placements(
        slide,
        args.width,
        args.height,
        near=args.near,
        gap=args.gap,
        margin=args.margin,
        snap=args.snap,
        limit=args.limit,
        ignore_id=args.ignore_id,
    )
    result = {"slideId": args.slide_id, "width": args.width, "height": args.height, "placements": rows}
    if args.json:
        emit(result, True)
        return
    print(f"Slide {args.slide_id} free placements for {args.width}x{args.height} near={args.near}:")
    if not rows:
        print("  no free placement found")
    for i, row in enumerate(rows, start=1):
        b = row["bbox"]
        print(f"  {i}. xy=({int(b['x'])},{int(b['y'])}) size={int(b['width'])}x{int(b['height'])} score={row['score']}")


def cmd_validate(args: argparse.Namespace) -> None:
    data = get_all(args)
    slides = data.get("slides", [])
    if args.all:
        targets = slides
    else:
        targets = [get_slide(data, args.slide_id)]
    reports = [validate_slide(slide) for slide in targets]
    ok = all(report["ok"] for report in reports)
    if args.json:
        emit({"ok": ok, "slides": reports}, True)
    else:
        for report in reports:
            print(f"Slide {report['slideId']}: errors={len(report['errors'])} warnings={len(report['warnings'])}")
            for item in report["errors"] + report["warnings"]:
                print(f"  ! {item['kind']}: {item.get('id') or item.get('ids')} {item['message']}")
    if not ok:
        raise SystemExit(2)


def cmd_add(args: argparse.Namespace) -> None:
    html_file = getattr(args, "html_file", "")
    css_file = getattr(args, "css_file", "")
    if html_file:
        if args.html:
            fail("--html 和 --html-file 不能同时使用")
        args.html = read_text_file(html_file)
    if css_file:
        if args.css:
            fail("--css 和 --css-file 不能同时使用")
        args.css = read_text_file(css_file)
    if getattr(args, "auto_place", False):
        slide = get_slide(get_all(args), args.slide_id)
        placement = choose_free_placement(
            slide,
            args.width,
            args.height,
            near=args.near,
            gap=args.gap,
            margin=args.margin,
            snap=args.snap,
        )
        args.x = int(placement["bbox"]["x"])
        args.y = int(placement["bbox"]["y"])
        args.center_h = False
        args.center_v = False
    element = build_element(args)
    body: dict[str, Any] = {"element": element}
    if args.index is not None:
        body["index"] = args.index
    emit(api(args, "POST", f"/api/slides/{args.slide_id}/elements", body), args.json)


def cmd_update(args: argparse.Namespace) -> None:
    props = parse_properties(args.properties)
    updated = api(args, "PUT", f"/api/slides/{args.slide_id}/elements/{args.elem_id}", {"properties": props})
    result: dict[str, Any] = {"updated": updated}
    if args.preview:
        result["preview"] = export_preview(args, args.slide_id)
    emit(result, args.json)


def cmd_delete(args: argparse.Namespace) -> None:
    emit(api(args, "DELETE", f"/api/slides/{args.slide_id}/elements/{args.elem_id}"), args.json)


def cmd_move(args: argparse.Namespace) -> None:
    """按绝对值或相对值移动/缩放元素，并支持画布对齐。"""
    slide = get_slide(get_all(args), args.slide_id)
    _, elem = find_element(slide, args.elem_id)
    bbox = element_bbox(elem)
    x = float(args.x) if args.x is not None else bbox["x"]
    y = float(args.y) if args.y is not None else bbox["y"]
    width = float(args.width) if args.width is not None else bbox["width"]
    height = float(args.height) if args.height is not None else bbox["height"]

    x += args.dx
    y += args.dy
    width += args.dw
    height += args.dh
    width = max(1, width)
    height = max(1, height)

    for align in args.align or []:
        if align == "left":
            x = 0
        elif align == "right":
            x = CANVAS_W - width
        elif align == "top":
            y = 0
        elif align == "bottom":
            y = CANVAS_H - height
        elif align == "center-h":
            x = (CANVAS_W - width) / 2
        elif align == "center-v":
            y = (CANVAS_H - height) / 2

    if args.snap and args.snap > 1:
        grid = args.snap
        x = round(x / grid) * grid
        y = round(y / grid) * grid
        width = max(1, round(width / grid) * grid)
        height = max(1, round(height / grid) * grid)

    if args.clamp:
        width = min(width, CANVAS_W)
        height = min(height, CANVAS_H)
        x = min(max(0, x), CANVAS_W - width)
        y = min(max(0, y), CANVAS_H - height)

    props = {
        "x": int(round(x)),
        "y": int(round(y)),
        "width": int(round(width)),
        "height": int(round(height)),
    }
    result = {
        "before": {"x": bbox["x"], "y": bbox["y"], "width": bbox["width"], "height": bbox["height"]},
        "after": props,
    }
    if args.dry_run:
        emit(result, args.json)
        return
    updated = api(args, "PUT", f"/api/slides/{args.slide_id}/elements/{args.elem_id}", {"properties": props})
    output: dict[str, Any] = {"move": result, "updated": updated}
    if args.preview:
        output["preview"] = export_preview(args, args.slide_id)
    emit(output, args.json)


def cmd_batch(args: argparse.Namespace) -> None:
    ops_path = resolve_input_path(args.ops, allow_at_prefix=True)
    with ops_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    operations = normalize_batch_operations(payload)
    if args.normalize:
        operations = normalize_batch_for_agent(operations)
    if args.dry_run:
        emit({"operations": operations}, args.json)
        return
    emit(api(args, "POST", f"/api/slides/{args.slide_id}/elements/batch", {"operations": operations}), args.json)


def cmd_measure_text(args: argparse.Namespace) -> None:
    """估算文本在指定宽度内的推荐高度。"""
    text = args.text
    if args.text_file:
        text = read_text_file(args.text_file)
    elem = {
        "type": "text",
        "text": text,
        "width": args.width,
        "fontSize": args.font_size,
        "lineHeight": args.line_height,
    }
    metrics = estimate_text_metrics(elem)
    recommended_height = max(1, int(round(metrics["estimatedHeight"] + args.padding)))
    result = {
        "textLength": len(text),
        "width": args.width,
        "fontSize": args.font_size,
        "lineHeight": args.line_height,
        "padding": args.padding,
        "visualLines": int(metrics["visualLines"]),
        "estimatedHeight": metrics["estimatedHeight"],
        "recommendedHeight": recommended_height,
        "maxUnbreakableWidth": metrics["maxUnbreakableWidth"],
        "overflowRisk": metrics["maxUnbreakableWidth"] > args.width + 4,
    }
    emit(result, args.json)


def cmd_upload(args: argparse.Namespace) -> None:
    results = []
    for file in args.files:
        result = upload_file(args, file)
        results.append({"file": file, **result})
    emit(results, args.json)


def cmd_upload_place(args: argparse.Namespace) -> None:
    files = args.files
    uploads = []
    operations = []
    cols = len(files) if args.layout == "row" else max(1, int((len(files) - 1) ** 0.5) + 1)
    if args.layout == "single" and len(files) > 1:
        fail("单图布局只接受 1 个文件；多图请使用 --layout row 或 --layout grid")
    origin_x = args.x
    origin_y = args.y
    if len(files) > 1:
        rows = (len(files) + cols - 1) // cols
        group_w = cols * args.width + (cols - 1) * args.gap
        group_h = rows * args.height + (rows - 1) * args.gap
        if getattr(args, "auto_place", False):
            slide = get_slide(get_all(args), args.slide_id)
            placement = choose_free_placement(
                slide,
                group_w,
                group_h,
                near=args.near,
                gap=args.gap,
                margin=args.margin,
                snap=args.snap,
            )
            origin_x = int(placement["bbox"]["x"])
            origin_y = int(placement["bbox"]["y"])
            args.center_h = False
            args.center_v = False
        if args.center_h:
            origin_x = (CANVAS_W - group_w) // 2
        if args.center_v:
            origin_y = (CANVAS_H - group_h) // 2
    elif getattr(args, "auto_place", False):
        slide = get_slide(get_all(args), args.slide_id)
        placement = choose_free_placement(
            slide,
            args.width,
            args.height,
            near=args.near,
            gap=args.gap,
            margin=args.margin,
            snap=args.snap,
        )
        origin_x = int(placement["bbox"]["x"])
        origin_y = int(placement["bbox"]["y"])
        args.x = origin_x
        args.y = origin_y
        args.center_h = False
        args.center_v = False
    for i, file in enumerate(files):
        upload = upload_file(args, file)
        src = upload.get("url")
        if not src:
            fail(f"上传接口未返回 url: {upload}")
        add_args = argparse.Namespace(**vars(args))
        add_args.type = "image"
        add_args.src = src
        if len(files) > 1:
            col = i % cols
            row = i // cols
            add_args.x = origin_x + col * (args.width + args.gap)
            add_args.y = origin_y + row * (args.height + args.gap)
            add_args.center_h = False
            add_args.center_v = False
            if args.id:
                add_args.id = f"{args.id}-{i + 1}"
        element = build_element(add_args)
        operation: dict[str, Any] = {"action": "add", "element": element}
        if args.index is not None:
            operation["index"] = args.index + i
        operations.append(operation)
        uploads.append({"file": file, **upload})
    if len(operations) == 1:
        body = {"element": operations[0]["element"]}
        if args.index is not None:
            body["index"] = args.index
        created = api(args, "POST", f"/api/slides/{args.slide_id}/elements", body)
        result = {"uploads": uploads, "created": created}
    else:
        created = api(args, "POST", f"/api/slides/{args.slide_id}/elements/batch", {"operations": operations})
        result = {"uploads": uploads, "layout": args.layout, "created": created}
    if args.preview:
        result["preview"] = export_preview(args, args.slide_id)
    emit(result, args.json)


def cmd_place(args: argparse.Namespace) -> None:
    """上传图片并放入已有占位槽或图片元素的 bbox。"""
    data = get_all(args)
    slide = get_slide(data, args.slide_id)
    target_index, target = find_element(slide, args.elem_id)
    bbox = element_bbox(target)
    upload = upload_file(args, args.file)
    src = upload.get("url")
    if not src:
        fail(f"上传接口未返回 url: {upload}")

    clip_type = args.clip_type or target.get("clipType") or "rect"
    rx = args.rx if args.rx is not None else int(target.get("rx", 0) or 0)
    meta = target.get("meta") if isinstance(target.get("meta"), dict) else {}
    image_element = {
        "type": "image",
        "x": int(bbox["x"]),
        "y": int(bbox["y"]),
        "width": int(bbox["width"]),
        "height": int(bbox["height"]),
        "angle": target.get("angle", 0) or 0,
        "opacity": target.get("opacity", 1) if target.get("opacity", None) is not None else 1,
        "locked": bool(target.get("locked", False)),
        "src": src,
        "clipType": clip_type,
        "rx": rx,
        "meta": {**meta, "role": args.role or "image", "replacedPlaceholder": target.get("id", "")},
    }

    if target.get("type") == "image" and not args.replace and not args.add_only:
        props = {"src": src, "clipType": clip_type, "rx": rx}
        updated = api(args, "PUT", f"/api/slides/{args.slide_id}/elements/{args.elem_id}", {"properties": props})
        output = {"upload": upload, "mode": "update-image", "target": args.elem_id, "updated": updated}
        if args.preview:
            output["preview"] = export_preview(args, args.slide_id)
        emit(output, args.json)
        return

    operations: list[dict[str, Any]] = []
    if not args.add_only:
        operations.append({"action": "delete", "id": args.elem_id})
    insert_index = target_index + 1 if args.add_only else target_index
    operations.append({"action": "add", "index": insert_index, "element": image_element})
    result = api(args, "POST", f"/api/slides/{args.slide_id}/elements/batch", {"operations": operations})
    output = {"upload": upload, "mode": "replace-slot" if not args.add_only else "add-over-slot", "bbox": bbox, "result": result}
    if args.preview:
        output["preview"] = export_preview(args, args.slide_id)
    emit(output, args.json)


def cmd_autofit(args: argparse.Namespace) -> None:
    """按估算文本高度自动修正文本框高度，必要时缩小字号。"""
    slide = get_slide(get_all(args), args.slide_id)
    _, elem = find_element(slide, args.elem_id)
    if elem.get("type") != "text":
        fail("autofit 只支持 text 元素")
    bbox = element_bbox(elem)
    font_size = int(elem.get("fontSize", 18) or 18)
    props: dict[str, Any] = {}

    metrics = estimate_text_metrics(elem)
    needed_height = int(round(metrics["estimatedHeight"] + args.padding))
    available_height = max(1, CANVAS_H - int(bbox["y"]))
    if needed_height <= available_height:
        props["height"] = max(int(bbox["height"]), needed_height)
    elif args.shrink:
        trial = dict(elem)
        while font_size > args.min_font:
            font_size -= 1
            trial["fontSize"] = font_size
            metrics = estimate_text_metrics(trial)
            needed_height = int(round(metrics["estimatedHeight"] + args.padding))
            if needed_height <= available_height:
                break
        props["fontSize"] = font_size
        props["height"] = min(available_height, max(1, needed_height))
    else:
        props["height"] = available_height

    result = {
        "before": {"fontSize": elem.get("fontSize", 18), "height": bbox["height"]},
        "after": props,
        "estimated": metrics,
    }
    if args.dry_run:
        emit(result, args.json)
        return
    updated = api(args, "PUT", f"/api/slides/{args.slide_id}/elements/{args.elem_id}", {"properties": props})
    output = {"autofit": result, "updated": updated}
    if args.preview:
        output["preview"] = export_preview(args, args.slide_id)
    emit(output, args.json)


def cmd_fix_overlaps(args: argparse.Namespace) -> None:
    """为非刻意重叠元素生成移动建议，必要时批量应用。"""
    slide = get_slide(get_all(args), args.slide_id)
    elements = slide.get("canvas_elements", []) or []
    warnings = find_overlaps(elements)
    suggestions = []
    planned_updates: list[dict[str, Any]] = []
    virtual_slide = json.loads(json.dumps(slide, ensure_ascii=False))

    for warning in warnings:
        ids = warning.get("ids") or []
        if len(ids) < 2:
            continue
        elem_id = str(ids[1])
        try:
            elem_index, elem = find_element(virtual_slide, elem_id)
        except SystemExit:
            continue
        bbox = element_bbox(elem)
        if args.axis in {"x", "y"}:
            placement = choose_axis_constrained_placement(
                virtual_slide,
                bbox,
                axis=args.axis,
                gap=args.gap,
                margin=args.margin,
                snap=args.snap,
                ignore_id=elem_id,
            )
            if placement is None:
                suggestions.append({
                    "id": elem_id,
                    "from": {"x": bbox["x"], "y": bbox["y"], "width": bbox["width"], "height": bbox["height"]},
                    "to": None,
                    "reason": f"{warning['message']}；按 {args.axis} 轴锁定未找到无重叠位置",
                    "skipped": True,
                })
                continue
        else:
            placement = choose_free_placement(
                virtual_slide,
                int(bbox["width"]),
                int(bbox["height"]),
                near=args.near,
                gap=args.gap,
                margin=args.margin,
                snap=args.snap,
                ignore_id=elem_id,
            )
        new_bbox = placement["bbox"]
        props = {"x": int(new_bbox["x"]), "y": int(new_bbox["y"])}
        shift = abs(props["x"] - int(bbox["x"])) + abs(props["y"] - int(bbox["y"]))
        if args.max_shift is not None and shift > args.max_shift:
            suggestions.append({
                "id": elem_id,
                "from": {"x": bbox["x"], "y": bbox["y"], "width": bbox["width"], "height": bbox["height"]},
                "to": props,
                "reason": f"{warning['message']}；建议位移 {shift}px 超过 --max-shift {args.max_shift}px，未应用",
                "skipped": True,
            })
            continue
        virtual_slide["canvas_elements"][elem_index].update(props)
        suggestions.append({
            "id": elem_id,
            "from": {"x": bbox["x"], "y": bbox["y"], "width": bbox["width"], "height": bbox["height"]},
            "to": props,
            "reason": warning["message"],
            "shift": shift,
        })
        planned_updates.append({"action": "update", "id": elem_id, "properties": props})

    result: dict[str, Any] = {"slideId": args.slide_id, "overlaps": len(warnings), "suggestions": suggestions}
    if args.apply and planned_updates:
        result["result"] = api(args, "POST", f"/api/slides/{args.slide_id}/elements/batch", {"operations": planned_updates})
        if args.preview:
            result["preview"] = export_preview(args, args.slide_id)

    if args.json:
        emit(result, True)
        return
    print(f"Slide {args.slide_id} overlaps={len(warnings)} suggestions={len(suggestions)}")
    for item in suggestions:
        src = item["from"]
        dst = item["to"]
        if dst is None:
            print(f"  {item['id']}: skipped  {item['reason']}")
        else:
            suffix = " skipped" if item.get("skipped") else ""
            print(f"  {item['id']}: ({int(src['x'])},{int(src['y'])}) -> ({dst['x']},{dst['y']}){suffix}  {item['reason']}")
    if args.apply:
        print("  applied" if planned_updates else "  nothing to apply")


def cmd_component_list(args: argparse.Namespace) -> None:
    rows = [{"name": name, "description": description} for name, description in COMPONENT_HELP.items()]
    emit(rows, args.json)


def cmd_component_render(args: argparse.Namespace) -> None:
    data = read_component_data(args.data)
    try:
        rendered = render_registered_component(args.name, data)
    except KeyError:
        fail(f"未知组件: {args.name}，可用组件: {', '.join(COMPONENT_HELP)}")
    except ValueError as exc:
        fail(str(exc))
    emit(rendered, args.json)


def cmd_component_add(args: argparse.Namespace) -> None:
    data = read_component_data(args.data)
    try:
        rendered = render_registered_component(args.name, data)
    except KeyError:
        fail(f"未知组件: {args.name}，可用组件: {', '.join(COMPONENT_HELP)}")
    except ValueError as exc:
        fail(str(exc))
    add_args = argparse.Namespace(**vars(args))
    add_args.type = "html"
    add_args.html = rendered["html"]
    add_args.css = rendered["css"]
    add_args.src = ""
    add_args.clip_type = "rect"
    add_args.rx = 0
    add_args.ry = 0
    element = build_element(add_args)
    meta = element.setdefault("meta", {})
    if isinstance(meta, dict):
        meta.setdefault("role", "html")
        meta.setdefault("component", args.name)
    body: dict[str, Any] = {"element": element}
    if args.index is not None:
        body["index"] = args.index
    emit(api(args, "POST", f"/api/slides/{args.slide_id}/elements", body), args.json)


def cmd_create_slide(args: argparse.Namespace) -> None:
    slide: dict[str, Any] = {}
    if args.bg:
        slide["backgroundColor"] = args.bg
    if args.theme:
        slide["theme"] = args.theme
    if args.layout:
        slide["layout"] = args.layout
    if args.bg_pattern_color:
        slide["bgPatternColor"] = args.bg_pattern_color
    body: dict[str, Any] = {"slide": slide}
    if args.index != -1:
        body["index"] = args.index
    emit(api(args, "POST", "/api/slides/create", body), args.json)


def cmd_update_slide(args: argparse.Namespace) -> None:
    data = get_all(args)
    slide = get_slide(data, args.slide_id)
    if args.layout is not None:
        slide["layout"] = args.layout
    if args.theme is not None:
        slide["theme"] = args.theme
    if args.bg is not None:
        slide["backgroundColor"] = args.bg
    if args.bg_pattern_color is not None:
        slide["bgPatternColor"] = args.bg_pattern_color
    emit(api(args, "PUT", f"/api/slides/{args.slide_id}", slide), args.json)


def cmd_delete_slide(args: argparse.Namespace) -> None:
    emit(api(args, "DELETE", f"/api/slides/{args.slide_id}"), args.json)


def cmd_export(args: argparse.Namespace) -> None:
    emit(api(args, "GET", "/api/export"), args.json)


def cmd_workspace_list(args: argparse.Namespace) -> None:
    """列出服务端工作区。"""
    result = api(args, "GET", "/api/workspaces")
    if args.json:
        result["cli_default"] = args.workspace
        emit(result, True)
        return
    print(f"Current workspace: {result.get('current')}")
    print(f"CLI default workspace: {args.workspace}")
    for ws in result.get("workspaces", []):
        marker = "*" if ws.get("id") == result.get("current") else " "
        print(f"{marker} {ws.get('id')}  {ws.get('name', '')}")


def cmd_workspace_select(args: argparse.Namespace) -> None:
    """把常用工作区写入本地 CLI 会话配置。"""
    path = session_path()
    data = read_session()
    data["workspace"] = args.workspace_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"status": "ok", "workspace": args.workspace_id, "session": str(path)}
    emit(result, args.json)


def cmd_workspace_create(args: argparse.Namespace) -> None:
    """创建工作区。"""
    name = args.name or args.workspace_id
    emit(api(args, "POST", "/api/workspaces", {"id": args.workspace_id, "name": name}), args.json)


def cmd_workspace_rename(args: argparse.Namespace) -> None:
    """重命名工作区。"""
    emit(api(args, "PUT", f"/api/workspaces/{args.workspace_id}", {"name": args.name}), args.json)


def cmd_workspace_delete(args: argparse.Namespace) -> None:
    """删除工作区。"""
    emit(api(args, "DELETE", f"/api/workspaces/{args.workspace_id}"), args.json)


def find_chrome_or_edge() -> str | None:
    """跨平台寻找 Chrome 或 Edge 浏览器的执行路径（Windows/macOS/Linux）。"""
    import shutil
    if sys.platform == "win32":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return None
    elif sys.platform == "darwin":
        mac_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in mac_paths:
            if os.path.exists(p):
                return p
        return None
    else:
        # Linux / 其他 Unix：用 which 探测
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "microsoft-edge-stable"):
            found = shutil.which(name)
            if found:
                return found
        return None


def cmd_export_image(args: argparse.Namespace) -> None:
    result = export_slide_image(args, args.slide_id, args.output, announce=not args.json)
    emit(result, args.json)


def export_preview(args: argparse.Namespace, slide_id: str) -> dict[str, Any]:
    """导出当前页预览图并返回文件信息。"""
    return export_slide_image(args, slide_id, "", announce=False)


def export_slide_image(args: argparse.Namespace, slide_id: str, output_path: str = "", announce: bool = False) -> dict[str, Any]:
    """用无头浏览器把单页幻灯片导出为 PNG。"""
    browser = find_chrome_or_edge()
    if not browser:
        fail("未能找到 Google Chrome 或 Microsoft Edge 浏览器，无法导出图片。请安装 Chrome/Edge/Chromium 后重试。")

    slides_image_dir = project_root() / "data" / "workspaces" / args.workspace / "slides_image"
    slides_image_dir.mkdir(parents=True, exist_ok=True)

    if not output_path:
        out_path_obj = slides_image_dir / f"slide_{slide_id}.png"
    else:
        expanded = os.path.expandvars(os.path.expanduser(output_path))
        out_path_obj = Path(expanded)
        if not out_path_obj.is_absolute():
            out_path_obj = (slides_image_dir / out_path_obj).resolve()

    out_path_obj.parent.mkdir(parents=True, exist_ok=True)

    url = f"{args.base.rstrip('/')}{with_workspace(args, f'/slide/{slide_id}')}"

    import subprocess
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--window-size=960,540",
        f"--screenshot={out_path_obj}",
        "--virtual-time-budget=3000",
        url,
    ]

    if announce:
        print(f"正在启动浏览器导出幻灯片 {slide_id} 到 {out_path_obj}...")

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30)
        if res.returncode != 0:
            fail(f"浏览器截图进程返回非0错误码({res.returncode}): {res.stderr or res.stdout}")

        if not out_path_obj.exists() or out_path_obj.stat().st_size == 0:
            fail("浏览器截图文件未生成或文件大小为0。")

        return {
            "status": "ok",
            "workspace": args.workspace,
            "slide_id": slide_id,
            "output_path": str(out_path_obj),
            "size_bytes": out_path_obj.stat().st_size,
        }
    except subprocess.TimeoutExpired:
        fail("浏览器导出截图超时。")
    except Exception as exc:
        fail(f"导出截图失败: {exc}")


def image_content_bounds(image: Any, threshold: int = 18) -> dict[str, Any]:
    """按四角背景色估算非背景内容边界。"""
    rgb = image.convert("RGB")
    width, height = rgb.size
    corner_points = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    bg = tuple(sum(rgb.getpixel(point)[i] for point in corner_points) // 4 for i in range(3))
    pixels = rgb.load()
    min_x, min_y = width, height
    max_x, max_y = -1, -1
    count = 0
    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            diff = sum(abs(pixel[i] - bg[i]) for i in range(3))
            if diff > threshold:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                count += 1
    if max_x < min_x or max_y < min_y:
        return {"x": 0, "y": 0, "width": 0, "height": 0, "right": 0, "bottom": 0, "coverage": 0.0, "background": bg}
    return {
        "x": min_x,
        "y": min_y,
        "width": max_x - min_x + 1,
        "height": max_y - min_y + 1,
        "right": max_x + 1,
        "bottom": max_y + 1,
        "coverage": round(count / (width * height), 4),
        "background": bg,
    }


def image_difference_summary(current: Any, reference: Any) -> dict[str, Any]:
    """把当前图缩放到参考图尺寸后计算像素差异摘要。"""
    from PIL import ImageChops, ImageStat

    current_rgb = current.convert("RGB")
    reference_rgb = reference.convert("RGB")
    if current_rgb.size != reference_rgb.size:
        current_rgb = current_rgb.resize(reference_rgb.size)
    diff = ImageChops.difference(current_rgb, reference_rgb)
    stat = ImageStat.Stat(diff)
    mean = sum(stat.mean) / 3
    extrema = diff.getextrema()
    max_channel = max(channel[1] for channel in extrema)
    changed = 0
    pixels = diff.load()
    width, height = diff.size
    for y in range(height):
        for x in range(width):
            if sum(pixels[x, y]) > 45:
                changed += 1
    return {
        "resizedCurrentTo": {"width": width, "height": height},
        "meanAbsDiff": round(mean, 2),
        "maxChannelDiff": max_channel,
        "changedPixelRatio": round(changed / (width * height), 4),
    }


def cmd_compare_image(args: argparse.Namespace) -> None:
    """对比当前导出图和参考截图，输出还原偏差指标。"""
    try:
        from PIL import Image
    except ImportError:
        fail("compare-image 需要 Pillow，请先安装 requirements.txt 中的 Pillow。")

    reference_path = resolve_input_path(args.reference)
    if args.current:
        current_path = resolve_input_path(args.current)
        export_result = None
    elif args.export_current:
        export_result = export_slide_image(args, args.slide_id, args.output, announce=not args.json)
        current_path = Path(export_result["output_path"])
    else:
        current_path = project_root() / "data" / "workspaces" / args.workspace / "slides_image" / f"slide_{args.slide_id}.png"
        export_result = None
        if not current_path.exists():
            fail(f"当前页截图不存在: {current_path}；请加 --export-current 先导出")

    with Image.open(current_path) as current_image, Image.open(reference_path) as reference_image:
        current_bounds = image_content_bounds(current_image, threshold=args.threshold)
        reference_bounds = image_content_bounds(reference_image, threshold=args.threshold)
        diff = image_difference_summary(current_image, reference_image)
        scale_x = current_image.width / reference_image.width
        scale_y = current_image.height / reference_image.height
        mapped_reference = {
            "x": round(reference_bounds["x"] * scale_x, 2),
            "y": round(reference_bounds["y"] * scale_y, 2),
            "width": round(reference_bounds["width"] * scale_x, 2),
            "height": round(reference_bounds["height"] * scale_y, 2),
        }
        result = {
            "slideId": args.slide_id,
            "current": {
                "path": str(current_path),
                "size": {"width": current_image.width, "height": current_image.height},
                "contentBounds": current_bounds,
            },
            "reference": {
                "path": str(reference_path),
                "size": {"width": reference_image.width, "height": reference_image.height},
                "contentBounds": reference_bounds,
                "mappedToCurrentCanvas": mapped_reference,
            },
            "layoutDelta": {
                "contentX": round(current_bounds["x"] - mapped_reference["x"], 2),
                "contentY": round(current_bounds["y"] - mapped_reference["y"], 2),
                "contentWidth": round(current_bounds["width"] - mapped_reference["width"], 2),
                "contentHeight": round(current_bounds["height"] - mapped_reference["height"], 2),
            },
            "pixelDiff": diff,
        }
        if export_result:
            result["export"] = export_result
    emit(result, args.json)


def add_common_element_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", default="", help="元素 ID；为空时由后端生成")
    parser.add_argument("--x", type=int, default=0, help="左上角 x；--center-h 开启时被覆盖")
    parser.add_argument("--y", type=int, default=0, help="左上角 y；--center-v 开启时被覆盖")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--center-h", action="store_true", help="水平居中 x = (960 - width) / 2")
    parser.add_argument("--center-v", action="store_true", help="垂直居中 y = (540 - height) / 2")
    parser.add_argument("--angle", type=int, default=0)
    parser.add_argument("--opacity", type=float, default=1)
    parser.add_argument("--locked", action="store_true")
    parser.add_argument("--meta", "-m", action="append", default=[], help="元信息，如 role=title 或 allowOverlap=true")
    parser.add_argument("--index", type=int, default=None, help="插入层级；默认追加到最上层")


def add_auto_place_args(parser: argparse.ArgumentParser) -> None:
    """增加自动找空位相关参数。"""
    parser.add_argument("--auto-place", action="store_true", help="自动选择无重叠空位，覆盖 --x/--y/--center-*")
    parser.add_argument("--near", choices=["top", "bottom", "left", "right", "center", "middle"], default="center", help="自动放置偏好区域")
    parser.add_argument("--gap", type=int, default=12, help="自动放置与多图布局间距")
    parser.add_argument("--margin", type=int, default=40, help="自动放置画布边距")
    parser.add_argument("--snap", type=int, default=4, help="自动放置网格吸附")


def add_slide_index_arg(parser: argparse.ArgumentParser) -> None:
    """增加 0 基页序号定位参数。"""
    parser.add_argument("--slide-index", type=int, default=None, help="按 0 基页序号选择幻灯片，-1 表示最后一页")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EVKIT2 幻灯片 Agent 编辑工具")
    parser.add_argument("--base", default=DEFAULT_BASE, help="API 基地址，默认 http://127.0.0.1:5001")
    parser.add_argument("--workspace", default=default_workspace(), help="目标工作区 ID，默认读取 SLIDE_WORKSPACE、workspace select 或 default")
    parser.add_argument("--timeout", type=int, default=15, help="请求超时秒数")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("workspace", help="管理工作区")
    workspace_sub = p.add_subparsers(dest="workspace_command", required=True)
    wp = workspace_sub.add_parser("list", help="列出工作区")
    wp.add_argument("--json", action="store_true")
    wp.set_defaults(func=cmd_workspace_list)
    wp = workspace_sub.add_parser("select", help="设置后续 CLI 默认工作区")
    wp.add_argument("workspace_id")
    wp.add_argument("--json", action="store_true")
    wp.set_defaults(func=cmd_workspace_select)
    wp = workspace_sub.add_parser("create", help="创建工作区")
    wp.add_argument("workspace_id")
    wp.add_argument("--name", default="", help="工作区显示名称")
    wp.add_argument("--json", action="store_true")
    wp.set_defaults(func=cmd_workspace_create)
    wp = workspace_sub.add_parser("rename", help="重命名工作区")
    wp.add_argument("workspace_id")
    wp.add_argument("--name", required=True, help="新的显示名称")
    wp.add_argument("--json", action="store_true")
    wp.set_defaults(func=cmd_workspace_rename)
    wp = workspace_sub.add_parser("delete", help="删除工作区")
    wp.add_argument("workspace_id")
    wp.add_argument("--json", action="store_true")
    wp.set_defaults(func=cmd_workspace_delete)

    p = sub.add_parser("status", help="检查服务、版本、页数和元素数")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("assets", help="列出模板可用字体、图标、CSS token 和本地素材")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_assets)

    p = sub.add_parser("list", help="列出所有幻灯片摘要")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("overview", aliases=["brief"], help="一次性查看页面、元素、占位槽和风险摘要")
    p.add_argument("--slide", default="", help="只查看指定幻灯片；省略时查看全局")
    add_slide_index_arg(p)
    p.add_argument("--elements", action="store_true", help="全局模式下也输出元素摘要")
    p.add_argument("--limit", type=int, default=14, help="每页最多输出多少个元素摘要")
    p.add_argument("--warnings", action="store_true", help="附带 validate 风险计数和明细")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_overview)

    p = sub.add_parser("inspect", aliases=["view"], help="查看单页元素 bbox、层级和告警")
    p.add_argument("slide_id", nargs="?")
    add_slide_index_arg(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--overlaps", action="store_true", help="检查非刻意重叠")
    p.add_argument("--ascii", action="store_true", help="附加输出 ASCII 线框图，元素首字母按 a/b/c 顺序标注")
    p.add_argument("--summary", action="store_true", help="只输出关键 ID、位置和层级，便于快速定位")
    p.add_argument("--warnings", action="store_true", help="summary 模式下也输出告警；普通模式默认输出告警")
    p.add_argument("--cols", type=int, default=80, help="ASCII 线框图列数（含边框），默认 80")
    p.add_argument("--rows", type=int, default=24, help="ASCII 线框图行数（含边框），默认 24")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("find", help="按文本、id 或类型定位元素")
    p.add_argument("--text", default="")
    p.add_argument("--id", default="")
    p.add_argument("--type", choices=["text", "image", "rect", "circle", "triangle", "polygon", "html", "3d"], default="")
    p.add_argument("--role", default="", help="按 meta.role 精确匹配，如 title/body/image/placeholder")
    p.add_argument("--near", choices=["top", "bottom", "left", "right", "center", "middle"], default="", help="按画布大致区域过滤")
    p.add_argument("--slide", default="")
    add_slide_index_arg(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("slots", help="列出可填充/替换的占位槽")
    p.add_argument("--slide", default="", help="只查看指定幻灯片")
    add_slide_index_arg(p)
    p.add_argument("--kind", choices=["any", "image", "text"], default="any")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_slots)

    p = sub.add_parser("space", help="查找指定尺寸的无重叠空位")
    p.add_argument("slide_id", nargs="?")
    add_slide_index_arg(p)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--near", choices=["top", "bottom", "left", "right", "center", "middle"], default="center")
    p.add_argument("--gap", type=int, default=12, help="与已有主要元素保持的最小安全间距")
    p.add_argument("--margin", type=int, default=40, help="画布边距")
    p.add_argument("--snap", type=int, default=4, help="网格吸附")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--ignore-id", default="", help="计算空位时忽略指定元素，常用于移动该元素")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_space)

    p = sub.add_parser("validate", help="校验结构、越界、溢出和重叠")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("slide_id", nargs="?")
    target.add_argument("--slide-index", type=int, default=None, help="按 0 基页序号选择幻灯片，-1 表示最后一页")
    target.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("add", help="添加元素")
    p.add_argument("slide_id")
    p.add_argument("--type", required=True, choices=["text", "image", "rect", "circle", "triangle", "polygon", "html", "3d"])
    add_common_element_args(p)
    p.add_argument("--text", default="")
    p.add_argument("--font-size", type=int, default=18)
    p.add_argument("--font-family", default="")
    p.add_argument("--font-weight", default="")
    p.add_argument("--line-height", type=float, default=None)
    p.add_argument("--text-align", default="")
    p.add_argument("--fill", default="")
    p.add_argument("--stroke", default="")
    p.add_argument("--stroke-width", type=int, default=0)
    p.add_argument("--src", default="")
    p.add_argument("--clip-type", default="rect", choices=["rect", "circle", "rounded-rect"])
    p.add_argument("--rx", type=int, default=0)
    p.add_argument("--ry", type=int, default=0)
    p.add_argument("--html", default="")
    p.add_argument("--css", default="")
    p.add_argument("--html-file", default="", help="从文件读取 HTML，避免 shell 转义。和 --html 互斥")
    p.add_argument("--css-file", default="", help="从文件读取 CSS，避免 shell 转义。和 --css 互斥")
    # 3D 元素参数（--type 3d 时使用）
    p.add_argument("--geometry", default="cube", choices=["cube", "sphere", "torus", "cylinder", "cone", "icosahedron", "particles", "custom"])
    p.add_argument("--auto-rotate", dest="auto_rotate", action="store_true", default=True)
    p.add_argument("--no-auto-rotate", dest="auto_rotate", action="store_false")
    p.add_argument("--rotate-speed", type=float, default=0.01)
    p.add_argument("--metalness", type=float, default=0.4)
    p.add_argument("--roughness", type=float, default=0.4)
    p.add_argument("--wireframe", action="store_true", default=False)
    p.add_argument("--bg", default="transparent", help="3D 背景色（transparent 或 #RRGGBB）")
    p.add_argument("--custom-code", default="", help="自定义 Three.js 场景完整 HTML 代码（仅 --geometry custom 时使用）")
    p.add_argument("--custom-file", default="", help="从文件读取自定义 Three.js 场景代码（与 --custom-code 互斥）")
    add_auto_place_args(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="更新元素属性")
    p.add_argument("slide_id")
    p.add_argument("elem_id")
    p.add_argument("--property", "-p", action="append", dest="properties", required=True)
    p.add_argument("--preview", action="store_true", help="修改成功后自动导出当前页预览图")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="删除元素")
    p.add_argument("slide_id")
    p.add_argument("elem_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("move", help="移动、缩放、对齐元素，减少手算坐标")
    p.add_argument("slide_id")
    p.add_argument("elem_id")
    p.add_argument("--x", type=int, default=None)
    p.add_argument("--y", type=int, default=None)
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--dx", type=int, default=0)
    p.add_argument("--dy", type=int, default=0)
    p.add_argument("--dw", type=int, default=0)
    p.add_argument("--dh", type=int, default=0)
    p.add_argument("--align", action="append", choices=["left", "right", "top", "bottom", "center-h", "center-v"], default=[])
    p.add_argument("--snap", type=int, default=0, help="按网格吸附 x/y/width/height，例如 8")
    p.add_argument("--clamp", action="store_true", help="把元素限制在 960x540 画布内")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--preview", action="store_true", help="修改成功后自动导出当前页预览图")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("autofit", help="自动修正文本框高度，必要时缩小字号")
    p.add_argument("slide_id")
    p.add_argument("elem_id")
    p.add_argument("--padding", type=int, default=4)
    p.add_argument("--shrink", action="store_true", help="高度不够时缩小字号")
    p.add_argument("--min-font", type=int, default=10)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--preview", action="store_true", help="修改成功后自动导出当前页预览图")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_autofit)

    p = sub.add_parser("measure-text", help="估算文本在指定宽度内的推荐高度")
    p.add_argument("--text", default="", help="要测量的文本；可配合 --text-file 使用")
    p.add_argument("--text-file", default="", help="从文件读取文本")
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--font-size", type=int, default=18)
    p.add_argument("--line-height", type=float, default=1.4)
    p.add_argument("--padding", type=int, default=4)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_measure_text)

    p = sub.add_parser("fix-overlaps", help="为非刻意重叠元素生成移动建议，必要时应用")
    p.add_argument("slide_id", nargs="?")
    add_slide_index_arg(p)
    p.add_argument("--near", choices=["top", "bottom", "left", "right", "center", "middle"], default="center")
    p.add_argument("--gap", type=int, default=12)
    p.add_argument("--margin", type=int, default=40)
    p.add_argument("--snap", type=int, default=4)
    p.add_argument("--axis", choices=["x", "y", "both"], default="both", help="限制修复位移轴；截图还原建议 y")
    p.add_argument("--max-shift", type=int, default=None, help="建议位移超过该像素值时只报告不应用")
    p.add_argument("--apply", action="store_true", help="应用建议；不加时只预览")
    p.add_argument("--preview", action="store_true", help="应用成功后自动导出当前页预览图")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_fix_overlaps)

    p = sub.add_parser("batch", help="批量操作元素")
    p.add_argument("slide_id")
    p.add_argument("--ops", required=True, help="JSON 文件，支持 {operations:[...]} 或直接数组")
    p.add_argument("--normalize", action="store_true", help="补齐 Agent 手写元素的默认字段，尤其是 text 高度")
    p.add_argument("--dry-run", action="store_true", help="只输出归一化后的 operations，不提交 API")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("upload", help="上传文件")
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("upload-place", help="上传图片并准确放置到指定幻灯片")
    p.add_argument("slide_id")
    p.add_argument("files", nargs="+")
    add_common_element_args(p)
    p.add_argument("--layout", choices=["single", "row", "grid"], default="single", help="多文件放置布局")
    add_auto_place_args(p)
    p.add_argument("--clip-type", default="rect", choices=["rect", "circle", "rounded-rect"])
    p.add_argument("--rx", type=int, default=0)
    p.add_argument("--preview", action="store_true", help="修改成功后自动导出当前页预览图")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_upload_place)

    p = sub.add_parser("place", help="上传图片并放入已有占位槽/图片元素的精确 bbox")
    p.add_argument("slide_id")
    p.add_argument("elem_id")
    p.add_argument("file")
    p.add_argument("--clip-type", default=None, choices=["rect", "circle", "rounded-rect"])
    p.add_argument("--rx", type=int, default=None)
    p.add_argument("--role", default="")
    p.add_argument("--replace", action="store_true", help="即使目标是 image，也删除后按原 bbox 新建图片元素")
    p.add_argument("--add-only", action="store_true", help="保留占位元素，在其层级位置再添加图片")
    p.add_argument("--preview", action="store_true", help="修改成功后自动导出当前页预览图")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_place)

    p = sub.add_parser("component", help="使用内置 HTML/CSS 组件")
    comp = p.add_subparsers(dest="component_command", required=True)

    cp = comp.add_parser("list", help="列出可用组件")
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=cmd_component_list)

    cp = comp.add_parser("render", help="按 JSON 数据渲染组件 HTML/CSS")
    cp.add_argument("name", choices=sorted(COMPONENT_HELP))
    cp.add_argument("--data", default="", help="JSON 字符串、JSON 文件路径，或 @JSON文件")
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=cmd_component_render)

    cp = comp.add_parser("add", help="渲染组件并添加为 html 元素")
    cp.add_argument("slide_id")
    cp.add_argument("name", choices=sorted(COMPONENT_HELP))
    add_common_element_args(cp)
    cp.add_argument("--data", default="", help="JSON 字符串、JSON 文件路径，或 @JSON文件")
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=cmd_component_add)

    p = sub.add_parser("create-slide", help="创建幻灯片")
    p.add_argument("--bg", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--layout", default="")
    p.add_argument("--bg-pattern-color", default="")
    p.add_argument("--index", type=int, default=-1)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_create_slide)

    p = sub.add_parser("update-slide", help="修改幻灯片属性(版式、主题等)")
    p.add_argument("slide_id")
    p.add_argument("--layout", default=None, help="页面布局/版式，例如 SWISS-COVER-CROSS")
    p.add_argument("--theme", default=None, help="主题，例如 light 或 dark")
    p.add_argument("--bg", default=None, help="背景色")
    p.add_argument("--bg-pattern-color", default=None, help="背景图案色")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_update_slide)

    p = sub.add_parser("delete-slide", help="删除幻灯片")
    p.add_argument("slide_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_delete_slide)

    p = sub.add_parser("export", help="导出 ppt/index.html")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("export-image", help="导出某一页幻灯片为图片 (需安装 Edge/Chrome)")
    p.add_argument("slide_id", nargs="?", help="幻灯片 ID")
    add_slide_index_arg(p)
    p.add_argument("--output", "-o", default="", help="保存的图片路径，默认当前目录下 slide_SLIDE_ID.png")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_export_image)

    p = sub.add_parser("compare-image", help="对比当前页导出图和参考截图，输出还原偏差指标")
    p.add_argument("slide_id", nargs="?")
    add_slide_index_arg(p)
    p.add_argument("--reference", required=True, help="参考截图路径")
    p.add_argument("--current", default="", help="当前页截图路径；省略时使用默认导出图")
    p.add_argument("--export-current", action="store_true", help="对比前先导出当前页截图")
    p.add_argument("--output", "-o", default="", help="--export-current 的输出路径")
    p.add_argument("--threshold", type=int, default=18, help="内容边界背景差异阈值")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compare_image)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    resolve_slide_targets(args)
    if hasattr(args, "slide_id") and not getattr(args, "slide_id", None) and not getattr(args, "all", False):
        fail("请提供 slide_id，或使用 --slide-index 选择幻灯片")
    args.func(args)


if __name__ == "__main__":
    main()
