"""
إدارة الإعدادات — Settings Management with validation
مدمج: production config.yaml + new typed config system
"""
import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from functools import lru_cache

try:
    from pydantic import BaseModel, Field
except ImportError:
    # Fallback for older pydantic or when not installed
    BaseModel = object
    def Field(*args, **kwargs):
        return None
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    BaseSettings = object
    SettingsConfigDict = dict

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# الإعدادات الافتراضية — تضمن ما يطير الكود لو key ناقص
DEFAULTS = {
    "ai": {
        "model": "deepseek-v4-flash",
        "provider": "opencode-go",
        "api_base": "https://opencode.ai/zen/v1/chat/completions",
    },
    "bot": {},
    "market": {"enabled": False},
    "publisher": {"delay_between_posts": 10, "max_posts_per_cycle": 3},
    "scheduler": {"interval_minutes": 10, "news_window_hours": 3},
    "logging": {"level": "INFO", "file": "/var/log/YJCryptoNews/bot.log"},
    "sources": [],
}

# المتغيرات البيئية المعتمدة (ما نقرأ من .env مباشرة)
ENV_MAP = {
    "AI_API_KEY": ("ai", "api_key"),
    "AI_API_KEY_2": ("ai", "api_key_2"),
    "AI_API_KEY_3": ("ai", "api_key_3"),
    "AI_FALLBACK_KEY": ("ai", "fallback_api_key"),
    "AI_FALLBACK_KEY_2": ("ai", "fallback_api_key_2"),
    "AI_FALLBACK_KEY_3": ("ai", "fallback_api_key_3"),
    "AI_FALLBACK_KEY_4": ("ai", "fallback_api_key_4"),
    "AI_FALLBACK_KEY_5": ("ai", "fallback_api_key_5"),
    "AI_FALLBACK_KEY_6": ("ai", "fallback_api_key_6"),
    "BOT_TOKEN": ("bot", "token"),
    "AI_API_BASE": ("ai", "api_base"),
}

# Extra mapping: BOT_TOKEN also goes to publishing.telegram.bot_token
EXTRA_ENV_MAP = {
    "BOT_TOKEN": ("publishing.telegram", "bot_token"),
}

ENV_PATH = Path(__file__).parent.parent / ".env"


def _load_dotenv():
    """تحميل .env إلى environment variables (مرة وحدة عند الاستيراد)"""
    if not ENV_PATH.exists():
        return
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and key not in os.environ:
                    os.environ[key] = val


def _set_nested(d: dict, path: str, key: str, val: Any):
    """Set value in nested dict using dot-separated path"""
    parts = path.split(".")
    curr = d
    for part in parts[:-1]:
        if part not in curr or not isinstance(curr[part], dict):
            curr[part] = {}
        curr = curr[part]
    # Handle the last part
    if parts[-1] not in curr or not isinstance(curr[parts[-1]], dict):
        curr[parts[-1]] = {}
    curr[parts[-1]][key] = val


def _load_env() -> dict:
    """تحميل المتغيرات من Environment Variables"""
    env = {}
    for env_key in ENV_MAP:
        val = os.environ.get(env_key, "")
        if val:
            section, key = ENV_MAP[env_key]
            _set_nested(env, section, key, val)
    # Apply EXTRA_ENV_MAP
    for env_key, (section, key) in EXTRA_ENV_MAP.items():
        val = os.environ.get(env_key, "")
        if val:
            _set_nested(env, section, key, val)
    return env


def _deep_merge(base: dict, override: dict) -> dict:
    """دمج قاموسين بعمق — override يعلو base (يتجاوز None)"""
    result = dict(base)
    for key, val in override.items():
        if val is None:
            continue  # نتجاوز القيم الفارغة — نحتفظ بالافتراضي
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _apply_env_overrides(cfg: dict, env: dict) -> dict:
    """تطبيق متغيرات البيئة على الإعدادات"""
    for section, vals in env.items():
        if section not in cfg or cfg[section] is None:
            cfg[section] = {}
        # Deep merge for nested sections
        if isinstance(vals, dict) and isinstance(cfg[section], dict):
            cfg[section] = _deep_merge(cfg[section], vals)
        else:
            cfg[section].update(vals)
    return cfg


def load() -> dict:
    """تحميل الإعدادات: defaults ← config.yaml ← environment variables"""
    # 1. تحميل .env إلى البيئة
    _load_dotenv()

    # 2. نبدأ من defaults
    cfg = _deep_merge({}, DEFAULTS)

    # 3. ندمج من config.yaml (إن وجد) — يحافظ على هيكل الإنتاج
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
            cfg = _deep_merge(cfg, file_cfg)

    # 4. environment variables تتجاوز كل شي
    env = _load_env()
    cfg = _apply_env_overrides(cfg, env)

    return cfg


def save(cfg: dict):
    """حفظ الإعدادات إلى config.yaml (بدون مفاتيح سرية)"""
    to_save = _deep_merge({}, cfg)
    if "ai" in to_save:
        to_save["ai"].pop("api_key", None)
    if "bot" in to_save:
        to_save["bot"].pop("token", None)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(to_save, f, default_flow_style=False, allow_unicode=True)


# ============================================================
# NEW: Typed Settings System (Pydantic) -Compatible with both
# ============================================================

class Settings:
    """Unified settings wrapper - provides both dict and typed access with nested access"""
    
    def __init__(self, cfg: dict = None):
        self._cfg = cfg if cfg is not None else load()
    
    def __getattr__(self, name: str) -> Any:
        val = self._cfg.get(name)
        if isinstance(val, dict):
            return Settings(val)  # Return nested Settings for dict values
        return val
    
    def __getitem__(self, key: str) -> Any:
        val = self._cfg.get(key)
        if isinstance(val, dict):
            return Settings(val)
        return val
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._cfg.get(key, default)
    
    def update(self, updates: dict):
        self._cfg = _deep_merge(self._cfg, updates)
    
    def dict(self) -> dict:
        return self._cfg


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# For backward compatibility
# Use different name to not override the config module
_settings_instance = get_settings()

# Export settings for backward compatibility
settings = _settings_instance

# Alias for new typed access
load_config = load  # Legacy function name