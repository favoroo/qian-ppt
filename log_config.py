"""日志系统配置模块。

功能：
- 按日期创建日志文件（log/YYYY-MM-DD.log），午夜自动切换
- 按大小轮转（单文件超 MAX_FILE_SIZE 时重命名为 YYYY-MM-DD.HHMMSS.log）
- QueueHandler 异步写入，主线程零阻塞
- 控制台彩色输出，文件纯文本
- 自动清理超过 LOG_RETENTION_DAYS 天的日志
- 通过 LOG_LEVEL 环境变量控制级别（默认 INFO）
"""
from __future__ import annotations

import os
import sys
import glob
import atexit
import logging
from queue import Queue
from datetime import datetime, timedelta
from logging.handlers import QueueHandler, QueueListener

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
MAX_FILE_SIZE = 10 * 1024 * 1024        # 10MB，单文件大小上限
MAX_BACKUP_COUNT = 5                     # 单日按大小轮转的备份文件数上限
LOG_RETENTION_DAYS = 30                  # 日志保留天数
DEFAULT_LOG_LEVEL = logging.INFO

# ANSI 颜色码
_RESET = '\033[0m'
_COLORS = {
    logging.DEBUG: '\033[37m',      # 灰色
    logging.INFO: '\033[32m',       # 绿色
    logging.WARNING: '\033[33m',    # 黄色
    logging.ERROR: '\033[31m',      # 红色
    logging.CRITICAL: '\033[41m',   # 红底
}


class ColoredFormatter(logging.Formatter):
    """控制台彩色格式化器，按日志级别添加 ANSI 颜色。"""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelno, '')
        message = super().format(record)
        return f'{color}{message}{_RESET}' if color else message


class DailyDateFileHandler(logging.Handler):
    """按日期命名日志文件并在午夜自动切换的 handler。

    文件命名：log/YYYY-MM-DD.log
    日期变化时自动切换到新文件。
    单日文件超过 MAX_FILE_SIZE 时轮转为 YYYY-MM-DD.HHMMSS.log，
    保留最近 MAX_BACKUP_COUNT 个轮转备份。
    """

    def __init__(self, log_dir: str = _LOG_DIR,
                 max_bytes: int = MAX_FILE_SIZE,
                 backup_count: int = MAX_BACKUP_COUNT,
                 encoding: str = 'utf-8'):
        super().__init__()
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.encoding = encoding
        self._current_date: str | None = None
        self._current_path: str | None = None
        self._stream = None
        os.makedirs(self.log_dir, exist_ok=True)
        self._open_stream()

    # -- 内部方法 ----------------------------------------------------------
    @staticmethod
    def _today() -> str:
        return datetime.now().strftime('%Y-%m-%d')

    def _open_stream(self) -> None:
        """打开当天日志文件流。"""
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
        self._current_date = self._today()
        self._current_path = os.path.join(self.log_dir, f'{self._current_date}.log')
        self._stream = open(self._current_path, 'a', encoding=self.encoding)

    def _should_rotate_by_size(self) -> bool:
        """检查当前文件是否超过大小上限。"""
        try:
            return os.path.getsize(self._current_path) >= self.max_bytes
        except OSError:
            return False

    def _rotate_by_size(self) -> None:
        """按大小轮转：重命名当前文件，清理旧备份，打开新文件。"""
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        timestamp = datetime.now().strftime('%H%M%S')
        backup_path = os.path.join(self.log_dir, f'{self._current_date}.{timestamp}.log')
        try:
            os.rename(self._current_path, backup_path)
        except OSError:
            pass
        self._cleanup_old_backups(self._current_date)
        self._stream = open(self._current_path, 'a', encoding=self.encoding)

    def _cleanup_old_backups(self, date_str: str) -> None:
        """清理指定日期超出备份数的轮转文件。"""
        pattern = os.path.join(self.log_dir, f'{date_str}.*.log')
        backups = sorted(glob.glob(pattern))
        while len(backups) > self.backup_count:
            try:
                os.remove(backups.pop(0))
            except OSError:
                break

    # -- Handler 接口 ------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # 日期变化 → 切换文件
            today = self._today()
            if today != self._current_date:
                self._open_stream()
            # 大小超限 → 轮转
            elif self._should_rotate_by_size():
                self._rotate_by_size()
            msg = self.format(record)
            self._stream.write(msg + '\n')
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        super().close()


def cleanup_old_logs(log_dir: str = _LOG_DIR,
                     retention_days: int = LOG_RETENTION_DAYS) -> None:
    """清理超过保留期的日志文件。"""
    if not os.path.isdir(log_dir):
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for filepath in glob.glob(os.path.join(log_dir, '*.log')):
        filename = os.path.basename(filepath)
        # 从文件名解析日期：YYYY-MM-DD.log 或 YYYY-MM-DD.HHMMSS.log
        date_str = filename[:10]
        try:
            file_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(filepath)
            except OSError:
                pass


def setup_logging(level: int | None = None) -> logging.Logger:
    """配置全局日志系统。

    - 创建 log/ 目录
    - 清理过期日志
    - 安装文件 handler（按日期+大小轮转）和控制台 handler（彩色）
    - 使用 QueueHandler 异步写入，主线程零阻塞
    """
    if level is None:
        env_level = os.environ.get('LOG_LEVEL', '').upper()
        level = getattr(logging, env_level, DEFAULT_LOG_LEVEL)

    os.makedirs(_LOG_DIR, exist_ok=True)
    cleanup_old_logs()

    # 文件 handler（纯文本）
    file_handler = DailyDateFileHandler()
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    # 控制台 handler（彩色）
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(ColoredFormatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    # QueueHandler 异步：主线程只入队，后台线程负责 I/O
    log_queue: Queue = Queue(-1)  # 无界队列
    queue_handler = QueueHandler(log_queue)
    listener = QueueListener(log_queue, file_handler, console_handler)
    listener.start()
    atexit.register(listener.stop)

    # 配置 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # 移除已有 handler，避免重复输出
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    root_logger.addHandler(queue_handler)

    return root_logger


def get_logger(name: str = 'qian-ppt') -> logging.Logger:
    """获取已配置的 logger。"""
    return logging.getLogger(name)
