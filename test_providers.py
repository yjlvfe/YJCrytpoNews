#!/usr/bin/env python3
"""🧪 اختبار شامل لكل المزودين + الموديلات المجانية"""
import sys, os, json, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env first
from pathlib import Path
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and k not in os.environ:
                    os.environ[k] = v

TEST_PROMPT = [{"role": "user", "content": "Say 'WORKING' and nothing else. Just the word WORKING."}]

providers = [
    # (name, key_env, model, base, api_type)
    ("Mistral", "AI_API_KEY_2", "mistral-small-latest", "https://api.mistral.ai/v1/chat/completions", "openai"),
    ("Groq", "AI_FALLBACK_KEY", "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1/chat/completions", "openai"),
    ("NVIDIA NIM", "AI_FALLBACK_KEY_2", "meta/llama-3.1-70b-instruct", "https://integrate.api.nvidia.com/v1/chat/completions", "openai"),
    ("SambaNova", "AI_FALLBACK_KEY_3", "Meta-Llama-3.3-70B-Instruct", "https://api.sambanova.ai/v1/chat/completions", "openai"),
    ("Cerebras", "AI_FALLBACK_KEY_4", "llama-3.3-70b", "https://api.cerebras.ai/v1/chat/completions", "openai"),
    ("Ollama Cloud", "AI_FALLBACK_KEY_5", "gemma3:12b", "https://api.ollama.com", "ollama"),
    ("AI21 Labs", "AI_FALLBACK_KEY_6", "jamba-large-1.7-2025-07", "https://api.ai21.com/studio/v1/chat/completions", "openai"),
    ("OpenRouter NEW", "AI_API_KEY", "meta-llama/llama-3.3-70b-instruct:free", "https://openrouter.ai/api/v1/chat/completions", "openai"),
    ("DeepSeek", "AI_FALLBACK_KEY_7", "deepseek-chat", "https://api.deepseek.com/chat/completions", "openai"),
    ("DeepInfra", "AI_FALLBACK_KEY_8", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "https://api.deepinfra.com/v1/openai/chat/completions", "openai"),
    ("GitHub Models", "AI_FALLBACK_KEY_9", "gpt-4o-mini", "https://models.inference.ai.azure.com/chat/completions", "openai"),
    ("Hyperbolic", "AI_FALLBACK_KEY_10", "meta-llama/Meta-Llama-3.1-70B-Instruct", "https://api.hyperbolic.xyz/v1/chat/completions", "openai"),
    ("xAI Grok", "AI_FALLBACK_KEY_11", "grok-2", "https://api.x.ai/v1/chat/completions", "openai"),
    ("Cohere", "AI_FALLBACK_KEY_12", "command-a", "https://api.cohere.ai/v1", "cohere"),
    ("Fireworks AI", "AI_API_KEY_3", "accounts/fireworks/models/deepseek-v4-pro", "https://api.fireworks.ai/inference/v1/chat/completions", "openai"),
]

# Additional model tests for providers that support multiple models
extra_models = [
    ("Groq", "AI_FALLBACK_KEY", "qwen-2.5-32b", "https://api.groq.com/openai/v1/chat/completions", "openai"),
    ("Groq", "AI_FALLBACK_KEY", "llama-3.1-8b-instant", "https://api.groq.com/openai/v1/chat/completions", "openai"),
    ("Groq", "AI_FALLBACK_KEY", "mixtral-8x7b-32768", "https://api.groq.com/openai/v1/chat/completions", "openai"),
    ("Groq", "AI_FALLBACK_KEY", "gemma2-9b-it", "https://api.groq.com/openai/v1/chat/completions", "openai"),
    ("Cerebras", "AI_FALLBACK_KEY_4", "gpt-oss-120b", "https://api.cerebras.ai/v1/chat/completions", "openai"),
    ("Cerebras", "AI_FALLBACK_KEY_4", "llama-3.1-8b", "https://api.cerebras.ai/v1/chat/completions", "openai"),
    ("NVIDIA NIM", "AI_FALLBACK_KEY_2", "meta/llama-3.3-70b-instruct", "https://integrate.api.nvidia.com/v1/chat/completions", "openai"),
    ("SambaNova", "AI_FALLBACK_KEY_3", "Meta-Llama-3.1-8B-Instruct", "https://api.sambanova.ai/v1/chat/completions", "openai"),
    ("DeepInfra", "AI_FALLBACK_KEY_8", "mistralai/Mixtral-8x22B-Instruct-v0.1", "https://api.deepinfra.com/v1/openai/chat/completions", "openai"),
    ("Hyperbolic", "AI_FALLBACK_KEY_10", "deepseek-ai/DeepSeek-V3", "https://api.hyperbolic.xyz/v1/chat/completions", "openai"),
    ("OpenRouter NEW", "AI_API_KEY", "deepseek/deepseek-chat", "https://openrouter.ai/api/v1/chat/completions", "openai"),
    ("OpenRouter NEW", "AI_API_KEY", "cognitivecomputations/dolphin3.0-mistral-24b:free", "https://openrouter.ai/api/v1/chat/completions", "openai"),
    ("Fireworks AI", "AI_API_KEY_3", "accounts/fireworks/models/llama-v3p3-70b-instruct", "https://api.fireworks.ai/inference/v1/chat/completions", "openai"),
    ("xAI Grok", "AI_FALLBACK_KEY_11", "grok-2-mini", "https://api.x.ai/v1/chat/completions", "openai"),
]

all_tests = providers + extra_models

def test_provider(name, key_env, model, base, api_type):
    key = os.environ.get(key_env, "")
    if not key:
        return {"status": "❌", "detail": f"No key for {key_env}"}
    
    if len(key) < 10:
        return {"status": "❌", "detail": f"Key too short ({len(key)} chars)"}
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    
    if api_type == "openai":
        payload = {"model": model, "messages": TEST_PROMPT, "max_tokens": 20, "temperature": 0}
        url = base
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.ok:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                return {"status": "✅", "detail": f"{content[:30]}", "model": model}
            else:
                detail = resp.text[:100]
                return {"status": f"❌ HTTP {resp.status_code}", "detail": detail, "model": model}
        except requests.Timeout:
            return {"status": "⏱️", "detail": "Timeout (15s)", "model": model}
        except Exception as e:
            return {"status": "❌", "detail": str(e)[:80], "model": model}
    
    elif api_type == "ollama":
        base = base.rstrip("/")
        url = f"{base}/api/chat" if "/api/chat" not in base and "/v1" not in base else base
        payload = {"model": model, "messages": TEST_PROMPT, "options": {"num_predict": 20, "temperature": 0}, "stream": False}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.ok:
                content = resp.json().get("message", {}).get("content", "").strip()
                return {"status": "✅", "detail": content[:30], "model": model}
            else:
                return {"status": f"❌ HTTP {resp.status_code}", "detail": resp.text[:100], "model": model}
        except Exception as e:
            return {"status": "❌", "detail": str(e)[:80], "model": model}
    
    elif api_type == "cohere":
        base = base.rstrip("/")
        url = f"{base}/v2/chat" if "v2" not in base else f"{base}/chat"
        payload = {"model": model, "messages": TEST_PROMPT, "max_tokens": 20, "temperature": 0}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.ok:
                data = resp.json()
                content_blocks = data.get("message", {}).get("content", [])
                if content_blocks and isinstance(content_blocks, list):
                    text = " ".join(c.get("text", "") for c in content_blocks if isinstance(c, dict))
                else:
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"status": "✅", "detail": text[:30], "model": model}
            else:
                return {"status": f"❌ HTTP {resp.status_code}", "detail": resp.text[:100], "model": model}
        except Exception as e:
            return {"status": "❌", "detail": str(e)[:80], "model": model}
    
    return {"status": "❓", "detail": f"Unknown api_type: {api_type}", "model": model}


# ===== RUN ALL TESTS =====
results = []
for name, key_env, model, base, api_type in all_tests:
    print(f"  🔍 Testing {name:20s} | {model:40s} | {api_type:8s}...", end=" ", flush=True)
    time.sleep(0.3)  # Small delay between tests
    r = test_provider(name, key_env, model, base, api_type)
    print(f"{r['status']:>12s}  {r['detail'][:60]}")
    results.append(r)

# ===== SUMMARY =====
print("\n" + "=" * 80)
print("📊 ملخص اختبار المزودين والموديلات المجانية")
print("=" * 80)

working = [r for r in results if r['status'] == '✅']
failing = [r for r in results if '❌' in r['status'] or '⏱️' in r['status']]

print(f"\n✅ شغال: {len(working)}")
for r in working:
    print(f"   ✅ {r['model']}")

print(f"\n❌ فاشل: {len(failing)}")
for r in failing:
    print(f"   {r['status']} {r['model']}: {r['detail'][:80]}")

# Best providers for each task
print("\n" + "=" * 80)
print("🏆 أفضل الموديلات المجانية الشغالة:")
print("=" * 80)
for i, r in enumerate(working):
    print(f"  {i+1}. {r['model']}")
