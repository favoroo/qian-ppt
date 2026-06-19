---
name: slide-editor
description: EVKIT2 幻灯片生成与精确编辑技能。用于从文档、素材或修改需求快速规划、生成、查看、定位、添加、删除、移动、替换和校验 960x540 画布元素；优先通过 slide_cli.py 和本地 API 操作 canvas_elements，支持页序号定位、占位槽识别、自动找空位、图片上传精确放置、文本溢出/重叠检查、HTML/CSS 组件和单页导出预览。Windows PowerShell 5.1 环境下禁止用 `&&`/`||` 串联命令。
---

# EVKIT2 幻灯片编辑技能

## 核心原则

只通过 `slide_cli.py` 或后端 API 编辑 `canvas_elements`，不要直接改工作区下的 `slides.json`。画布固定为 `960 x 540`，`x/y` 是左上角坐标。所有 `SLIDE_ID` 都可写成 `#0`、`#1`、`#-1` 按页序号引用；PowerShell 中必须加引号，例如 `"#0"`。

先确认工作区，再做定位和修改。常用工作区执行一次：

```bash
python .agents/skills/slide-editor/slide_cli.py workspace list
python .agents/skills/slide-editor/slide_cli.py workspace select WORKSPACE_ID
```

PowerShell 5.1 每条命令单独执行，禁止 `&&`、`||`、bash heredoc 和 `\` 行尾续行。大段 JSON/HTML/CSS 必须写入文件。`batch --ops` 永远传普通文件名，例如 `--ops ops.json`，不要写 `@ops.json`；`@file.json` 只用于明确支持该写法的参数，例如组件 `--data @data.json` 或属性值文件。

## 最短工作流

1. **看全局和风险**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py overview --warnings
   python .agents/skills/slide-editor/slide_cli.py overview --slide-index -1 --warnings
   ```
   首选 `overview --warnings`，通常不用连续跑 `status/list/inspect`。

2. **精确定位目标**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py find --text "关键词"
   python .agents/skills/slide-editor/slide_cli.py find --role title --near top
   python .agents/skills/slide-editor/slide_cli.py inspect "#0" --summary --warnings
   python .agents/skills/slide-editor/slide_cli.py inspect "#0" --ascii --overlaps
   ```
   找图片槽先用 `slots`，找可添加区域用 `space`。

3. **修改优先用专用命令**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py update "#0" title-main -p "text=新标题"
   python .agents/skills/slide-editor/slide_cli.py move "#0" title-main --dx 12 --dy -8 --snap 4 --clamp
   python .agents/skills/slide-editor/slide_cli.py move "#0" title-main --align center-h
   python .agents/skills/slide-editor/slide_cli.py autofit "#0" body-main --shrink
   python .agents/skills/slide-editor/slide_cli.py delete "#0" old-element
   ```
   坐标调整优先用 `move`，不要手算复杂对齐。文本改完优先跑 `autofit` 或 `validate`。

4. **新增元素先自动找位置**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py space "#0" --width 280 --height 120 --near right
   python .agents/skills/slide-editor/slide_cli.py add "#0" --type text --text "补充说明" --width 280 --height 90 --auto-place --near right -m role=body
   python .agents/skills/slide-editor/slide_cli.py upload-place "#0" image/photo.png --width 320 --height 220 --auto-place --near right --clip-type rounded-rect --rx 8
   ```
   `--auto-place` 会避开主要内容元素，忽略装饰、背景和 `meta.allowOverlap=true` 的元素。

5. **图片优先放入占位槽**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py slots --slide "#0" --kind image
   python .agents/skills/slide-editor/slide_cli.py place "#0" slot-image-main image/photo.png --clip-type rounded-rect --rx 8
   python .agents/skills/slide-editor/slide_cli.py upload-place "#0" a.png b.png c.png --layout row --auto-place --near bottom --width 220 --height 140 --gap 18
   ```
   有占位槽或旧图片时用 `place`，它会读取目标 bbox 和层级精确替换。没有槽才用 `upload-place`。

6. **复杂版式用组件或批量**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py component list
   python .agents/skills/slide-editor/slide_cli.py component add "#0" grid-list --x 60 --y 160 --width 840 --height 260 --data @data.json
   python .agents/skills/slide-editor/slide_cli.py batch "#0" --ops ops.json --normalize --dry-run
   python .agents/skills/slide-editor/slide_cli.py batch "#0" --ops ops.json
   ```
   一页新增多个元素时优先写 `ops.json` 用 `batch`，减少 API 往返和 token。手写批量文本时先跑 `--normalize --dry-run`，让 CLI 补齐文本高度、行高、字体和默认角色。

7. **收尾校验**
   ```bash
   python .agents/skills/slide-editor/slide_cli.py validate "#0"
   python .agents/skills/slide-editor/slide_cli.py fix-overlaps "#0"
   python .agents/skills/slide-editor/slide_cli.py fix-overlaps "#0" --axis y --max-shift 32
   python .agents/skills/slide-editor/slide_cli.py fix-overlaps "#0" --axis y --max-shift 32 --apply
   python .agents/skills/slide-editor/slide_cli.py validate --all
   python .agents/skills/slide-editor/slide_cli.py export
   python .agents/skills/slide-editor/slide_cli.py export-image "#0"
   python .agents/skills/slide-editor/slide_cli.py compare-image "#0" --reference reference.png --export-current
   ```
   `fix-overlaps` 默认只给建议；精细还原页面不要直接 `--apply`，先用 `--axis y|x` 锁定对齐轴并设置 `--max-shift`，确认建议合理后再应用。

## 命令速查

| 目标 | 首选命令 |
| --- | --- |
| 快速总览 | `overview --warnings` |
| 单页元素和层级 | `inspect SLIDE_ID --summary --warnings` |
| 线框看布局 | `inspect SLIDE_ID --ascii --overlaps` |
| 搜文字/ID/类型/角色/区域 | `find --text ...`、`find --id ...`、`find --type image`、`find --role title --near top` |
| 找占位槽 | `slots --slide SLIDE_ID --kind image|text` |
| 找空位 | `space SLIDE_ID --width ... --height ... --near right` |
| 新增元素 | `add SLIDE_ID --type text|image|rect|circle|triangle|html ...` |
| 自动避让新增 | `add ... --auto-place --near ...` |
| 修改属性 | `update SLIDE_ID ELEM_ID -p "key=value"` |
| 移动/对齐/缩放 | `move SLIDE_ID ELEM_ID --dx ... --align ... --clamp` |
| 文本测量 | `measure-text --text ... --width ... --font-size ...` |
| 文本适配 | `autofit SLIDE_ID ELEM_ID --shrink` |
| 上传到占位 | `place SLIDE_ID SLOT_ID file.png` |
| 上传并自动排布 | `upload-place SLIDE_ID a.png b.png --layout row|grid --auto-place` |
| 重叠建议/修复 | `fix-overlaps SLIDE_ID`、`fix-overlaps SLIDE_ID --apply` |
| 批量操作 | `batch SLIDE_ID --ops ops.json` |
| 截图对比 | `compare-image SLIDE_ID --reference reference.png --export-current` |
| 组件 | `component list/render/add` |
| 校验 | `validate SLIDE_ID` 或 `validate --all` |
| 导出 | `export`、`export-image SLIDE_ID` |

## 元素字段

通用字段：`id/type/x/y/width/height/angle/opacity/locked/meta`。新增元素必须有 `type/x/y/width/height`；`id` 可省略，由后端生成。文本元素必须显式或通过 `batch --normalize` 补齐 `width/height/fontSize/lineHeight/fontFamily/textAlign`，避免不同渲染环境下排版漂移。

常用类型：

```json
{
  "text": { "text": "标题", "fontSize": 36, "fill": "#0a0a0a", "fontFamily": "Inter, Noto Sans SC, sans-serif", "lineHeight": 1.4 },
  "image": { "src": "/static/uploads/photo.png", "clipType": "rect|circle|rounded-rect", "rx": 8 },
  "shape": { "type": "rect|circle|triangle", "fill": "#C5E803", "stroke": "", "strokeWidth": 0 },
  "html": { "html": "<div>...</div>", "css": ".box{box-sizing:border-box;height:100%;overflow:hidden}" },
  "3d": { "type": "html", "meta": { "role": "3d", "component": "cube", "data": { "geometry": "cube", "color": "#C5E803", "autoRotate": true, "rotateSpeed": 0.01, "metalness": 0.4, "roughness": 0.4, "wireframe": false, "background": "transparent" } } }
}
```

常用 `meta.role`：

| role | 用途 |
| --- | --- |
| `title` / `body` / `image` | 主内容，参与重叠风险 |
| `placeholder` / `image-slot` / `text-slot` | 可替换占位槽 |
| `decor` / `background` | 装饰或背景，自动布局和重叠检查会弱化 |
| `html` | HTML 组件容器 |
| `3d` | Three.js 3D 元素（底层 type='html'） |

刻意重叠时加 `meta.allowOverlap=true`。装饰元素加 `meta.role=decor`，避免误报。

## 3D 元素（Three.js）

3D 元素复用 HTML 通道：底层 `type='html'`，通过 `meta.role='3d'` 标识。`html` 字段内嵌 Three.js 场景代码，展示页和编辑器自动执行。

**预设几何体**：`cube`（立方体）、`sphere`（球体）、`torus`（圆环）、`cylinder`（圆柱）、`cone`（圆锥）、`icosahedron`（二十面体）、`particles`（粒子系统）、`galaxy`（星系粒子）、`waves`（动态波浪）、`network`（科技网络）、`custom`（自定义代码）。

**添加 3D 元素**：

```bash
# 添加默认旋转立方体
python .agents/skills/slide-editor/slide_cli.py add "#0" --type 3d --geometry cube --auto-place

# 添加红色球体
python .agents/skills/slide-editor/slide_cli.py add "#0" --type 3d --geometry sphere --fill "#ff0000" --auto-place

# 添加快速旋转的圆环
python .agents/skills/slide-editor/slide_cli.py add "#0" --type 3d --geometry torus --rotate-speed 0.03 --auto-place

# 添加线框模式二十面体
python .agents/skills/slide-editor/slide_cli.py add "#0" --type 3d --geometry icosahedron --wireframe --auto-place
```

**3D 参数**：`--geometry`（几何体）、`--fill`（颜色）、`--auto-rotate`/`--no-auto-rotate`（自动旋转）、`--rotate-speed`（旋转速度 0-0.1）、`--metalness`（金属度 0-1）、`--roughness`（粗糙度 0-1）、`--wireframe`（线框模式）、`--bg`（背景色，transparent 或 #RRGGBB）。

**自定义 3D 元素**：当用户需要非预设几何体、复杂动画、加载外部模型、特殊材质或特定交互效果时，优先使用 `--geometry custom` 传入完整 Three.js 场景代码。自定义代码仍会被标记为 `meta.role='3d'`，享受 3D 元素识别和管理能力。

```bash
# 直接传入自定义 Three.js 场景完整 HTML 代码
python .agents/skills/slide-editor/slide_cli.py add "#0" --type 3d --geometry custom --custom-code "<div class=\"three-host\">...</div><script>...</script>" --auto-place

# 从文件读取自定义 Three.js 场景代码
python .agents/skills/slide-editor/slide_cli.py add "#0" --type 3d --geometry custom --custom-file my_scene.html --auto-place
```

自定义代码需要自包含可执行的 Three.js 场景：建议包含容器 `<div>`、`<canvas>` 初始化、`requestAnimationFrame` 动画循环，并复用页面已加载的 `window.THREE`。注意：自定义 3D 元素在展示页仍为自动播放，不支持鼠标/键盘交互；需要交互请在编辑器内测试。

**修改 3D 元素**：用 `update --property html=<新代码>` 直接替换整个 3D 场景代码；也可以修改 `meta.data` 中的参数后重新生成代码（适用于基于模板的元素）。自定义 3D 元素通常直接 `update html` 即可。

**查找 3D 元素**：`find --type 3d` 会自动匹配 `type='html'` 且 `meta.role='3d'` 的元素。

**注意**：3D 元素在展示页为自动播放（自动旋转），不支持鼠标交互。编辑器内可交互。默认尺寸 240×240。

**高级兜底**：如需完全脱离 3D 元数据机制，也可用 `--type html` + `--html-file` 传入自定义 Three.js 代码并设置 `--meta role=3d`：

```bash
python .agents/skills/slide-editor/slide_cli.py add "#0" --type html --html-file my_scene.html --meta role=3d --auto-place
```

## 占位与上传规则

新增图片槽推荐：

```bash
python .agents/skills/slide-editor/slide_cli.py add "#0" --type rect --id slot-image-main --x 520 --y 120 --width 360 --height 260 --fill "#f0f0ee" --meta role=placeholder
```

CLI 会识别这些占位：`meta.role=placeholder|slot|image-slot|text-slot|upload-slot`；`id` 含 `placeholder/slot/drop/upload/replace/image-slot`；文本含 `占位/上传/替换/放置图片/placeholder/image here`；空 `image.src`；默认文本 `双击编辑文字`。

`place` 行为：

- 目标是已有 `image` 且未加 `--replace`：只更新 `src/clipType/rx`。
- 目标是文本/矩形占位：删除占位，并在原 bbox 和原层级插入图片。
- 需要保留占位框：加 `--add-only`。

## HTML 与设计规则

- 截图/网页/界面还原时，默认使用原生 `text/image/rect/circle/triangle` 元素重建，不要把整页做成一个 `html` 容器。
- 截图还原先量参考图：识别网页主体内容容器、左右边距、主要基线、列宽、分割线和卡片间距，再按 960x540 画布映射坐标；不要把原网页窄容器凭感觉铺满整张幻灯片。
- 需要辅助对齐时，可以临时建立 `layout-guide` 类装饰线或只读报告；辅助线必须设置 `meta.role=decor` 或 `meta.allowOverlap=true`，避免重叠校验误报。
- 标题、导航、按钮文案、卡片标题、正文、标签、页脚等文字必须优先拆成独立 `text` 元素，便于用户双击编辑。
- 色块、卡片背景、分割线、头像圆点、占位图块等视觉结构优先用原生形状；图片优先用 `image`。
- 每个可编辑元素设置稳定 `id`，并按用途补 `meta.role=title|body|image|decor|placeholder`，便于后续定位和批量修改。
- `type: html` 只用于复杂组件、KPI/图表、CSS 特效、不可拆 SVG、交互式结构或短期无法可靠拆解的局部片段。
- 如果确实要用 HTML，范围要尽量小：只包住不可拆的局部，不要覆盖整张幻灯片或整块主内容。
- 编辑器支持对选中的自定义 HTML/CSS 执行“拆分为可编辑元素”，但这只是兜底能力；Agent 生成时仍应优先直接产出原生元素。
- HTML 适合复杂卡片、KPI、网格、流程、截图框；编辑器内可能只显示占位框，展示页完整渲染。
- 自写 HTML 根节点必须限制容器：`box-sizing:border-box;height:100%;overflow:hidden`。
- 局部变色或加粗，优先拆成多个 `text` 元素并保持相同 `y/fontSize/lineHeight`。
- 组件数据包含数组时用 `--data @file.json`。
- 常用组件：`metric-card`、`grid-list`、`circular-flow`、`compare-columns`、`kpi-strip`、`screenshot-frame`、`guizang-*`。

## 布局规则

- 常用边距：左右 `40-60px`，顶部 `30-60px`，底部 `24-40px`。
- 标题区：kicker `x=60 y=38`；主标题 `x=60 y=72-130`；正文从 `y=150` 后开始。
- 双栏：左栏 `x=60 width=400`，右栏 `x=500 width=400`。
- 四卡片：`x=40/260/480/700`，`width=204`，间距 `16px`。
- 不确定位置时先 `space`，新增时用 `--auto-place`。
- 文本溢出先 `autofit --shrink`，仍不足再拆分文本。
- 误重叠先 `inspect --overlaps`，再 `fix-overlaps --axis y|x --max-shift ...` 或 `move`。截图还原优先手动保持原图对齐关系。

## 截图还原工作流

1. 先保存参考截图路径，确认目标页和工作区；运行 `overview --warnings` 看当前状态。
2. 根据参考图估算主体容器：记录参考图尺寸、内容左上角、内容宽度、高度、列分割位置和关键文字基线。
3. 把参考图主体容器映射到 960x540 画布，先建 header、hero、内容区、侧栏、页脚的骨架，再填文本和形状。
4. 批量新增前运行 `batch "#0" --ops ops.json --normalize --dry-run`，确认文本 bbox 完整；通过后再执行真实 `batch`。
5. 每轮调整后运行 `validate`、`export-image` 和 `compare-image "#0" --reference reference.png --export-current`，用内容边界偏移和像素差异判断是否继续微调。
6. 不用 ASCII 预览作为最终依据；ASCII 只用于快速定位元素，最终以导出图和参考图对比为准。

## 从文档生成 PPT

1. 先拆页级大纲：封面、章节、内容、数据、案例、结尾。
2. 每页先做骨架：标题、正文区、图片槽、数据槽；槽显式设置 `meta.role=placeholder`。
3. 批量创建元素优先写 `ops.json` 并用 `batch`。
4. 图片素材用 `slots` 找槽再 `place`，没有槽才 `upload-place --auto-place`。
5. 每完成 1-3 页跑 `overview --warnings`；全量完成后跑 `validate --all`、`export`，关键页再 `export-image`。

## Batch JSON

`batch` 推荐顶层使用 `operations`，也兼容直接传数组。动作字段是 `action`，元素类型写在 `element.type`。PowerShell 中命令写 `--ops ops.json`，不要写 `--ops @ops.json`；CLI 虽兼容误写的 `@` 前缀，但规范流程仍使用普通文件名。

```json
{
  "operations": [
    {
      "action": "add",
      "element": {
        "type": "text",
        "x": 60,
        "y": 80,
        "width": 360,
        "height": 60,
        "text": "标题"
      }
    },
    {
      "action": "update",
      "id": "title-main",
      "properties": {
        "fontSize": 42
      }
    },
    {
      "action": "delete",
      "id": "old-placeholder"
    }
  ]
}
```

## API 兜底

优先用 CLI。只有 CLI 不够时直接调用 API：

| 操作 | API |
| --- | --- |
| 获取全部数据 | `GET /api/slides?workspace=WORKSPACE_ID` |
| 创建幻灯片 | `POST /api/slides/create` |
| 删除幻灯片 | `DELETE /api/slides/<slide_id>` |
| 重排幻灯片 | `POST /api/slides/reorder` |
| 获取元素 | `GET /api/slides/<slide_id>/elements` |
| 添加元素 | `POST /api/slides/<slide_id>/elements` |
| 更新元素 | `PUT /api/slides/<slide_id>/elements/<elem_id>` |
| 删除元素 | `DELETE /api/slides/<slide_id>/elements/<elem_id>` |
| 批量元素操作 | `POST /api/slides/<slide_id>/elements/batch` |
| 上传文件 | `POST /api/upload` |
| 导出 HTML | `GET /api/export` |
