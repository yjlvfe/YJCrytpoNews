"""🤖 AI Client — Multi-Provider with API Adapters (OpenAI, Ollama, Cohere...)"""
import json
import time
import random
import requests
from .. import config
from ..log import get_logger

logger = get_logger("ai")

USER_AGENT = "YJCryptoNews/1.0 (+https://github.com/yjcryptonews; news aggregator)"

MAX_RETRIES = 2  # Phase 2: was 4 — one retry then move on, prevents 80-min worst case
RETRY_DELAY = 1
MAX_BACKOFF = 30
# Phase 2: was 120. AI responses over 30s are almost always gateway failures.
# Tuple form (connect, read) fails fast on stalled routes.
TIMEOUT = (10, 30)
MIN_SPREAD = 2.0
MAX_SPREAD = 5.0
# Phase 3: hard outer cap on the entire multi-fallback cascade. Even if all
# 10 providers time out internally (10 × 30s = 300s), the cascade returns None
# after this many wall-clock seconds to keep the cycle under cron timeouts.
MAX_CASCADE_SECONDS = 90

_api_key_pool = []
_api_key_index = 0
# Phase 3: signature of the env values used to build _api_key_pool.
# If this changes between calls, the pool is rebuilt so that env edits
# (e.g., AI_API_KEY rotated via `hermes secrets set`) take effect immediately
# instead of being ignored because the pool was cached.
_api_key_pool_signature: tuple = ()

# ========== ADAPTER REGISTRY ==========
API_ADAPTERS = {}


def register_adapter(api_type):
    """Decorator: سجل محول API لنوع معين"""
    def wrapper(fn):
        API_ADAPTERS[api_type] = fn
        return fn
    return wrapper


def call(messages: list, max_tokens: int = 4096, temperature: float = 0.15,
         model_override: str = None, base_override: str = None,
         key_override: str = None, api_type_override: str = None) -> str | None:
    """استدعاء API مع محول تلقائي حسب نوع API"""
    global _api_key_index, _api_key_pool

    cfg = config.load()

    if key_override:
        current_key = key_override
    else:
        # Phase 3: rebuild pool if env values changed (e.g., AI_API_KEY rotated)
        _refresh_api_key_pool_if_stale(cfg)

        if not _api_key_pool:
            logger.error("No AI API key configured")
            return None

        if _api_key_index >= len(_api_key_pool):
            _api_key_index = 0
        current_key = _api_key_pool[_api_key_index]

    model = model_override or cfg.get("ai", {}).get("model", "deepseek-v4-flash")
    api_base = base_override or cfg.get("ai", {}).get("api_base", "")

    if not api_base:
        logger.error("No AI API base URL configured")
        return None

    api_type = api_type_override or "openai"
    adapter = API_ADAPTERS.get(api_type)

    if not adapter:
        logger.error("⚠️ لا يوجد محول لنوع API: %s", api_type)
        return None

    return adapter(messages, model, current_key, api_base, max_tokens, temperature)


# ========== OPENAI ADAPTER (Standard Chat Completions) ==========
@register_adapter("openai")
def _adapter_openai(messages, model, api_key, api_base, max_tokens, temperature):
    """محول OpenAI Chat Completions — يدعم 90%+ من المزودين"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": USER_AGENT,
        "Connection": "keep-alive",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_error = None
    # Phase 2: hoist Session outside retry loop — keep-alive + connection pooling
    session = requests.Session()
    try:
        for attempt in range(MAX_RETRIES):
            try:
                resp = session.post(api_base, json=payload, headers=headers, timeout=TIMEOUT)

                if resp.ok:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = (msg.get("content") or "").strip()
                    reasoning = (msg.get("reasoning_content") or "").strip()

                    if not content and reasoning:
                        logger.warning("AI تفكير طويل (%d حرف) — إعادة توجيه فورية", len(reasoning))
                        fixed_messages = list(messages)
                        if fixed_messages and fixed_messages[0].get("role") == "system":
                            fixed_messages[0]["content"] = fixed_messages[0]["content"] + " أخرج النتيجة مباشرة بدون تفكير. JSON فقط فوراً."
                        else:
                            fixed_messages.insert(0, {"role": "system", "content": "أخرج النتيجة مباشرة بدون تفكير. JSON فقط فوراً."})
                        payload["messages"] = fixed_messages
                        payload["temperature"] = 0.7
                        try:
                            resp2 = session.post(api_base, json=payload, headers=headers, timeout=TIMEOUT)
                            if resp2.ok:
                                data2 = resp2.json()
                                msg2 = data2["choices"][0]["message"]
                                content2 = (msg2.get("content") or "").strip()
                                reasoning2 = (msg2.get("reasoning_content") or "").strip()
                                if content2:
                                    return content2
                                if reasoning2:
                                    logger.warning("AI لا يزال يفكر فقط (%d حرف) — استخدام التفكير كإجابة", len(reasoning2))
                                    return reasoning2
                        except Exception:
                            pass
                        last_error = "reasoning_only"
                        delay = min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF)
                        time.sleep(delay)
                        continue

                    if content:
                        return content

                    logger.warning("AI returned empty content (attempt %d/%d) — تجربة إعادة التوجيه", attempt + 1, MAX_RETRIES)
                    fixed_messages = list(messages)
                    if fixed_messages and fixed_messages[0].get("role") == "system":
                        fixed_messages[0]["content"] = fixed_messages[0]["content"] + " أخرج النتيجة مباشرة بدون تفكير. JSON فقط فوراً."
                    else:
                        fixed_messages.insert(0, {"role": "system", "content": "أخرج النتيجة مباشرة بدون تفكير. JSON فقط فوراً."})
                    payload["messages"] = fixed_messages
                    payload["temperature"] = 0.7
                    try:
                        resp3 = session.post(api_base, json=payload, headers=headers, timeout=TIMEOUT)
                        if resp3.ok:
                            data3 = resp3.json()
                            content3 = (data3["choices"][0]["message"].get("content") or "").strip()
                            if content3:
                                return content3
                    except Exception:
                        pass
                    logger.warning("AI still empty after fix — إرجاع None لتشغيل الفولباك فوراً")
                    return None

                elif resp.status_code == 429:
                    global _api_key_index, _api_key_pool
                    retry_after = resp.headers.get("Retry-After", None)
                    if retry_after:
                        try:
                            backoff = min(int(retry_after), MAX_BACKOFF)
                        except (ValueError, TypeError):
                            backoff = min(RETRY_DELAY * (2 ** attempt) + random.uniform(1, 5), MAX_BACKOFF)
                    else:
                        backoff = min(RETRY_DELAY * (2 ** attempt) + random.uniform(1, 3), MAX_BACKOFF)

                    if len(_api_key_pool) > 1:
                        old_key = _api_key_index
                        _api_key_index = (_api_key_index + 1) % len(_api_key_pool)
                        headers["Authorization"] = f"Bearer {_api_key_pool[_api_key_index]}"
                        logger.warning("⏳ 429 Rate Limited (key %d→%d, model: %s, attempt: %d/%d) — ننتظر %.1f ثانية",
                                       old_key + 1, _api_key_index + 1, model, attempt + 1, MAX_RETRIES, backoff)
                    else:
                        logger.warning("⏳ 429 Rate Limited (model: %s, attempt: %d/%d) — ننتظر %.1f ثانية",
                                       model, attempt + 1, MAX_RETRIES, backoff)
                    last_error = "rate_limited"
                    time.sleep(backoff)
                    continue
                else:
                    logger.error("API error [%d]: %s", resp.status_code, resp.text[:200])
                    last_error = f"HTTP {resp.status_code}"

            except requests.Timeout:
                logger.warning("AI timeout (attempt %d/%d)", attempt + 1, MAX_RETRIES)
                last_error = "timeout"
            except requests.ConnectionError:
                logger.warning("AI connection error (attempt %d/%d)", attempt + 1, MAX_RETRIES)
                last_error = "connection"
            except Exception as e:
                logger.error("AI call failed: %s", e)
                last_error = str(e)

            if attempt < MAX_RETRIES - 1:
                delay = min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF)
                time.sleep(delay)
    finally:
        session.close()
    return None


# ========== OLLAMA ADAPTER ==========
@register_adapter("ollama")
def _adapter_ollama(messages, model, api_key, api_base, max_tokens, temperature):
    """محول Ollama — يستخدم /api/chat بدلاً من /v1/chat/completions"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
        "stream": False,
    }

    # Ollama endpoint مختلف: /api/chat
    base = api_base.rstrip("/")
    if "/api/chat" not in base and "/v1" not in base:
        url = f"{base}/api/chat"
    else:
        url = base

    for attempt in range(MAX_RETRIES):
        # Phase 2: hoisted Session outside retry loop
        session = requests.Session()
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=TIMEOUT)

            if resp.ok:
                data = resp.json()
                content = (data.get("message", {}).get("content") or "").strip()
                if content:
                    return content
                logger.warning("Ollama empty response (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            elif resp.status_code == 429:
                # Phase 2 fix: was `continue` without attempt counter increment → infinite loop
                # Now: sleep then fall through to the bottom-of-loop delay which respects MAX_RETRIES
                time.sleep(min(30, RETRY_DELAY * (2 ** attempt)))
                session.close()
                if attempt < MAX_RETRIES - 1:
                    time.sleep(min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF))
                continue
            else:
                logger.error("Ollama error [%d]: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("Ollama call failed: %s", e)
        finally:
            session.close()

        if attempt < MAX_RETRIES - 1:
            time.sleep(min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF))

    return None


# ========== COHERE ADAPTER ==========
@register_adapter("cohere")
def _adapter_cohere(messages, model, api_key, api_base, max_tokens, temperature):
    """محول Cohere — يستخدم /v2/chat مع صيغته الخاصة"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": USER_AGENT,
    }

    # Cohere v2 chat expects messages in OpenAI format too
    base = api_base.rstrip("/")
    url = f"{base}/v2/chat" if "v2" not in base else f"{base}/chat"

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    for attempt in range(MAX_RETRIES):
        # Phase 2: hoisted Session outside retry loop
        session = requests.Session()
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=TIMEOUT)

            if resp.ok:
                data = resp.json()
                # Cohere v2 returns {message: {content: [...]}}
                content_blocks = data.get("message", {}).get("content", [])
                if content_blocks and isinstance(content_blocks, list):
                    text = " ".join(c.get("text", "") for c in content_blocks if isinstance(c, dict))
                    if text.strip():
                        return text.strip()
                # Also try OpenAI-compat format
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content
                logger.warning("Cohere empty response (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            else:
                logger.error("Cohere error [%d]: %s", resp.status_code, resp.text[:200])

        except Exception as e:
            logger.error("Cohere call failed: %s", e)
        finally:
            session.close()

        if attempt < MAX_RETRIES - 1:
            time.sleep(min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF))

    return None


# ========== CLOUDFLARE WORKERS AI ADAPTER ==========
@register_adapter("cloudflare")
def _adapter_cloudflare(messages, model, api_key, api_base, max_tokens, temperature):
    """محول Cloudflare Workers AI"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    base = api_base.rstrip("/")
    # Cloudflare: POST /accounts/{id}/ai/run/{model}
    url = f"{base}/{model}"

    # استخراج النظام والمستخدم من الرسائل
    system_msg = ""
    user_msg = ""
    for m in messages:
        if m.get("role") == "system" and not system_msg:
            system_msg = m.get("content", "")
        elif m.get("role") == "user":
            user_msg = m.get("content", "")

    payload = {
        "messages": [{"role": "system", "content": system_msg}] if system_msg else [],
    }
    if user_msg:
        payload["messages"].append({"role": "user", "content": user_msg})
    if not payload["messages"]:
        payload["messages"] = messages
    payload["max_tokens"] = max_tokens

    for attempt in range(MAX_RETRIES):
        # Phase 2: hoisted Session outside retry loop
        session = requests.Session()
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=TIMEOUT)

            if resp.ok:
                data = resp.json()
                result = data.get("result", {})
                content = result.get("response", "")
                if content:
                    return content
                logger.warning("Cloudflare empty response")
            else:
                logger.error("Cloudflare error [%d]: %s", resp.status_code, resp.text[:200])

        except Exception as e:
            logger.error("Cloudflare call failed: %s", e)
        finally:
            session.close()

        if attempt < MAX_RETRIES - 1:
            time.sleep(min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF))

    return None


# ========== FALLBACK & MULTI-FALLBACK ==========
def call_with_fallback(messages: list, max_tokens: int = 4096, temperature: float = 0.15,
                       model_primary: str = None, model_fallback: str = None,
                       base_primary: str = None, base_fallback: str = None,
                       key_primary: str = None, key_fallback: str = None) -> str | None:
    """استدعاء مع fallback: جرب الموديل الأساسي، وإذا فشل → جرب الموديل الاحتياطي"""
    cfg = config.load()

    if not model_primary:
        model_primary = cfg.get("ai", {}).get("model", "minimax-m2.5-free")
    if not model_fallback:
        model_fallback = cfg.get("ai", {}).get("fallback_model", "deepseek-v4-flash")
    if not base_primary:
        base_primary = cfg.get("ai", {}).get("api_base", "")
    if not base_fallback:
        base_fallback = cfg.get("ai", {}).get("fallback_base", "https://api.groq.com/openai/v1/chat/completions")
    if not key_primary:
        key_primary = cfg.get("ai", {}).get("api_key", "")
    if not key_fallback:
        key_fallback = cfg.get("ai", {}).get("fallback_api_key", "")

    logger.info("🤖 استدعاء AI: %s (الاحتياطي: %s)", model_primary, model_fallback)

    result = call(messages, max_tokens=max_tokens, temperature=temperature,
                  model_override=model_primary, base_override=base_primary,
                  key_override=key_primary)
    if result:
        return result

    logger.warning("⚠️ %s فشل — تجربة %s الاحتياطي", model_primary, model_fallback)
    spread_delay()
    result = call(messages, max_tokens=max_tokens, temperature=temperature,
                  model_override=model_fallback, base_override=base_fallback,
                  key_override=key_fallback)
    if result:
        return result

    logger.error("❌ جميع الموديلات فشلت (الرئيسي: %s, الاحتياطي: %s)", model_primary, model_fallback)
    return None


def call_with_multi_fallback(messages: list, max_tokens: int = 4096, temperature: float = 0.15) -> str | None:
    """🔥 سلسلة مزودين متعددة — جرب كل مزود بالترتيب حتى ينجح واحد.
    يقرأ قائمة المزودين من config.yaml: ai.providers[]
    كل مزود يدعم: name, model, base, key_field, api_type (openai|ollama|cohere|cloudflare)

    Phase 3: bounded by MAX_CASCADE_SECONDS (90s) wall-clock. Returns None
    if the budget is exhausted, even if more providers remain.
    """
    cfg = config.load()
    providers = cfg.get("ai", {}).get("providers", [])

    if not providers:
        logger.warning("⚠️ لا توجد قائمة مزودين — استخدم fallback القديم")
        return call_with_fallback(messages, max_tokens=max_tokens, temperature=temperature)

    total = len(providers)
    # Phase 3: monotonic clock is immune to system clock changes mid-call
    cascade_start = time.monotonic()

    for i, prov in enumerate(providers):
        # Phase 3: enforce the hard outer cap before each provider attempt.
        # Skip the spread_delay() so we don't waste the remaining budget sleeping.
        elapsed = time.monotonic() - cascade_start
        if elapsed > MAX_CASCADE_SECONDS:
            logger.warning(
                "⏱️ cascade budget exhausted (%.1fs > %ds) — aborting with %d/%d providers left",
                elapsed, MAX_CASCADE_SECONDS, total - i, total
            )
            break

        if i > 0:
            spread_delay()

        key_field = prov.get("key_field", "api_key")
        name = prov.get("name", f"مزود {i+1}")
        model = prov.get("model", "")
        base = prov.get("base", "")
        api_type = prov.get("api_type", "openai")
        key = cfg.get("ai", {}).get(key_field, "")

        if not model or not base or not key:
            logger.warning("⚠️ [%d/%d] %s: إعدادات ناقصة", i+1, total, name)
            continue

        logger.info("🤖 [%d/%d] %s ← %s [%s]", i+1, total, name, model, api_type)

        result = call(messages, max_tokens=max_tokens, temperature=temperature,
                      model_override=model, base_override=base,
                      key_override=key, api_type_override=api_type)
        if result:
            logger.info("✅ [%d/%d] %s نجح", i+1, total, name)
            return result

        logger.warning("⚠️ [%d/%d] %s فشل — ننتقل للتالي", i+1, total, name)

        # Phase 3: re-check budget AFTER each provider attempt. A slow call can
        # consume 30s internally, so we may have just blown past the cap.
        elapsed = time.monotonic() - cascade_start
        if elapsed > MAX_CASCADE_SECONDS:
            logger.warning(
                "⏱️ cascade budget exhausted (%.1fs > %ds) after provider %d/%d — aborting",
                elapsed, MAX_CASCADE_SECONDS, i + 1, total
            )
            break

    elapsed = time.monotonic() - cascade_start
    if elapsed > MAX_CASCADE_SECONDS:
        logger.error("❌ جميع المزودين فشلوا (%d/%d) — cascade timed out at %.1fs", total, total, elapsed)
    else:
        logger.error("❌ جميع المزودين فشلوا (%d/%d) in %.1fs", total, total, elapsed)
    return None


def spread_delay():
    """تأخير عشوائي بين الطلبات المتتالية"""
    delay = random.uniform(MIN_SPREAD, MAX_SPREAD)
    logger.debug("😴 spread: %.1f ثانية بين الطلبات", delay)
    time.sleep(delay)


def reset_session_pool():
    """إعادة تعيين عداد المفاتيح"""
    global _api_key_index
    _api_key_index = 0


def _refresh_api_key_pool_if_stale(cfg: dict) -> None:
    """Phase 3: rebuild _api_key_pool if the underlying env values changed.

    Detects edits to AI_API_KEY, AI_API_KEY_2, AI_API_KEY_3. Used by `call()`
    on every invocation — cheap when nothing changed (one tuple compare).
    """
    global _api_key_pool, _api_key_index, _api_key_pool_signature
    ai_cfg = cfg.get("ai", {})
    new_sig = (
        ai_cfg.get("api_key", ""),
        ai_cfg.get("api_key_2", ""),
        ai_cfg.get("api_key_3", ""),
    )
    if new_sig == _api_key_pool_signature and _api_key_pool:
        return  # cached pool is still valid
    primary = new_sig[0]
    secondary = new_sig[1]
    tertiary = new_sig[2]
    new_pool = [k for k in (primary, secondary, tertiary) if k]
    if new_pool != _api_key_pool:
        if _api_key_pool:
            logger.info("🔄 API key pool refreshed (env values changed): %d → %d keys",
                        len(_api_key_pool), len(new_pool))
        _api_key_pool = new_pool
        _api_key_index = 0
    _api_key_pool_signature = new_sig


def is_rate_limited(last_error: str) -> bool:
    return last_error == "rate_limited"


def extract_json(text: str) -> dict | None:
    """استخراج JSON من النص بطريقة متينة"""
    if not text:
        return None
    text = text.strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    stack = []
    for i, ch in enumerate(text):
        if ch == '{':
            stack.append(i)
        elif ch == '}':
            if stack:
                start = stack.pop()
                if not stack:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        return None
    return None
