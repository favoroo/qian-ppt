# QIAN-PPT

基于 **Flask + Fabric.js** 的瑞士风格 PPT 编辑器与展示系统。支持可视化编辑幻灯片（960×540 画布）、全屏演示、导出独立 HTML。

## 技术栈

- **后端**: Flask 3.0+（端口 5001）
- **编辑器**: Fabric.js v5.3.x
- **展示页**: Jinja2 + Motion One + WebGL
- **存储**: JSON 文件

## 快速启动

```bash
python app.py
# 编辑器: http://127.0.0.1:5001/editor
# 展示页: http://127.0.0.1:5001/
# 指定工作区: http://127.0.0.1:5001/editor?workspace=default
```

## 项目结构

```
app.py              — Flask 主应用
data/slides.json    — 旧版默认幻灯片数据（首次访问归入 default 工作区）
data/workspaces/    — 多工作区数据、备份、导出和截图
templates/          — Jinja2 模板
static/             — 静态资源
ppt/                — 导出目录
.agents/skills/       — 项目级技能
```

## 相关技能

| 技能 | 用途 |
|------|------|
| **slide-editor** | 幻灯片编辑（CLI/API），**编辑时优先使用** |

多工作区项目中，Agent 修改前必须先确认目标工作区：

```bash
python .agents/skills/slide-editor/slide_cli.py workspace list
python .agents/skills/slide-editor/slide_cli.py --workspace default overview --warnings
```

## 详细文档

- API、数据结构、CLI 命令、布局规则、校验规则、UI 设计规范 → [skill.md](.agents/skills/slide-editor/skill.md)

