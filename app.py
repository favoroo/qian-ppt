import os
import json
import shutil
import time
import uuid
import copy
import re
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, has_request_context, abort
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 跨平台文件锁（可选依赖，缺失时降级为无锁并告警）
try:
    import portalocker
    HAS_FILE_LOCK = True
except ImportError:
    HAS_FILE_LOCK = False

# 响应压缩（可选依赖，缺失时降级为不压缩）
try:
    from flask_compress import Compress
    HAS_COMPRESS = True
except ImportError:
    HAS_COMPRESS = False

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['DATA_FILE'] = os.path.join('data', 'slides.json')
app.config['BACKUP_FOLDER'] = os.path.join('data', 'backups')
app.config['WORKSPACES_FOLDER'] = os.path.join('data', 'workspaces')
app.config['WORKSPACES_META_FILE'] = os.path.join(app.config['WORKSPACES_FOLDER'], 'workspaces.json')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'mp4', 'webm'}
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 7  # 静态资源 7 天缓存

# 日志配置：按日期落盘 + 异步写入 + 大小轮转（详见 log_config.py）
from log_config import setup_logging, get_logger
setup_logging()
logger = get_logger('qian-ppt')

if not HAS_FILE_LOCK:
    logger.warning("portalocker 未安装，文件锁降级为无锁模式，并发写入可能丢失更新。建议 pip install portalocker")

if HAS_COMPRESS:
    Compress(app)
else:
    logger.info("flask-compress 未安装，大 JSON 响应未启用 gzip。建议 pip install flask-compress")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)
os.makedirs(os.path.join('data'), exist_ok=True)
os.makedirs(app.config['WORKSPACES_FOLDER'], exist_ok=True)

DEFAULT_WORKSPACE_ID = 'default'
WORKSPACE_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')
BACKUP_KEEP_COUNT = 10

# Slide editor 路径配置（可根据实际目录结构调整）
SLIDE_EDITOR_PATH = os.path.join('.agents', 'skills', 'slide-editor')


class WorkspaceValidationError(ValueError):
    """工作区参数校验失败专用异常。"""


class VersionConflictError(Exception):
    """乐观锁版本冲突异常，返回 409 + 当前数据。"""
    def __init__(self, current_version, current_data):
        super().__init__("version_conflict")
        self.current_version = current_version
        self.current_data = current_data


@app.errorhandler(WorkspaceValidationError)
def handle_workspace_validation_error(error):
    """把工作区参数校验失败返回为 400。"""
    return jsonify({"error": "Invalid workspace id"}), 400


@app.errorhandler(VersionConflictError)
def handle_version_conflict(error):
    """乐观锁冲突：返回 409 + 当前版本与数据，供前端刷新合并。"""
    return jsonify({
        "error": "version_conflict",
        "message": "数据已被其他会话修改，请刷新后重试",
        "_version": error.current_version,
        "data": error.current_data
    }), 409


@app.after_request
def add_security_headers(response):
    """补充基础安全响应头并记录请求日志。"""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    # 请求日志：按状态码分级记录
    start_time = getattr(request, '_start_time', None)
    duration = (time.time() - start_time) * 1000 if start_time else 0
    status = response.status_code
    msg = "%s %s → %s (%.0fms)" % (request.method, request.path, status, duration)
    if status >= 500:
        logger.error(msg)
    elif status >= 400:
        logger.warning(msg)
    else:
        logger.debug(msg)
    return response


# Token 认证（可选）：设置 QIAN_PPT_TOKEN 后，/api/* 写操作需带 X-Auth-Token 头
AUTH_TOKEN = os.environ.get('QIAN_PPT_TOKEN', '')
WRITE_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}


@app.before_request
def enforce_token_auth():
    """对 /api/* 写操作校验 Token；未设置 QIAN_PPT_TOKEN 时跳过（本地零配置）。"""
    # 记录请求开始时间，供 after_request 计算耗时
    request._start_time = time.time()
    if not AUTH_TOKEN:
        return None
    if not request.path.startswith('/api/'):
        return None
    if request.method not in WRITE_METHODS:
        return None
    if request.headers.get('X-Auth-Token', '') == AUTH_TOKEN:
        return None
    logger.warning("认证失败: %s %s (缺少或错误的 X-Auth-Token, 远程地址: %s)",
                   request.method, request.path, request.remote_addr)
    return jsonify({"error": "unauthorized", "message": "缺少或错误的 X-Auth-Token"}), 401


def default_slides_data():
    """生成默认幻灯片数据结构。"""
    return {
        "_version": 0,
        "settings": {"accent": "lemon-green", "title": "QIAN-PPT"},
        "slides": []
    }


def validate_workspace_id(workspace_id):
    """校验工作区 ID，避免路径穿越和不可控文件名。"""
    if not isinstance(workspace_id, str):
        return False
    return bool(WORKSPACE_ID_RE.match(workspace_id))


def normalize_workspace_id(workspace_id=None):
    """解析并规范化工作区 ID。"""
    raw = workspace_id
    if raw is None:
        raw = request.args.get('workspace', DEFAULT_WORKSPACE_ID) if has_request_context() else DEFAULT_WORKSPACE_ID
    raw = str(raw or DEFAULT_WORKSPACE_ID).strip()
    if not raw:
        raw = DEFAULT_WORKSPACE_ID
    if not validate_workspace_id(raw):
        raise WorkspaceValidationError("Invalid workspace id")
    return raw


def workspace_dir(workspace_id):
    """返回工作区目录。"""
    wid = normalize_workspace_id(workspace_id)
    return os.path.join(app.config['WORKSPACES_FOLDER'], wid)


def workspace_data_file(workspace_id):
    """返回工作区幻灯片数据文件。"""
    return os.path.join(workspace_dir(workspace_id), 'slides.json')


def workspace_backup_folder(workspace_id):
    """返回工作区备份目录。"""
    return os.path.join(workspace_dir(workspace_id), 'backups')


def workspace_export_folder(workspace_id):
    """返回工作区 HTML 导出目录。"""
    return os.path.join(workspace_dir(workspace_id), 'ppt')


def workspace_image_folder(workspace_id):
    """返回工作区截图导出目录。"""
    return os.path.join(workspace_dir(workspace_id), 'slides_image')


def ensure_workspace_dirs(workspace_id):
    """确保工作区基础目录存在。"""
    wid = normalize_workspace_id(workspace_id)
    os.makedirs(workspace_dir(wid), exist_ok=True)
    os.makedirs(workspace_backup_folder(wid), exist_ok=True)
    os.makedirs(workspace_export_folder(wid), exist_ok=True)
    os.makedirs(workspace_image_folder(wid), exist_ok=True)
    return wid


def read_workspaces_meta():
    """读取工作区元数据。"""
    if os.path.exists(app.config['WORKSPACES_META_FILE']):
        try:
            with open(app.config['WORKSPACES_META_FILE'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get('workspaces'), dict):
                return data
        except Exception as e:
            logger.error("加载工作区元数据失败: %s", e)
    return {"workspaces": {}}


def write_workspaces_meta(meta):
    """写入工作区元数据。"""
    os.makedirs(app.config['WORKSPACES_FOLDER'], exist_ok=True)
    with open(app.config['WORKSPACES_META_FILE'], 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def ensure_workspace(workspace_id=DEFAULT_WORKSPACE_ID, name=None, copy_from_legacy=False):
    """创建或补齐工作区目录、数据文件和元数据。"""
    wid = ensure_workspace_dirs(workspace_id)
    meta = read_workspaces_meta()
    workspaces = meta.setdefault('workspaces', {})
    if wid not in workspaces:
        workspaces[wid] = {
            "id": wid,
            "name": name or ("默认工作区" if wid == DEFAULT_WORKSPACE_ID else wid),
            "createdAt": datetime.now().isoformat(timespec='seconds'),
            "updatedAt": datetime.now().isoformat(timespec='seconds')
        }
        write_workspaces_meta(meta)

    data_file = workspace_data_file(wid)
    if not os.path.exists(data_file):
        if (copy_from_legacy or wid == DEFAULT_WORKSPACE_ID) and os.path.exists(app.config['DATA_FILE']):
            shutil.copy2(app.config['DATA_FILE'], data_file)
        else:
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(default_slides_data(), f, ensure_ascii=False, indent=2)
    return wid


def ensure_default_workspace():
    """确保默认工作区存在，并兼容迁移旧 data/slides.json。"""
    return ensure_workspace(DEFAULT_WORKSPACE_ID, "默认工作区", copy_from_legacy=True)


def list_workspaces():
    """列出所有工作区。只读不写，避免每次列出都触发元数据写放大。

    未登记的目录以"孤儿"形式展示（标记 unregistered），由 create/rename/delete/save 时才写元数据。
    """
    ensure_default_workspace()
    meta = read_workspaces_meta()
    registered = meta.get('workspaces', {})
    rows = list(registered.values())
    # 收集已登记的 id，用于检测孤儿目录
    registered_ids = {r.get('id') for r in rows}
    # 目录存在但元数据缺失时，作为只读孤儿展示，不自动写元数据
    try:
        for item in os.listdir(app.config['WORKSPACES_FOLDER']):
            item_path = os.path.join(app.config['WORKSPACES_FOLDER'], item)
            if os.path.isdir(item_path) and validate_workspace_id(item) and item not in registered_ids:
                rows.append({
                    "id": item,
                    "name": item,
                    "createdAt": "",
                    "updatedAt": "",
                    "unregistered": True
                })
    except OSError:
        pass
    rows.sort(key=lambda x: (x.get('id') != DEFAULT_WORKSPACE_ID, x.get('name', x.get('id', ''))))
    return rows


def sanitize_text_in_data(data):
    """递归清理数据中所有文本元素的转义字符（\\n → 真换行）"""
    if isinstance(data, dict):
        return {k: sanitize_text_in_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_text_in_data(item) for item in data]
    elif isinstance(data, str) and '\\n' in data:
        return data.replace('\\n', '\n').replace('\\t', '\t')
    return data


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def load_slides(workspace_id=None):
    wid = ensure_workspace(normalize_workspace_id(workspace_id))
    data_file = workspace_data_file(wid)
    backup_folder = workspace_backup_folder(wid)
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error("加载工作区 %s 的 slides.json 失败: %s。尝试从备份恢复...", wid, e)
            # 尝试从最近的合法备份恢复
            if os.path.exists(backup_folder):
                backups = sorted([f for f in os.listdir(backup_folder) if f.startswith('slides_')], reverse=True)
                for backup in backups:
                    backup_path = os.path.join(backup_folder, backup)
                    try:
                        with open(backup_path, 'r', encoding='utf-8') as bf:
                            data = json.load(bf)
                        # 用合法备份覆盖损坏的 data_file（原子写）
                        _atomic_write_json(data_file, data)
                        logger.info("已从备份 %s 恢复 slides.json", backup)
                        return data
                    except Exception as be:
                        logger.warning("加载备份 %s 失败: %s", backup, be)
            logger.error("未找到可用备份，返回空数据。")
    return default_slides_data()


def _read_version_fast(data_file):
    """快速读取 _version，只读文件头部用正则匹配，避免完整解析大 JSON。"""
    if not os.path.exists(data_file):
        return 0
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            head = f.read(2048)
        match = re.search(r'"_version"\s*:\s*(\d+)', head)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return 0


def _next_version(data_file):
    """生成单调递增的版本号，避免同毫秒碰撞。"""
    current = _read_version_fast(data_file)
    now_ms = int(time.time() * 1000)
    return max(now_ms, current + 1)


def _atomic_write_json(target_path, data):
    """原子写 JSON：写临时文件后 os.replace 替换，避免半截损坏。"""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target_path), suffix='.tmp', prefix='.save_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target_path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        logger.error("原子写 JSON 失败: %s (临时文件: %s)", target_path, tmp, exc_info=True)
        raise


def _prune_backups(backup_folder, keep=BACKUP_KEEP_COUNT):
    """只保留最近 N 个备份。"""
    try:
        backups = sorted([f for f in os.listdir(backup_folder) if f.startswith('slides_')])
        for old in backups[:-keep]:
            try:
                os.remove(os.path.join(backup_folder, old))
            except OSError as e:
                logger.warning("删除旧备份 %s 失败: %s", old, e)
    except OSError:
        pass


def save_slides(data, workspace_id=None, expected_version=None):
    """保存幻灯片数据。

    - expected_version: 乐观锁，若不为 None 且与磁盘当前版本不一致则抛 VersionConflictError(409)。
    - 采用文件锁 + 原子写，防止并发丢失更新与崩溃损坏。
    - 备份直接 copy2（不再先 json.load 验证，减少一次全量读）；合法性校验由 load_slides 恢复路径兜底。
    """
    wid = ensure_workspace(normalize_workspace_id(workspace_id))
    data_file = workspace_data_file(wid)
    backup_folder = workspace_backup_folder(wid)
    lock_file = data_file + '.lock'

    with open(lock_file, 'w') as lf:
        if HAS_FILE_LOCK:
            try:
                portalocker.lock(lf, portalocker.LOCK_EX)
            except Exception as e:
                logger.warning("获取文件锁失败，降级无锁写入: %s", e)

        # 乐观锁校验（在锁内，避免 TOCTOU）
        if expected_version is not None:
            current = _read_version_fast(data_file)
            if current != expected_version:
                # 冲突：返回当前数据供前端合并
                logger.warning("乐观锁冲突: 工作区 %s 期望版本 %s, 实际版本 %s", wid, expected_version, current)
                try:
                    with open(data_file, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                except Exception:
                    current_data = default_slides_data()
                raise VersionConflictError(current, current_data)

        # 更新版本号（单调递增）
        data['_version'] = _next_version(data_file)

        # 备份（直接 copy2，不再先 json.load 验证）
        if os.path.exists(data_file):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            backup_path = os.path.join(backup_folder, f'slides_{ts}.json')
            try:
                shutil.copy2(data_file, backup_path)
            except OSError as e:
                logger.warning("备份失败: %s", e)
            _prune_backups(backup_folder)

        # 原子写
        _atomic_write_json(data_file, data)

    # 更新工作区元数据 updatedAt
    meta = read_workspaces_meta()
    if wid in meta.get('workspaces', {}):
        meta['workspaces'][wid]['updatedAt'] = datetime.now().isoformat(timespec='seconds')
        write_workspaces_meta(meta)
    return data['_version']


def _extract_base_version():
    """从当前请求 JSON 体中提取 base_version（乐观锁），无则返回 None（兼容老前端）。

    依次查找 base_version / _base_version / _version 字段。
    对 POST /api/slides（body 即完整 deck，含 _version）自动生效；
    对元素级路由，前端需显式发送 base_version。
    """
    if not has_request_context():
        return None
    try:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            for key in ('base_version', '_base_version', '_version'):
                bv = body.get(key)
                if bv is not None:
                    try:
                        return int(bv)
                    except (TypeError, ValueError):
                        continue
    except Exception:
        pass
    return None


def make_export_data_json(data):
    """生成可嵌入 HTML 的编辑数据 JSON，避免内容意外闭合 script 标签。"""
    return json.dumps(data, ensure_ascii=False).replace('</', '<\\/')


def normalize_import_data(data):
    """校验并补齐导入数据的基础结构。"""
    if not isinstance(data, dict):
        return None, "导入数据必须是 JSON 对象"
    slides = data.get('slides')
    if not isinstance(slides, list):
        return None, "导入数据缺少 slides 数组"

    normalized = copy.deepcopy(data)
    normalized.setdefault('settings', {})
    if not isinstance(normalized['settings'], dict):
        return None, "settings 必须是 JSON 对象"

    for i, slide in enumerate(normalized['slides']):
        if not isinstance(slide, dict):
            return None, f"第 {i + 1} 页幻灯片必须是 JSON 对象"
        slide.setdefault('id', generate_slide_id())
        slide.setdefault('layout', '')
        slide.setdefault('theme', 'light')
        slide.setdefault('animate', '')
        slide.setdefault('backgroundColor', '#fafaf8')
        slide.setdefault('bgPatternColor', '')
        slide.setdefault('chrome', {"left": "", "right": ""})
        slide.setdefault('content', {})
        slide.setdefault('foot', {"left": "", "center": "", "right": ""})
        slide.setdefault('images', [])
        slide.setdefault('custom_style', {})
        slide.setdefault('canvas_elements', [])
        if not isinstance(slide['canvas_elements'], list):
            return None, f"第 {i + 1} 页 canvas_elements 必须是数组"
        for elem in slide['canvas_elements']:
            if not isinstance(elem, dict):
                return None, f"第 {i + 1} 页包含非法元素"
            if 'type' not in elem:
                return None, f"第 {i + 1} 页存在缺少 type 的元素"
    normalize_image_sources(normalized)
    return normalized, None


def normalize_image_sources(data):
    """把导入数据中的本机上传图片 URL 统一为 /static/uploads/...。"""
    for slide in data.get('slides', []):
        for elem in slide.get('canvas_elements', []):
            if elem.get('type') == 'image' and isinstance(elem.get('src'), str):
                elem['src'] = normalize_upload_url(elem['src'])
        for img in slide.get('images', []):
            if isinstance(img, dict) and isinstance(img.get('url'), str):
                img['url'] = normalize_upload_url(img['url'])


def normalize_upload_url(src):
    if not src or src.startswith('data:'):
        return src
    parsed = urlparse(src)
    path = parsed.path if parsed.scheme and parsed.netloc else src
    if path.startswith('/static/uploads/'):
        return path
    return src


def rewrite_import_ids(imported_data, existing_data):
    """追加导入时重写 slide/element ID，避免覆盖当前稿。"""
    existing_slide_ids = {str(s.get('id')) for s in existing_data.get('slides', []) if s.get('id')}
    existing_elem_ids = {
        str(e.get('id'))
        for s in existing_data.get('slides', [])
        for e in s.get('canvas_elements', [])
        if e.get('id')
    }

    rewritten = copy.deepcopy(imported_data)
    for slide in rewritten.get('slides', []):
        old_slide_id = str(slide.get('id', ''))
        new_slide_id = generate_slide_id()
        while new_slide_id in existing_slide_ids:
            new_slide_id = generate_slide_id()
        slide['id'] = new_slide_id
        existing_slide_ids.add(new_slide_id)

        for elem in slide.get('canvas_elements', []):
            old_elem_id = str(elem.get('id', ''))
            new_elem_id = generate_elem_id()
            while new_elem_id in existing_elem_ids:
                new_elem_id = generate_elem_id()
            elem['id'] = new_elem_id
            existing_elem_ids.add(new_elem_id)

            # HTML 组件内部可能记录来源 ID；只处理显式同名字段，避免误改用户内容。
            meta = elem.get('meta')
            if isinstance(meta, dict):
                if str(meta.get('slideId')) == old_slide_id:
                    meta['slideId'] = new_slide_id
                if str(meta.get('elementId')) == old_elem_id:
                    meta['elementId'] = new_elem_id

    return rewritten


def find_slide(data, slide_id):
    """根据 slide_id 查找幻灯片，兼容数字和字符串 ID"""
    for i, s in enumerate(data['slides']):
        if str(s.get('id')) == str(slide_id):
            return i, s
    return -1, None


def generate_elem_id():
    """生成元素唯一 ID"""
    return 'elem-' + uuid.uuid4().hex[:8]


def generate_slide_id():
    """生成幻灯片唯一 ID"""
    return 'slide-' + uuid.uuid4().hex[:8]


def parse_index(value, default=-1):
    """把请求里的 index 统一转成整数，非法时使用默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def collect_element_ids(slide):
    """收集当前幻灯片已有元素 ID，便于防重复。"""
    return {str(e.get('id')) for e in slide.get('canvas_elements', []) if e.get('id')}


def ensure_element_id(element, used_ids):
    """确保元素 ID 存在且不重复；显式传入重复 ID 时返回错误。"""
    elem_id = element.get('id')
    if elem_id:
        elem_id = str(elem_id)
        if elem_id in used_ids:
            return False, f"Element id already exists: {elem_id}"
        element['id'] = elem_id
    else:
        elem_id = generate_elem_id()
        while elem_id in used_ids:
            elem_id = generate_elem_id()
        element['id'] = elem_id
    used_ids.add(elem_id)
    return True, None


# ============ Template Filters ============

@app.template_filter('render_styled_text')
def render_styled_text_filter(elem):
    """将 Fabric.js 包含局部字符样式的 text 渲染为 HTML span 标签"""
    import html
    text = elem.get('text', '')
    if not text:
        return ''
    
    styles = elem.get('styles')
    if not styles or not isinstance(styles, dict):
        return html.escape(text).replace('\n', '<br>')
    
    lines = text.split('\n')
    html_lines = []
    
    def get_css_from_style(style_dict):
        css_parts = []
        if 'fill' in style_dict:
            css_parts.append(f"color: {style_dict['fill']}")
        if 'fontWeight' in style_dict:
            css_parts.append(f"font-weight: {style_dict['fontWeight']}")
        if 'fontStyle' in style_dict:
            css_parts.append(f"font-style: {style_dict['fontStyle']}")
        if 'fontSize' in style_dict:
            size = style_dict['fontSize']
            if isinstance(size, (int, float)):
                css_parts.append(f"font-size: {size}px")
            else:
                css_parts.append(f"font-size: {size}")
        if 'fontFamily' in style_dict:
            css_parts.append(f"font-family: {style_dict['fontFamily']}")
        if 'textBackgroundColor' in style_dict:
            css_parts.append(f"background-color: {style_dict['textBackgroundColor']}")
        
        decorations = []
        if style_dict.get('underline'):
            decorations.append('underline')
        if style_dict.get('linethrough'):
            decorations.append('line-through')
        if style_dict.get('overline'):
            decorations.append('overline')
        if decorations:
            css_parts.append(f"text-decoration: {' '.join(decorations)}")
            
        return '; '.join(css_parts)
    
    for i, line_text in enumerate(lines):
        line_style = styles.get(str(i), {})
        if not line_style:
            html_lines.append(html.escape(line_text))
            continue
            
        line_parts = []
        current_span_text = []
        current_style_key = None
        
        for j, char in enumerate(line_text):
            char_style = line_style.get(str(j), {})
            # 过滤提取支持的样式属性，以便进行稳定的比对
            normalized_style = {
                k: v for k, v in char_style.items() if k in (
                    'fill', 'fontWeight', 'fontStyle', 'fontSize', 'fontFamily', 'textBackgroundColor', 'underline', 'linethrough', 'overline'
                )
            }
            style_key = frozenset(normalized_style.items()) if normalized_style else None
            
            if style_key == current_style_key:
                current_span_text.append(char)
            else:
                if current_span_text:
                    span_content = ''.join(current_span_text)
                    escaped_content = html.escape(span_content)
                    if current_style_key:
                        css_str = get_css_from_style(dict(current_style_key))
                        line_parts.append(f'<span style="{css_str}">{escaped_content}</span>')
                    else:
                        line_parts.append(escaped_content)
                current_span_text = [char]
                current_style_key = style_key
                
        if current_span_text:
            span_content = ''.join(current_span_text)
            escaped_content = html.escape(span_content)
            if current_style_key:
                css_str = get_css_from_style(dict(current_style_key))
                line_parts.append(f'<span style="{css_str}">{escaped_content}</span>')
            else:
                line_parts.append(escaped_content)
                
        html_lines.append(''.join(line_parts))
                
    return '<br>'.join(html_lines)


# ============ 全局错误处理器 ============

from werkzeug.exceptions import HTTPException


@app.errorhandler(404)
def not_found(e):
    logger.warning("404 未找到: %s %s", request.method, request.path)
    return jsonify({"error": "not found"}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error("500 服务器内部错误: %s %s - %s", request.method, request.path, e, exc_info=True)
    return jsonify({"error": "internal server error"}), 500


@app.errorhandler(Exception)
def unhandled_exception(e):
    # HTTP 异常（abort 引发的 403/400 等）交由 Flask 默认处理，不在此拦截
    if isinstance(e, HTTPException):
        raise e
    logger.error("未处理异常: %s %s - %s", request.method, request.path, e, exc_info=True)
    return jsonify({"error": "internal server error"}), 500


# ============ 页面路由 ============

@app.route('/')
def index():
    try:
        workspace_id = normalize_workspace_id()
        data = load_slides(workspace_id)
    except ValueError:
        return "Invalid workspace id", 400
    clean_data = sanitize_text_in_data(data)
    return render_template(
        'presentation.html',
        slides=clean_data.get('slides', []),
        settings=clean_data.get('settings', {}),
        workspace_id=workspace_id
    )


@app.route('/editor')
def editor():
    try:
        workspace_id = normalize_workspace_id()
        data = load_slides(workspace_id)
    except ValueError:
        return "Invalid workspace id", 400
    _raw = json.dumps(data, ensure_ascii=False)
    # 防御性转义：数据中的 </script> 会截断 HTML <script> 块
    # 注意：不能用 '</scr'+'ipt>' 因为 Python 拼接后仍是 </script>
    slides_data = _raw.replace('</script>', r'<\/sc' + 'ript>')
    return render_template(
        'editor.html',
        slides_data=slides_data,
        workspace_id=workspace_id,
        workspaces_json=json.dumps(list_workspaces(), ensure_ascii=False)
    )


@app.route('/api/workspaces', methods=['GET'])
def get_workspaces():
    """列出所有工作区。"""
    return jsonify({"workspaces": list_workspaces(), "current": normalize_workspace_id()})


@app.route('/api/workspaces', methods=['POST'])
def create_workspace():
    """创建新工作区。"""
    body = request.get_json() or {}
    workspace_id = str(body.get('id') or '').strip()
    name = str(body.get('name') or workspace_id).strip()
    if not workspace_id or not validate_workspace_id(workspace_id):
        return jsonify({"error": "workspace id 只能包含字母、数字、短横线和下划线"}), 400
    if workspace_id in {item['id'] for item in list_workspaces()}:
        return jsonify({"error": "工作区已存在"}), 409
    ensure_workspace(workspace_id, name or workspace_id)
    return jsonify({"status": "ok", "workspace": next(w for w in list_workspaces() if w['id'] == workspace_id)})


@app.route('/api/workspaces/<workspace_id>', methods=['PUT'])
def rename_workspace(workspace_id):
    """重命名工作区显示名称。"""
    if not validate_workspace_id(workspace_id):
        return jsonify({"error": "Invalid workspace id"}), 400
    body = request.get_json() or {}
    name = str(body.get('name') or '').strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    ensure_workspace(workspace_id)
    meta = read_workspaces_meta()
    meta['workspaces'][workspace_id]['name'] = name
    meta['workspaces'][workspace_id]['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    write_workspaces_meta(meta)
    return jsonify({"status": "ok", "workspace": meta['workspaces'][workspace_id]})


@app.route('/api/workspaces/<workspace_id>', methods=['DELETE'])
def delete_workspace(workspace_id):
    """删除工作区。默认工作区不允许删除。"""
    if not validate_workspace_id(workspace_id):
        return jsonify({"error": "Invalid workspace id"}), 400
    if workspace_id == DEFAULT_WORKSPACE_ID:
        return jsonify({"error": "默认工作区不能删除"}), 400
    existing = {item['id'] for item in list_workspaces()}
    if workspace_id not in existing:
        return jsonify({"error": "工作区不存在"}), 404
    shutil.rmtree(workspace_dir(workspace_id), ignore_errors=True)
    meta = read_workspaces_meta()
    meta.get('workspaces', {}).pop(workspace_id, None)
    write_workspaces_meta(meta)
    remaining = list_workspaces()
    return jsonify({"status": "ok", "workspaces": remaining, "fallback": remaining[0]['id'] if remaining else DEFAULT_WORKSPACE_ID})


# ============ API ============

@app.route('/api/slides', methods=['GET'])
def get_slides():
    return jsonify(load_slides())


@app.route('/api/slides', methods=['POST'])
def save_all_slides():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    data.setdefault('settings', {})
    data.setdefault('slides', [])
    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version})


@app.route('/api/slides/<slide_id>', methods=['PUT'])
def update_slide(slide_id):
    data = load_slides()
    slide_data = request.get_json() or {}
    if not isinstance(slide_data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    idx, _ = find_slide(data, slide_id)
    if idx >= 0:
        data['slides'][idx] = slide_data
        version = save_slides(data, expected_version=_extract_base_version())
        return jsonify({"status": "ok", "_version": version})
    return jsonify({"error": "Slide not found"}), 404


@app.route('/api/slides/<slide_id>', methods=['DELETE'])
def delete_slide(slide_id):
    data = load_slides()
    original_len = len(data.get('slides', []))
    data['slides'] = [s for s in data['slides'] if str(s.get('id')) != str(slide_id)]
    if len(data['slides']) == original_len:
        return jsonify({"error": "Slide not found"}), 404
    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version})


@app.route('/api/slides/reorder', methods=['POST'])
def reorder_slides():
    data = load_slides()
    body = request.get_json() or {}
    order = body.get('order', [])
    if not isinstance(order, list):
        return jsonify({"error": "order must be a list"}), 400

    slides = data.get('slides', [])
    slide_map = {str(s.get('id')): s for s in slides}
    seen = set()
    reordered = []
    unknown = []

    for sid in order:
        key = str(sid)
        if key in seen:
            continue
        if key in slide_map:
            reordered.append(slide_map[key])
            seen.add(key)
        else:
            unknown.append(sid)

    # 漏传的幻灯片保留在末尾，避免重排请求意外删除页面。
    for slide in slides:
        key = str(slide.get('id'))
        if key not in seen:
            reordered.append(slide)

    data['slides'] = reordered
    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version, "unknown": unknown})


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No filename"}), 400
    if file and allowed_file(file.filename):
        # secure_filename 会清掉中文字符，这里保留 Unicode 仅替换路径分隔符与危险字符
        raw_name = os.path.basename(file.filename)
        # 去掉路径分隔符、控制字符，保留中文等 Unicode
        safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', raw_name).strip('._') or 'upload'
        name, ext = os.path.splitext(safe_name)
        # 添加时间戳避免冲突
        filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        # 路径穿越防护
        upload_root = os.path.realpath(app.config['UPLOAD_FOLDER'])
        filepath = os.path.realpath(os.path.join(upload_root, filename))
        if not filepath.startswith(upload_root + os.sep):
            abort(403)
        file.save(filepath)
        return jsonify({
            "url": f"/static/uploads/{filename}",
            "filename": filename
        })
    return jsonify({"error": "File type not allowed"}), 400


@app.route('/api/image-info', methods=['GET'])
def get_image_info():
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "Missing url parameter"}), 400
    filename = url.split('/')[-1] if '/' in url else url
    # 路径穿越防护：解析后必须仍在上传目录内
    upload_root = os.path.realpath(app.config['UPLOAD_FOLDER'])
    filepath = os.path.realpath(os.path.join(upload_root, filename))
    if not filepath.startswith(upload_root + os.sep):
        logger.warning("图片信息路径穿越: url=%s, filepath=%s", url, filepath)
        abort(403)
    if not os.path.exists(filepath):
        return jsonify({"error": f"File not found: {filename}"}), 404
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            return jsonify({
                "filename": filename,
                "width": img.width,
                "height": img.height,
                "aspect_ratio": round(img.width / img.height, 4) if img.height > 0 else 0,
                "url": f"/static/uploads/{filename}"
            })
    except Exception as e:
        return jsonify({"error": f"Cannot read image: {str(e)}"}), 500


# ============ 版本号 API ============

def get_slides_version(workspace_id=None):
    """快速获取幻灯片版本号，只读取文件头部，避免完整解析 JSON 大文件"""
    try:
        wid = normalize_workspace_id(workspace_id)
        data_file = workspace_data_file(wid)
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                head = f.read(1024)
            match = re.search(r'"_version"\s*:\s*(\d+)', head)
            if match:
                return int(match.group(1))
            # 备用方案：完整解析
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('_version', 0)
    except Exception:
        pass
    return 0


@app.route('/api/version', methods=['GET'])
def get_version():
    try:
        workspace_id = normalize_workspace_id()
        version = get_slides_version(workspace_id)
    except ValueError:
        return jsonify({"error": "Invalid workspace id"}), 400
    return jsonify({"_version": version})


# ============ 组件 API ============

# 启动期缓存的 components 模块引用，避免每次请求重复 sys.path.insert + import
_CACHED_COMPONENTS_MODULE = None
_COMPONENTS_PATH_INITIALIZED = False


def get_components_module():
    global _CACHED_COMPONENTS_MODULE, _COMPONENTS_PATH_INITIALIZED
    if _CACHED_COMPONENTS_MODULE is not None:
        return _CACHED_COMPONENTS_MODULE
    import sys
    from pathlib import Path
    if not _COMPONENTS_PATH_INITIALIZED:
        editor_path = str(Path(__file__).resolve().parent / SLIDE_EDITOR_PATH)
        if editor_path not in sys.path:
            sys.path.insert(0, editor_path)
        _COMPONENTS_PATH_INITIALIZED = True
    try:
        import components
        _CACHED_COMPONENTS_MODULE = components
        return components
    except ImportError as e:
        logger.error("导入 components 模块失败: %s", e)
        return None


CUSTOM_COMPONENTS_FILE = os.path.join(app.root_path, 'data', 'custom_components.json')


def load_custom_components():
    if os.path.exists(CUSTOM_COMPONENTS_FILE):
        try:
            with open(CUSTOM_COMPONENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error("加载 custom_components.json 失败: %s", e)
            return []
    return []


def save_custom_components(components):
    try:
        os.makedirs(os.path.dirname(CUSTOM_COMPONENTS_FILE), exist_ok=True)
        with open(CUSTOM_COMPONENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(components, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("保存 custom_components.json 失败: %s", e)
        return False


@app.route('/api/components/custom', methods=['POST'])
def add_custom_component():
    body = request.get_json() or {}
    name = body.get('name')
    display_name = body.get('displayName', name)
    description = body.get('description', '')
    html = body.get('html', '')
    css = body.get('css', '')
    default_size = body.get('default_size', {'width': 300, 'height': 200})
    canvas_elements = body.get('canvas_elements', [])
    
    if not name:
        return jsonify({"error": "name is required"}), 400
        
    components = load_custom_components()
    # Check if duplicate name
    components = [c for c in components if c.get('name') != name]
    
    components.append({
        "name": name,
        "displayName": display_name,
        "description": description,
        "html": html,
        "css": css,
        "default_size": default_size,
        "canvas_elements": canvas_elements,
        "is_custom": True
    })
    
    if save_custom_components(components):
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Failed to save component"}), 500


@app.route('/api/components/custom/<name>', methods=['DELETE'])
def delete_custom_component(name):
    components = load_custom_components()
    original_len = len(components)
    components = [c for c in components if c.get('name') != name]
    if len(components) == original_len:
        return jsonify({"error": "Component not found"}), 404
        
    if save_custom_components(components):
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Failed to delete component"}), 500


# 组件默认数据/尺寸缓存（从 default_data.json 加载，避免每次请求重复解析）
_COMPONENT_DEFAULTS_CACHE = None


def _load_component_defaults():
    """加载组件默认数据与尺寸，启动后缓存。"""
    global _COMPONENT_DEFAULTS_CACHE
    if _COMPONENT_DEFAULTS_CACHE is not None:
        return _COMPONENT_DEFAULTS_CACHE
    from pathlib import Path
    defaults_file = Path(__file__).resolve().parent / SLIDE_EDITOR_PATH / 'components' / 'default_data.json'
    empty = ({}, {})
    if not defaults_file.exists():
        _COMPONENT_DEFAULTS_CACHE = empty
        return empty
    try:
        with open(defaults_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        default_data = raw.get('default_data', {})
        default_sizes = raw.get('default_sizes', {})
        _COMPONENT_DEFAULTS_CACHE = (default_data, default_sizes)
        return _COMPONENT_DEFAULTS_CACHE
    except Exception as e:
        logger.error("加载 default_data.json 失败: %s", e)
        _COMPONENT_DEFAULTS_CACHE = empty
        return empty


@app.route('/api/components', methods=['GET'])
def get_components():
    mod = get_components_module()
    if not mod:
        return jsonify(load_custom_components())

    DEFAULT_DATA, DEFAULT_SIZES = _load_component_defaults()

    results = []
    for name, item in mod.COMPONENTS.items():
        data = DEFAULT_DATA.get(name, {})
        size = DEFAULT_SIZES.get(name, { "width": 300, "height": 200 })
        try:
            rendered = mod.render_component(name, data)
            html = rendered.get("html", "")
            css = rendered.get("css", "")
        except Exception as e:
            logger.error("渲染组件 %s 失败: %s", name, e)
            html = ""
            css = ""
        results.append({
            "name": name,
            "description": item.get("description", ""),
            "default_data": data,
            "default_size": size,
            "html": html,
            "css": css
        })
    # Append custom components
    results.extend(load_custom_components())
    return jsonify(results)


@app.route('/api/components/render', methods=['POST'])
def render_component_api():
    mod = get_components_module()
    if not mod:
        return jsonify({"error": "Components module not available"}), 500
    
    body = request.get_json() or {}
    name = body.get('name')
    data = body.get('data', {})
    
    if not name or name not in mod.COMPONENTS:
        return jsonify({"error": f"Unknown component: {name}"}), 400
    
    try:
        rendered = mod.render_component(name, data)
        return jsonify(rendered)
    except Exception as e:
        return jsonify({"error": f"Render failed: {str(e)}"}), 400


# ============ 幻灯片创建 API ============

@app.route('/api/slides/create', methods=['POST'])
def create_slide():
    """在指定位置插入新幻灯片"""
    data = load_slides()
    body = request.get_json() or {}
    index = parse_index(body.get('index'), -1)
    slide_template = body.get('slide', {})
    if not isinstance(slide_template, dict):
        return jsonify({"error": "slide must be a JSON object"}), 400

    new_slide = {
        "id": generate_slide_id(),
        "layout": slide_template.get('layout', ''),
        "theme": slide_template.get('theme', 'light'),
        "animate": slide_template.get('animate', ''),
        "backgroundColor": slide_template.get('backgroundColor', '#fafaf8'),
        "bgPatternColor": slide_template.get('bgPatternColor', ''),
        "chrome": slide_template.get('chrome', {"left": "", "right": ""}),
        "content": slide_template.get('content', {}),
        "foot": slide_template.get('foot', {"left": "", "center": "", "right": ""}),
        "images": slide_template.get('images', []),
        "custom_style": slide_template.get('custom_style', {}),
        "canvas_elements": slide_template.get('canvas_elements', [])
    }
    if not isinstance(new_slide["canvas_elements"], list):
        return jsonify({"error": "slide.canvas_elements must be a list"}), 400

    if index < 0 or index >= len(data['slides']):
        data['slides'].append(new_slide)
    else:
        data['slides'].insert(index, new_slide)

    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version, "slide": new_slide})


# ============ 元素级 CRUD API ============

@app.route('/api/slides/<slide_id>/elements', methods=['GET'])
def get_elements(slide_id):
    """获取幻灯片的所有元素"""
    data = load_slides()
    _, slide = find_slide(data, slide_id)
    if slide is None:
        return jsonify({"error": "Slide not found"}), 404
    return jsonify({
        "elements": slide.get('canvas_elements', []),
        "backgroundColor": slide.get('backgroundColor', '#fafaf8')
    })


@app.route('/api/slides/<slide_id>/elements', methods=['POST'])
def add_element(slide_id):
    """添加元素到幻灯片"""
    data = load_slides()
    idx, slide = find_slide(data, slide_id)
    if slide is None:
        return jsonify({"error": "Slide not found"}), 404

    body = request.get_json() or {}
    element = body.get('element', {})
    index = parse_index(body.get('index'), -1)
    if not isinstance(element, dict):
        return jsonify({"error": "element must be a JSON object"}), 400

    # 确保元素有类型
    if 'type' not in element:
        return jsonify({"error": "Element type is required"}), 400

    if 'canvas_elements' not in slide:
        slide['canvas_elements'] = []

    ok, error = ensure_element_id(element, collect_element_ids(slide))
    if not ok:
        return jsonify({"error": error}), 409

    if index < 0 or index >= len(slide['canvas_elements']):
        slide['canvas_elements'].append(element)
    else:
        slide['canvas_elements'].insert(index, element)

    data['slides'][idx] = slide
    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version, "element": element})


@app.route('/api/slides/<slide_id>/elements/<elem_id>', methods=['PUT'])
def update_element(slide_id, elem_id):
    """更新元素属性（部分更新）"""
    data = load_slides()
    slide_idx, slide = find_slide(data, slide_id)
    if slide is None:
        return jsonify({"error": "Slide not found"}), 404

    elements = slide.get('canvas_elements', [])
    elem_idx = -1
    for i, elem in enumerate(elements):
        if elem.get('id') == elem_id:
            elem_idx = i
            break

    if elem_idx < 0:
        return jsonify({"error": "Element not found"}), 404

    body = request.get_json() or {}
    properties = body.get('properties', {})
    if not isinstance(properties, dict):
        return jsonify({"error": "properties must be a JSON object"}), 400

    original_type = elements[elem_idx].get('type')
    # 部分更新：只修改传入的属性
    elements[elem_idx].update(properties)
    # 不允许修改 id 和 type
    elements[elem_idx]['id'] = elem_id
    elements[elem_idx]['type'] = original_type

    data['slides'][slide_idx]['canvas_elements'] = elements
    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version, "element": elements[elem_idx]})


@app.route('/api/slides/<slide_id>/elements/<elem_id>', methods=['DELETE'])
def delete_element(slide_id, elem_id):
    """删除元素"""
    data = load_slides()
    slide_idx, slide = find_slide(data, slide_id)
    if slide is None:
        return jsonify({"error": "Slide not found"}), 404

    elements = slide.get('canvas_elements', [])
    original_len = len(elements)
    elements = [e for e in elements if e.get('id') != elem_id]

    if len(elements) == original_len:
        return jsonify({"error": "Element not found"}), 404

    data['slides'][slide_idx]['canvas_elements'] = elements
    version = save_slides(data, expected_version=_extract_base_version())
    return jsonify({"status": "ok", "_version": version})


@app.route('/api/slides/<slide_id>/elements/batch', methods=['POST'])
def batch_elements(slide_id):
    """批量操作元素"""
    data = load_slides()
    slide_idx, slide = find_slide(data, slide_id)
    if slide is None:
        return jsonify({"error": "Slide not found"}), 404

    if 'canvas_elements' not in slide:
        slide['canvas_elements'] = []

    body = request.get_json() or {}
    if isinstance(body, list):
        operations = body
    elif isinstance(body, dict):
        operations = body.get('operations', [])
    else:
        return jsonify({"error": "request body must be an object with operations or an operations array"}), 400
    if not isinstance(operations, list):
        return jsonify({"error": "operations must be a list"}), 400
    results = []
    used_ids = collect_element_ids(slide)

    for op in operations:
        if not isinstance(op, dict):
            results.append({"action": None, "status": "error", "error": "Operation must be a JSON object"})
            continue
        action = op.get('action')
        if action is None and op.get('type') in {'add', 'update', 'delete'}:
            action = op.get('type')

        if action == 'add':
            element = op.get('element', {})
            if not isinstance(element, dict):
                results.append({"action": "add", "status": "error", "error": "element must be a JSON object"})
                continue
            if 'type' not in element:
                results.append({"action": "add", "status": "error", "error": "Element type is required"})
                continue
            ok, error = ensure_element_id(element, used_ids)
            if not ok:
                results.append({"action": "add", "status": "error", "error": error})
                continue
            index = parse_index(op.get('index'), -1)
            if index < 0 or index >= len(slide['canvas_elements']):
                slide['canvas_elements'].append(element)
            else:
                slide['canvas_elements'].insert(index, element)
            results.append({"action": "add", "status": "ok", "element": element})

        elif action == 'update':
            elem_id = op.get('id')
            properties = op.get('properties', {})
            if not isinstance(properties, dict):
                results.append({"action": "update", "status": "error", "error": "properties must be a JSON object"})
                continue
            found = False
            for i, elem in enumerate(slide['canvas_elements']):
                if elem.get('id') == elem_id:
                    original_type = slide['canvas_elements'][i].get('type')
                    slide['canvas_elements'][i].update(properties)
                    slide['canvas_elements'][i]['id'] = elem_id
                    slide['canvas_elements'][i]['type'] = original_type
                    results.append({"action": "update", "status": "ok", "element": slide['canvas_elements'][i]})
                    found = True
                    break
            if not found:
                results.append({"action": "update", "status": "error", "error": f"Element {elem_id} not found"})

        elif action == 'delete':
            elem_id = op.get('id')
            original_len = len(slide['canvas_elements'])
            slide['canvas_elements'] = [e for e in slide['canvas_elements'] if e.get('id') != elem_id]
            if len(slide['canvas_elements']) < original_len:
                results.append({"action": "delete", "status": "ok"})
            else:
                results.append({"action": "delete", "status": "error", "error": f"Element {elem_id} not found"})

        else:
            results.append({
                "action": action,
                "status": "error",
                "error": "Unknown action. Use action=add|update|delete; for add element type belongs in element.type"
            })

    data['slides'][slide_idx] = slide
    version = save_slides(data, expected_version=_extract_base_version())
    has_errors = any(item.get('status') == 'error' for item in results)
    return jsonify({"status": "partial" if has_errors else "ok", "_version": version, "results": results})


@app.route('/api/export', methods=['GET'])
def export_html():
    """导出为独立 HTML 文件"""
    workspace_id = normalize_workspace_id()
    data = load_slides(workspace_id)
    clean_data = sanitize_text_in_data(data)
    slides_html = render_template(
        'presentation.html',
        slides=clean_data.get('slides', []),
        settings=clean_data.get('settings', {}),
        export_data_json=make_export_data_json(clean_data),
        workspace_id=workspace_id
    )
    export_dir = workspace_export_folder(workspace_id)
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, 'index.html')
    with open(export_path, 'w', encoding='utf-8') as f:
        f.write(slides_html)
    return jsonify({
        "status": "ok",
        "workspace": workspace_id,
        "path": export_path.replace('\\', '/'),
        "url": f"/workspace/{workspace_id}/ppt/index.html"
    })


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """打开导出的文件夹"""
    import sys
    import subprocess
    workspace_id = normalize_workspace_id()
    export_dir = os.path.abspath(workspace_export_folder(workspace_id))
    
    if not os.path.exists(export_dir):
        return jsonify({"error": f"文件夹不存在: {export_dir}"}), 404
        
    try:
        if os.name == 'nt':
            os.startfile(export_dir)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', export_dir])
        else:
            subprocess.Popen(['xdg-open', export_dir])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/import', methods=['POST'])
def import_data():
    """从新版 HTML 内嵌的编辑数据导入幻灯片。"""
    workspace_id = normalize_workspace_id()
    body = request.get_json() or {}
    mode = body.get('mode')
    if mode not in ('replace', 'append'):
        return jsonify({"error": "mode must be replace or append"}), 400

    imported, error = normalize_import_data(body.get('data'))
    if error:
        return jsonify({"error": error}), 400

    current = load_slides(workspace_id)
    if mode == 'replace':
        next_data = imported
        rewritten_ids = False
    else:
        appended = rewrite_import_ids(imported, current)
        next_data = copy.deepcopy(current)
        if not isinstance(next_data.get('settings'), dict):
            next_data['settings'] = imported.get('settings', {})
        next_data.setdefault('slides', [])
        next_data['slides'].extend(appended.get('slides', []))
        rewritten_ids = True

    version = save_slides(next_data, workspace_id, expected_version=_extract_base_version())
    return jsonify({
        "status": "ok",
        "workspace": workspace_id,
        "_version": version,
        "mode": mode,
        "imported": len(imported.get('slides', [])),
        "rewritten_ids": rewritten_ids
    })


@app.route('/slide/<slide_id>')
def view_single_slide(slide_id):
    """渲染单张幻灯片，用于导出或截图"""
    workspace_id = normalize_workspace_id()
    data = load_slides(workspace_id)
    clean_data = sanitize_text_in_data(data)
    idx, slide = find_slide(clean_data, slide_id)
    if slide is None:
        return "Slide not found", 404
    return render_template(
        'presentation.html',
        slides=[slide],
        settings=clean_data.get('settings', {}),
        is_single=True,
        slide_index=idx + 1,
        total_slides=len(clean_data.get('slides', [])),
        workspace_id=workspace_id
    )


@app.route('/workspace/<workspace_id>/ppt/<path:filename>')
def serve_workspace_export(workspace_id, filename):
    """访问指定工作区的导出文件。"""
    if not validate_workspace_id(workspace_id):
        return "Invalid workspace id", 400
    return send_from_directory(workspace_export_folder(workspace_id), filename)


if __name__ == '__main__':
    # 默认仅监听本机，避免 Werkzeug 调试器暴露到外网导致远程代码执行。
    # 需要分享时显式设置 FLASK_HOST=0.0.0.0，且务必 FLASK_DEBUG=0。
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
    HOST = os.environ.get('FLASK_HOST', '127.0.0.1')
    PORT = int(os.environ.get('FLASK_PORT', '5001'))
    if HOST == '0.0.0.0' and DEBUG:
        logger.warning("检测到 FLASK_HOST=0.0.0.0 且 FLASK_DEBUG=1，正在强制关闭 debug 以避免远程代码执行风险。")
        DEBUG = False
    if HOST == '0.0.0.0' and not AUTH_TOKEN:
        logger.error("FLASK_HOST=0.0.0.0 监听外网但未设置 QIAN_PPT_TOKEN，写操作将无认证暴露。")
        logger.error("请设置环境变量 QIAN_PPT_TOKEN=<你的密码> 后再启动，或改用 FLASK_HOST=127.0.0.1。")
        raise SystemExit(1)
    logger.info("=" * 50)
    logger.info("Qian-PPT 启动中...")
    logger.info("监听地址: %s:%s (debug=%s)", HOST, PORT, DEBUG)
    logger.info("认证状态: %s", "已启用 (QIAN_PPT_TOKEN)" if AUTH_TOKEN else "未启用 (本地零配置)")
    logger.info("日志目录: %s", os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log'))
    logger.info("=" * 50)
    app.run(debug=DEBUG, host=HOST, port=PORT)
