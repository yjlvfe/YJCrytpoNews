""""📝 نظام تسجيل محترف — بديل print() مع مستويات وتوقيت وملف"""
import sys
import os
import logging
import logging.handlers
import threading
from pathlib import Path
from datetime import datetime
from . import config

# ثابت عشان نتأكد ننشئ الـ logger مرة وحدة
_loggers = {}
_lock = threading.Lock()
_ROOT_LOGGER = None


def setup_logging():
    """إعداد logging مركزي — يستدعى مرة وحدة عند بداية البرنامج"""
    global _ROOT_LOGGER

    with _lock:
        if _ROOT_LOGGER is not None:
            return _ROOT_LOGGER

        cfg = config.load()
        log_cfg = cfg.get("logging", {})
        level_name = (log_cfg.get("level", "INFO") or "INFO").upper()
        log_file = log_cfg.get("file", "/var/log/YJCryptoNews/bot.log")
        log_level = getattr(logging, level_name, logging.INFO)

        # تأكد من وجود مجلد السجل
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # formatter موحد
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Handlers
        handlers = []

        # 1. ملف
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

        # 2. كونسول (stdout)
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-7s | %(message)s"))
        handlers.append(console)

        # إعداد root logger
        _ROOT_LOGGER = logging.getLogger("yjcryptonews")
        _ROOT_LOGGER.setLevel(log_level)
        # Phase 4: prevent propagation to parent (root) loggers — stops the
        # duplicate emission we saw in /var/log/yjcryptonews.log where every
        # line appeared twice. Without this, any handler attached to the
        # root logger would also receive yjcryptonews.* events.
        _ROOT_LOGGER.propagate = False
        for h in handlers:
            _ROOT_LOGGER.addHandler(h)

        _ROOT_LOGGER.info("📝 نظام التسجيل شغال — level=%s, file=%s", level_name, log_file)
        return _ROOT_LOGGER


def get_logger(name: str = None) -> logging.Logger:
    """الحصول على logger باسم محدد (طفلي من root yjcryptonews)

    Sub-loggers (e.g. "dashboard", "cycle") keep propagate=True (the
    default) so their LogRecords walk up to the yjcryptonews root logger
    where the file/console handlers live. Root logger has propagate=False
    (Phase 4) which stops any further upward propagation — that single
    boundary is enough to prevent double-emission without breaking the
    handler chain.
    """
    global _ROOT_LOGGER
    if _ROOT_LOGGER is None:
        setup_logging()
    if name:
        return logging.getLogger(f"yjcryptonews.{name}")
    return _ROOT_LOGGER or logging.getLogger("yjcryptonews")


def cleanup_old_logs(days: int = 14):
    """تنظيف سجلات أقدم من N يوم"""
    cfg = config.load()
    log_file = cfg.get("logging", {}).get("file", "/var/log/YJCryptoNews/bot.log")
    log_dir = Path(log_file).parent

    if not log_dir.exists():
        return

    now = datetime.now().timestamp()
    cutoff = now - (days * 86400)
    cleaned = 0

    for f in log_dir.glob("*.log*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                cleaned += 1
            except OSError:
                pass

    if cleaned:
        logger = get_logger(__name__)
        logger.info("🧹 تنظيف: %d سجل قديم — أقدم من %d يوم", cleaned, days)
