"""تحليل سوق الكريبتو — CoinGecko API مجاني"""
import json
import requests

COINGECKO_API = "https://api.coingecko.com/api/v3"


def get_market_snapshot() -> str:
    """الحصول على لمحة احترافية عن السوق"""
    url = f"{COINGECKO_API}/simple/price"
    params = {
        "ids": "bitcoin,ethereum,solana,ripple,cardano,dogecoin",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }

    try:
        # tuple timeout = (connect, read) — fails fast on dead routes,
        # still allows slow responses 15s on CoinGecko's slow paths
        resp = requests.get(url, params=params, timeout=(5, 15))
        if not resp.ok:
            return ""
        data = resp.json()
    except Exception as e:
        print(f"⚠️ CoinGecko error: {e}")
        return ""

    if not data:
        return ""

    # بناء تحليل احترافي
    lines = ["📊 **تحليل السوق الآن**", ""]

    btc = data.get("bitcoin", {})
    eth = data.get("ethereum", {})

    if btc:
        price = btc.get("usd", 0)
        change = btc.get("usd_24h_change", 0)
        arrow = "🟢" if change >= 0 else "🔴"
        sign = "+" if change >= 0 else ""
        lines.append(f"{arrow} **بيتكوين** — ${price:,.0f} ({sign}{change:.2f}%)")

    if eth:
        price = eth.get("usd", 0)
        change = eth.get("usd_24h_change", 0)
        arrow = "🟢" if change >= 0 else "🔴"
        sign = "+" if change >= 0 else ""
        lines.append(f"{arrow} **إيثريوم** — ${price:,.0f} ({sign}{change:.2f}%)")

    # إضافة أفضل وأسوأ أداء
    names = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
        "ripple": "XRP", "cardano": "ADA", "dogecoin": "DOGE"
    }

    changes = []
    for coin, info in data.items():
        change = info.get("usd_24h_change")
        price = info.get("usd", 0)
        if change is not None:
            sym = names.get(coin, coin[:4].upper())
            changes.append((sym, change, price))

    if changes:
        changes.sort(key=lambda x: x[1], reverse=True)
        lines.append("")
        lines.append(f"🏆 الأفضل: {changes[0][0]} ({changes[0][1]:+.2f}%)")
        lines.append(f"📉 الأسوأ:  {changes[-1][0]} ({changes[-1][1]:+.2f}%)")
        lines.append("")
        lines.append(f"المصدر: CoinGecko | التحديث: لحظي")

    return "\n".join(lines)
