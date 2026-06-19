# QIAN-PPT

基于 **Flask + Fabric.js** 的瑞士风格 PPT 编辑器与展示系统。支持可视化编辑幻灯片（960×540 画布）、3D 元素、全屏演示、导出独立 HTML。

## 技术栈

- **后端**: Flask 3.0+（默认端口 5001，可用 `FLASK_PORT`/`FLASK_HOST` 覆盖；设置 `QIAN_PPT_TOKEN` 后写接口需 `X-Auth-Token`）。存储采用原子写入 + 文件锁（portalocker）+ 乐观锁
- **编辑器**: Fabric.js v5.3.x
- **3D 元素**: Three.js（场景代码由 `.agents/skills/slide-editor/three_templates.py` 生成，编辑器内交互、展示页自动旋转）
- **展示页**: Jinja2 + Motion One + WebGL
- **国际化**: `static/js/i18n.js`（默认 `zh-CN`，支持 `en`）
- **存储**: 多工作区 JSON 文件

## 快速启动

```bash
python app.py
# 编辑器: http://127.0.0.1:5001/editor
# 展示页: http://127.0.0.1:5001/
# 指定工作区: http://127.0.0.1:5001/editor?workspace=default
```

## 项目结构

```
app.py                      — Flask 主应用（页面路由 + REST API）
templates/                  — editor.html（编辑器）、presentation.html（展示/导出）
static/js/                  — fabric / three / motion / i18n
static/icons/               — Material Symbols 字体
static/guizang-backgrounds/ — 预设背景图
data/workspaces/            — 多工作区数据、备份、导出、截图（均 gitignored）
.agents/skills/             — 项目级技能（slide-editor）
ppt/                        — 导出目录
```

## 开发规范

**通用**
- 改动前先确认目标工作区：`python .agents/skills/slide-editor/slide_cli.py workspace list`（多工作区避免误改）
- 遵循现有风格：Python 用 `from __future__ import annotations` + 类型注解 + 中文 docstring/日志；前端文案走 i18n（`static/js/i18n.js`，zh-CN 与 en 同步补齐）

**存储（务必勿绕过）**
- 写 JSON 统一走原子写 + 文件锁（portalocker）+ 乐观锁；勿直接 `open(..., 'w')` 覆盖 slides.json
- 乐观锁冲突返回 409，前端按版本号重试，不要静默吞掉

**前端 / 平台**
- Fabric.js v5.3.x；3D 场景由 `.agents/skills/slide-editor/three_templates.py` 生成
- Windows PowerShell 5.1 禁用 `&&` / `||` 串联命令（用分号或分行）

### 日志排障

- **位置**：`log/YYYY-MM-DD.log`（按日期命名；单文件超 10MB 轮转为 `YYYY-MM-DD.HHMMSS.log`；保留 30 天；已 gitignored）
- **排障优先**：遇到 500、保存失败、加载异常、乐观锁冲突等，先读最新日志文件定位原因
- **新增日志**：`from log_config import get_logger; logger = get_logger('qian-ppt')`
- **错误带堆栈**：`logger.error("...: %s", e, exc_info=True)`（不要用裸 `print`）
- **开关**：`LOG_ENABLED=0` 关闭；`LOG_LEVEL=DEBUG` 调级别

## 相关技能

| 技能 | 用途 |
|------|------|
| **slide-editor** | 幻灯片编辑（CLI/API），**编辑时优先使用** |

多工作区项目中，Agent 修改前必须先确认目标工作区：

```bash
python .agents/skills/slide-editor/slide_cli.py workspace list
python .agents/skills/slide-editor/slide_cli.py --workspace default overview --warnings
```

技能同步给其他 AI 工具（Claude / CodeBuddy / Trae / WorkBuddy）：运行根目录的 `create_skill_links.bat` 或 `.ps1`（创建符号链接）。

## 详细文档

- API、数据结构、CLI 命令、元素类型（含 3D）、布局/校验规则、UI 规范 → [skill.md](.agents/skills/slide-editor/skill.md)
