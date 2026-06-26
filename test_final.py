#!/usr/bin/env python3
"""🧪 اختبار شامل سريع للبوت بعد التعديلات"""
import sys, os, json, time
sys.path.insert(0, "/usr/local/lib/YJCryptoNews")

from yjcryptonews import config, database, ai
from yjcryptonews.log import get_logger

print("=" * 60)
print("🧪 اختبار شامل للبوت")
print("=" * 60)

# 1. Load config
cfg = config.load()
ai_section = cfg.get("ai", {})
providers = ai_section.get("providers", [])
bot_token = cfg.get("bot", {}).get("token", "")

print(f"\n1️⃣  Config load: ✅")
print(f"   Providers: {len(providers)}")
print(f"   Primary model: {ai_section.get('model', 'N/A')}")
print(f"   Bot token: {'✅ ' + bot_token[:10] + '...' if bot_token else '❌ MISSING!'} ({len(bot_token)} chars)")

# 2. Test bot token with Telegram API
import requests
print(f"\n2️⃣  اختبار Bot Token في تيليجرام...")
resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
if resp.ok:
    bot_info = resp.json().get("result", {})
    print(f"   ✅ Bot: @{bot_info.get('username', 'N/A')} - {bot_info.get('first_name', 'N/A')}")
    print(f"   ✅ Bot token شغال!")
else:
    print(f"   ❌ Bot token فاشل: {resp.text[:100]}")

# 3. Test DB
print(f"\n3️⃣  اختبار قاعدة البيانات...")
database.init_db()
channels = database.get_channels()
print(f"   ✅ {len(channels)} قناة:")
for ch in channels:
    status = "🟢" if ch["is_active"] else "🔴"
    print(f"      {status} {ch.get('title', ch.get('username', ch['chat_id']))}")

# 4. Test AI multi-provider
print(f"\n4️⃣  اختبار سلسلة المزودين...")
test_msg = [{"role": "user", "content": "Say 'TEST OK' and nothing else."}]
result = ai.call_with_multi_fallback(test_msg, max_tokens=20, temperature=0)

if result:
    print(f"   ✅ AI رد: {result.strip()[:80]}")
else:
    print(f"   ❌ AI فشل - كل المزودين ما ردوا")

# 5. Print .env key stats
print(f"\n5️⃣  مفاتيح API (.env):")
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if v:
                print(f"      {k}: {'✅ ' if len(v) > 10 else '⚠️ '} {len(v)} chars")

print(f"\n{'=' * 60}")
print(f"✅ انتهى الاختبار")
print(f"{'=' * 60}")
