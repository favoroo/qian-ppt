# Qian-PPT · Intelligent Slide Editor

> 🌏 **中文版本: [README.md](./README.md)**

> Agent Generated × Manual Free Editing —— A New Generation PPT Workflow

Adapted from [guizang-ppt-skill](https://github.com/op7418/guizang-ppt-skill), building upon its exquisite magazine-style visual design while adding complete visual manual editing capabilities and a CLI toolchain.

## Features

- **Agent Friendly**: Supports PPT generation using various Agent tools (Codex, Antigravity, Claude Code, Trae, etc.)
- **Manual Free Editing** (Key Upgrade): Provides a complete web-based visual editor that allows interventions at any time
- **Rich Element System**: Supports adding text, shapes, widgets, icons, and various other elements
- **Flexible Attribute Control**: Freely adjust color, opacity, position, size, and other properties
- **Built-in CLI Toolchain**: A complete set of command-line tools for agents to precisely edit PPTs


![1780042811694](image/README/1780042811694.png)
*Editing Interface: Left side slide list, center canvas editing area, right side properties panel*


![1780042825426](image/README/1780042825426.png)
![1780042835146](image/README/1780042835146.png)
*Preview Interface: Full-screen slide playback*

![1780042848937](image/README/1780042848937.png)
*Widget Window: Built-in presets, one-click insertion*

## Quick Start

### Method 1: Let the Agent Configure It for You (Recommended)

Simply copy and paste the following message to your Agent:

```
Clone this project from https://github.com/favoroo/qian-ppt and help me configure the environment and start app.py.
```

Supported by mainstream Agent tools such as Claude Code, Codex, Trae, Cursor, etc.

### Method 2: Manual Configuration

#### Requirements

- Python 3.8+
- Flask 3.0+

#### Installation & Running

```bash
# 1. Clone the project
git clone https://github.com/favoroo/qian-ppt.git
cd qian-ppt

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the service
python app.py
```



Access the service after startup:

- **Preview Mode**: http://localhost:5001
- **Editor**: http://localhost:5001/editor
- **Specify Workspace**: http://localhost:5001/editor?workspace=default

### Export

Click the "Export" button in the editor to generate a standalone HTML file at `data/workspaces/<workspace_id>/ppt/index.html` in the current workspace. It can be opened directly in a browser or shared with others without any server.

## Project Structure

```
.
├── app.py                 # Flask backend service (API + routing)
├── requirements.txt       # Python dependencies
├── templates/
│   ├── editor.html        # Editor page
│   └── presentation.html  # Slide presentation page
├── static/                # Static resources (icons, JS libraries, etc.)
├── data/
│   ├── slides.json        # Legacy default data file (moved to default workspace on first access)
│   └── workspaces/        # Multi-workspace data, backups, exports, and screenshots
│       └── default/
│           ├── slides.json
│           ├── backups/
│           ├── ppt/
│           └── slides_image/
├── ppt/                   # Legacy export directory
└── .agents/skills/slide-editor/
    ├── slide_cli.py       # CLI command-line tools
    └── components/        # Widget modules
```

## User Operation Guide

### Screenshot Reproduction: Let the Agent Replicate Web Interfaces for You

**You can send a screenshot of a web page to the Agent, and it will automatically analyze the page structure and faithfully reproduce it in the slides.**

Usage:
1. Take a screenshot of the web interface you want to reproduce (e.g., dashboard, data monitor, product introduction page, etc.)
2. Send the screenshot to the Agent with the instruction "Help me reproduce this interface in slide 02"
3. The Agent will:
   - Analyze layout structure, colors, fonts, and other design elements in the screenshot
   - Use CLI tools or API to rebuild corresponding elements in the slides
   - Adjust position, color, opacity, and other attributes to match the original effect
4. After reproduction, you can fine-tune in the editor

Suitable scenarios: Product demonstrations, competitive analysis, data reports, UI presentations, and other scenarios requiring web content embedding in slides.

### Screenshot Tutorial: Teach the Agent How to Modify Slides

**If the Agent's modification results are unsatisfactory, you can screenshot the current slide, annotate what you want on the image, and send it to the Agent.**

Usage:
1. Take a screenshot of the slide that needs modification
2. Annotate or describe the desired effect on the screenshot (e.g., "make this title bigger", "move the button to the right", etc.)
3. Send the annotated screenshot to the Agent with your modification intent
4. The Agent will understand your intent and execute precise modifications

This approach is more intuitive than pure text descriptions, especially suitable for complex position adjustments, layout optimizations, and other scenarios.

### Recommended Workflow: Write Requirements Document First, Then Generate PPT

**Best Practice: Users only need to write a draft, and the Agent will automatically organize it into a slide-friendly format.**

You don't need to write it in great detail, simply describe your idea, and let the Agent generate the slide document based on the skill (slide-editor).

For example, you only need to write:

```markdown
# PPT Requirements

## Topic
How AI Changes the Software Development Process, 30-Minute Technical Sharing

## Key Points
- Start with pain points of traditional development processes
![](./screenshots/pain-points.png)

- Middle section shows changes and specific cases after AI introduction
![](./screenshots/ai-changes.png)

- Final summary

## Image Materials
You can directly attach image paths in the document, and the Agent will automatically process and insert them into the slides.

```
## Recommended Process
1. **Organize First**: Let the Agent generate a structured "Slide Conversion Document" based on your draft and skill document (slide-editor), clarifying the layout of each page (e.g., titles, paragraphs, images, tables, charts, etc.), content, and visual style
2. **Generate Next**: Let the Agent gradually generate the complete PPT based on this document by calling the skill (slide-editor)

## Agent User Guide

### Editing via CLI Tools

The project comes with a complete set of CLI tools. Agents can precisely manipulate slides via command line:

```bash
# View project structure
python slide_cli.py tree

# View and switch workspaces
python slide_cli.py workspace list
python slide_cli.py workspace create demo-talk --name "Demo Presentation"

# View element list for a specific slide
python slide_cli.py --workspace default ls <slide_id>

# Locate detailed attributes of an element
python slide_cli.py locate <slide_id> <elem_id>

# Add text element
python slide_cli.py --workspace default add-text <slide_id> "Hello World" --x 100 --y 200 --size 24

# Add shape
python slide_cli.py add-shape <slide_id> rect --x 50 --y 50 --width 200 --height 100 --fill "#C5E803"

# Insert widget
python slide_cli.py add-component <slide_id> metric-card --x 100 --y 100

# Update element attributes
python slide_cli.py update <slide_id> <elem_id> --opacity 0.8 --color "#ff0000"

# Delete element
python slide_cli.py delete <slide_id> <elem_id>

# Validate current slide structure
python slide_cli.py validate

# Export as standalone HTML
python slide_cli.py --workspace default export
```

All coordinates use the **960x540** canvas coordinate system.

### Editing via API

Agents can also directly call REST APIs:

| Method   | Path                              | Description                |
| -------- | --------------------------------- | -------------------------- |
| GET      | `/api/slides`                     | Get all slide data         |
| POST     | `/api/slides`                     | Save all slide data        |
| POST     | `/api/slides/create`              | Insert new slide at specified position |
| PUT      | `/api/slides/<id>`                | Update a specific slide    |
| DELETE   | `/api/slides/<id>`                | Delete a specific slide    |
| GET      | `/api/slides/<id>/elements`       | Get all elements of a slide |
| POST     | `/api/slides/<id>/elements`       | Add element                |
| PUT      | `/api/slides/<id>/elements/<id>`  | Update element attributes  |
| DELETE   | `/api/slides/<id>/elements/<id>`  | Delete element             |
| POST     | `/api/slides/<id>/elements/batch` | Batch operations on elements |
| POST     | `/api/upload`                     | Upload image               |
| GET      | `/api/components`                 | Get available widget list  |
| POST     | `/api/components/render`          | Render widget HTML         |
| GET      | `/api/export`                     | Export as standalone HTML  |

All data APIs support `?workspace=<workspace_id>`, defaults to `default` if not provided.

## Built-in Widgets

| Widget              | Description         |
| ------------------- | ------------------- |
| metric-card         | Key metric card     |
| grid-card           | Grid card           |
| grid-list           | Grid list           |
| circular-flow       | Circular flowchart  |
| compare-columns     | Two-column comparison |
| kpi-strip           | KPI strip           |
| screenshot-frame    | Screenshot frame    |
| guizang-typography  | Magazine-style typography |
| guizang-callout     | Callout block       |
| guizang-stat-card   | Statistics card     |
| guizang-stat-grid   | Statistics grid     |
| guizang-pillar-card | Pillar card         |
| guizang-pillar      | Pillar combination  |
| guizang-rowline     | Row line list       |
| guizang-figure      | Image reference     |
| guizang-platform    | Platform data card  |
| guizang-ghost       | Ghost large text background |

## Comparison with guizang-ppt-skill

| Feature                | guizang-ppt-skill | Qian-PPT |
| ---------------------- |:-----------------:|:--------:|
| Magazine-style Visual Design | ✅              | ✅       |
| Agent Generates PPT    | ✅                 | ✅       |
| Visual Editor          | ❌                 | ✅       |
| CLI Toolchain          | ❌                 | ✅       |
| REST API               | ❌                 | ✅       |
| Free Element Editing   | ❌                 | ✅       |
| Image Upload Management | ❌                | ✅       |
| Automatic Backup       | ❌                 | ✅       |
| Widget System          | ❌                 | ✅       |

