"""幻灯片 HTML/CSS 组件注册表。"""

from __future__ import annotations

from typing import Any, Callable

from .builtins import BUILTIN_COMPONENTS
from .guizang_components import GUIZANG_COMPONENTS


RenderResult = dict[str, str]
Renderer = Callable[[dict[str, Any]], RenderResult]


COMPONENTS: dict[str, dict[str, Any]] = {
    item["name"]: item for item in BUILTIN_COMPONENTS + GUIZANG_COMPONENTS
}


def component_help() -> dict[str, str]:
    """返回组件名称和说明，用于 CLI choices 与 list。"""
    return {name: str(item["description"]) for name, item in COMPONENTS.items()}


def render_component(name: str, data: dict[str, Any]) -> RenderResult:
    """按名称渲染组件。"""
    item = COMPONENTS.get(name)
    if not item:
        raise KeyError(name)
    renderer = item["renderer"]
    return renderer(data)

