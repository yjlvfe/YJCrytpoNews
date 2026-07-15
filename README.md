<div align="center">

# 🚀 YJCryptoNews

### نظام ذكي لتجميع ونشر أخبار الكريبتو بالعربية — مدعوم بالذكاء الاصطناعي

*An AI-powered crypto news engine that fetches, scores, deduplicates, translates to professional Arabic, and auto-publishes to Telegram — one fresh story every hour, plus instant breaking-news alerts.*

<br>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![AI](https://img.shields.io/badge/AI-Multi--Provider%20Fallback-f59e0b)](#-طبقة-الذكاء-الاصطناعي)
[![Sources](https://img.shields.io/badge/Sources-20%2B%20RSS-8b5cf6)](#-المصادر)
[![Arabic](https://img.shields.io/badge/Output-عربي%20احترافي-16a34a)](#)

<br>

[**المميزات**](#-المميزات) • [**التشغيل السريع**](#-التشغيل-السريع) • [**المعمارية**](#-المعمارية) • [**الإعداد**](#-الإعداد-والتثبيت) • [**الأوامر**](#-دليل-الأوامر) • [**الجدولة**](#-الجدولة-التلقائية-cron)

</div>

---

## 💡 ما هو YJCryptoNews؟

YJCryptoNews هو محرك أخبار كريبتو متكامل يعمل **24/7 بدون تدخل بشري**. يجمع الأخبار من أكثر من 20 مصدراً عالمياً، يقيّمها ذكياً حسب تأثيرها على السوق، يترجم **خبراً واحداً طازجاً كل ساعة** إلى عربية احترافية، وينشره تلقائياً على قنوات تليجرام — مع رصد فوري للأخبار العاجلة.

فلسفة التصميم الأساسية:

> **خبر واحد كل ساعة = ترجمة واحدة = نشرة واحدة**

هذا يضمن محتوى طازجاً دائماً، يوفّر توكنات الذكاء الاصطناعي (لا ترجمة إلا لما سيُنشر فعلاً)، ويحافظ على جودة تحريرية عالية.

---

## ✨ المميزات

| | الميزة | الوصف |
|---|--------|-------|
| 🧠 | **ذكاء متعدد المزودات** | سلسلة fallback تلقائية: Groq → NVIDIA → OpenRouter → Mistral. لو فشل مزود، ينتقل للتالي فوراً — صفر توقف |
| 🇸🇦 | **ترجمة عربية احترافية** | نموذج `allam-2-7b` العربي الأصلي + تحقق صارم (رفض الصيني/الإنجليزي الزائد)، إيموجي ذكي، عناوين نظيفة |
| 📡 | **+20 مصدر RSS** | CoinDesk, CoinTelegraph, Decrypt, U.Today, NewsBTC, CryptoNews, Blockworks وأكثر |
| ⏰ | **نشر بالساعة** | خبر واحد طازج كل ساعة من آخر ساعتين فقط — يضمن الحداثة ويوفّر التوكنات |
| 🚨 | **رصد عاجل صارم** | فحص كل 5 دقائق: 11+ مصدر يغطون **نفس القصة** + تأثير سوقي عالٍ = نشر فوري لكل القصص المؤكدة |
| 🔍 | **محرك تكرار 4 مراحل** | exact-match + fuzzy + key-facts + تشابه دلالي (embeddings) — لا أخبار مكررة أبداً |
| 📊 | **تقييم 7 معايير** | تقييم جودة + fact-check متعدد المصادر قبل أي نشر |
| 🌐 | **لوحة تحكم ويب** | Flask dashboard لإدارة القنوات وتشغيل الدورات يدوياً |
| 🔒 | **آمن بالكامل** | المفاتيح في `.env` فقط — صفر أسرار في الكود أو على GitHub |

---

## 🏗️ المعمارية

نظام من **4 طبقات** يتدفّق فيها الخبر من المصدر إلى النشر:

```
                    ┌─────────────────────────────────────────┐
                    │         YJCryptoNews Pipeline            │
                    └─────────────────────────────────────────┘

   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │  1️⃣  جمع     │   │  2️⃣  جودة    │   │  3️⃣  ذكاء    │   │  4️⃣  نشر     │
   │   البيانات   │──▶│   ومحرك      │──▶│  اصطناعي     │──▶│   وتنسيق     │
   │              │   │   التكرار    │   │              │   │              │
   ├──────────────┤   ├──────────────┤   ├──────────────┤   ├──────────────┤
   │ 20+ RSS      │   │ تقييم 7      │   │ ترجمة عربية  │   │ تنسيق نظيف   │
   │ 4 APIs       │   │ معايير       │   │ تلخيص        │   │ + إيموجي     │
   │ scrapers     │   │ fact-check   │   │ إثراء        │   │ نشر تليجرام  │
   │              │   │ dedup 4×     │   │ fallback ×4  │   │ تسجيل DB     │
   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### تدفّق الخبر التفصيلي

```
   📡 المصادر (20+ RSS)
        │  جلب 250+ مقال
        ▼
   🧠 تقييم الجودة (score 0-100) + fact-check
        │  فلترة بحد أدنى 65
        ▼
   🔍 محرك التكرار (4 مراحل: exact → fuzzy → facts → semantic)
        │  إزالة المكرر
        ▼
   ⭐ اختيار أفضل خبر واحد طازج (آخر ساعتين)
        │  خبر واحد فقط = توفير توكنات
        ▼
   🤖 ترجمة + تلخيص + إثراء (allam-2-7b → fallback)
        │  تحقق صارم: عربي فقط
        ▼
   📤 تنسيق نظيف + نشر على القنوات
        │
        ▼
   🗄️ تسجيل في SQLite (منع التكرار مستقبلاً)
```

### بنية المشروع

```
YJCryptoNews/
├── bot.py                      🎯 نقطة الدخول — موزّع الأوامر
├── server.py                   🌐 لوحة التحكم (Flask)
├── run.sh                      ⏰ سكربت الدورة الساعية (cron)
├── check_urgent.sh             🚨 سكربت فحص العاجل (cron كل 5د)
├── config.yaml                 ⚙️ كل الإعدادات والمزودات والمصادر
├── .env                        🔑 المفاتيح (غير مرفوع لـ git)
├── .env.example                📄 قالب المفاتيح
├── requirements.txt            📦 الاعتماديات
│
└── yjcryptonews/               📦 الحزمة الأساسية
    ├── database.py             🗄️ SQLite — القنوات + سجل النشر + منع التكرار
    ├── config.py               ⚙️ إدارة الإعدادات (defaults → yaml → env)
    ├── log.py                  📝 نظام تسجيل احترافي
    ├── publisher.py            📤 النشر على تليجرام
    ├── translator.py           📖 محرك الترجمة (legacy)
    ├── market.py               📊 تحليل السوق
    │
    ├── ai/
    │   └── client.py           🤖 عميل ذكاء اصطناعي متعدد المزودات
    │
    ├── models/
    │   └── source.py           📐 نماذج البيانات (Source, Article)
    │
    └── lib/                     🧩 الطبقات الأربع
        ├── data_acquisition.py    1️⃣ محرك جمع البيانات
        ├── rss_aggregator.py      1️⃣ جلب RSS
        ├── api_collectors.py      1️⃣ جامعو APIs
        ├── scraping_engine.py     1️⃣ محرك الكشط
        ├── quality_scorer.py      2️⃣ تقييم الجودة
        ├── fact_checker.py        2️⃣ التحقق من الحقائق
        ├── dedup_engine.py        2️⃣ محرك التكرار (4 مراحل)
        ├── ai_translator.py       3️⃣ الترجمة
        ├── ai_summarizer.py       3️⃣ التلخيص
        ├── ai_enricher.py         3️⃣ الإثراء
        ├── ai_client.py           3️⃣ عميل الذكاء (fallback chain)
        ├── scheduler.py           4️⃣ المنسّق (hourly + breaking)
        ├── publisher.py           4️⃣ النشر
        └── analytics.py           4️⃣ التحليلات
```

---

## ⚡ التشغيل السريع

```bash
# 1. استنساخ المشروع
git clone https://github.com/yjlvfe/YJCrytpoNews.git
cd YJCrytpoNews

# 2. بيئة افتراضية + الاعتماديات
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. المفاتيح
cp .env.example .env
nano .env        # املأ المفاتيح

# 4. أضف قناتك
python bot.py channels add @YourChannel

# 5. شغّل دورة واحدة (اختبار)
python bot.py hourly
```

خلال دقائق ستُنشر أول نشرة عربية على قناتك. 🎉

---

## 🔧 الإعداد والتثبيت

### المتطلبات

| المتطلب | الإصدار |
|---------|---------|
| Python | 3.11+ (مُختبر على 3.12) |
| نظام التشغيل | Linux / macOS |
| ذاكرة | 2GB+ (بسبب `sentence-transformers` + `torch` للتكرار الدلالي) |

### 1️⃣ المفاتيح المطلوبة

انسخ `.env.example` إلى `.env` واملأ القيم:

| المتغير | الوصف | إلزامي | مجاني من |
|---------|-------|:------:|----------|
| `AI_API_KEY` | المزود الأساسي (OpenRouter) | ✅ | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `AI_FALLBACK_KEY` | Groq (allam-2-7b العربي) | ✅ | [console.groq.com](https://console.groq.com) |
| `BOT_TOKEN` | توكن بوت تليجرام | ✅ | [@BotFather](https://t.me/BotFather) |
| `AI_API_KEY_2` | Mistral | اختياري | [console.mistral.ai](https://console.mistral.ai) |
| `AI_FALLBACK_KEY_2` | NVIDIA NIM | اختياري | [build.nvidia.com](https://build.nvidia.com) |

> 💡 **نصيحة:** كلما أضفت مفاتيح fallback أكثر، زادت موثوقية النظام عند انتهاء حدود المزودات (rate limits).

### 2️⃣ إنشاء بوت تليجرام

1. افتح [@BotFather](https://t.me/BotFather) واكتب `/newbot`
2. انسخ التوكن إلى `BOT_TOKEN` في `.env`
3. أضف البوت **مشرفاً (admin)** في قناتك مع صلاحية النشر

### 3️⃣ إضافة القنوات

```bash
python bot.py channels add @YourChannel "اسم القناة"   # إضافة
python bot.py channels                                  # عرض الكل
python bot.py channels toggle @YourChannel              # تفعيل/إيقاف
python bot.py channels remove @YourChannel              # حذف
```

---

## 📋 دليل الأوامر

### الأوامر الأساسية (الإنتاج)

| الأمر | الوصف | الجدولة المقترحة |
|-------|-------|------------------|
| `python bot.py hourly` | ⏰ **الدورة الرئيسية** — خبر واحد طازج = ترجمة = نشر | كل ساعة |
| `python bot.py breaking_check` | 🚨 فحص عاجل صارم — 11+ مصدر نفس القصة = نشر فوري | كل 5 دقائق |
| `python bot.py prepare_hourly` | 🔍 معاينة الخبر القادم (بدون نشر) | يدوي |
| `python bot.py summary` | 📊 تقرير مسائي شامل | يومياً 20:00 |

### أوامر الإدارة

| الأمر | الوصف |
|-------|-------|
| `python bot.py channels` | عرض كل القنوات |
| `python bot.py channels add <id> [اسم]` | إضافة قناة |
| `python bot.py channels remove <id>` | حذف قناة |
| `python bot.py channels toggle <id>` | تفعيل/إيقاف قناة |
| `python bot.py daily_stats` | إحصائيات الطابور اليومي |

### أوامر متقدمة (legacy)

| الأمر | الوصف |
|-------|-------|
| `python bot.py v3` | دورة v3 كاملة (كل الطبقات، عدة مقالات) |
| `python bot.py run` | دورة واحدة |
| `python bot.py urgent` | فحص عاجل قديم |

---

## ⏰ الجدولة التلقائية (cron)

أضف هذه السطور لـ crontab (`crontab -e`):

```cron
# ⏰ الدورة الساعية — خبر واحد طازج كل ساعة
0 * * * * /path/to/YJCryptoNews/run.sh >> /var/log/YJCryptoNews.log 2>&1

# 🚨 فحص العاجل — كل 5 دقائق
*/5 * * * * /path/to/YJCryptoNews/check_urgent.sh >> /var/log/YJCryptoNews-urgent.log 2>&1

# 📊 التقرير المسائي — يومياً 20:00 UTC
0 20 * * * cd /path/to/YJCryptoNews && source venv/bin/activate && python bot.py summary >> /var/log/YJCryptoNews-daily.log 2>&1
```

> السكربتات `run.sh` و `check_urgent.sh` تتضمن حماية ضد التداخل (تقتل الدورة العالقة السابقة) و timeout تلقائي.

---

## 🤖 طبقة الذكاء الاصطناعي

سلسلة fallback ذكية مرتّبة حسب الأولوية — لو فشل مزود (rate limit / خطأ)، ينتقل للتالي **فوراً**:

```
🥇 Groq (allam-2-7b)      ← نموذج عربي أصلي، الأولوية القصوى
     │ فشل / 429؟
     ▼
🥈 Groq (llama-3.3-70b)   ← احتياطي بنفس المفتاح
     │
     ▼
🥉 NVIDIA NIM (llama-3.1) ← مزود مجاني قوي
     │
     ▼
🏅 OpenRouter (deepseek)  ← تنوّع نماذج
     │
     ▼
🎖️ Mistral (small)        ← الملاذ الأخير
```

### تحقق صارم من الجودة العربية

كل مخرجات الذكاء الاصطناعي تمرّ بفلاتر صارمة قبل النشر:

- ✅ **عربي فقط** — رفض المخرجات بدون أحرف عربية (نطاق `\u0600-\u06FF`)
- 🚫 **رفض الصيني/الياباني/الكوري** (CJK) — بعض النماذج تخلط الصيني
- 🚫 **رفض الإنجليزي الزائد** — لو الأحرف اللاتينية > ضعف العربية
- 🧹 **تنظيف الآثار** — إزالة `العنوان العربي:`, `📰`, أسماء الكتّاب, الروابط

---

## ⚙️ الإعدادات (config.yaml)

أهم الأقسام:

| القسم | الوصف |
|-------|-------|
| `ai.providers[]` | سلسلة المزودات المرتّبة + النماذج لكل مهمة |
| `sources.rss_feeds[]` | قائمة مصادر RSS (20 مصدر) |
| `urgent_detection` | عتبات العاجل (11+ مصدر، تشابه 0.75، تأثير 0.5) |
| `daily_publishing` | إعدادات النشر (الحد الأقصى/اليوم، الحد الأدنى للجودة) |
| `quality_engine` | عتبات التكرار 4 مراحل |
| `logging` | مستوى السجل ومساره |

### إضافة مزود جديد

```yaml
ai:
  providers:
    - name: "my_provider"
      base_url: "https://api.myprovider.com/v1"
      api_key_env: "MY_PROVIDER_KEY"     # اسم المتغير في .env
      models:
        translation: "my-arabic-model"
        summarization: "my-fast-model"
      timeout: 30
      enabled: true
```

---

## 🌐 لوحة التحكم (Dashboard)

```bash
python server.py        # http://127.0.0.1:5050
```

| المسار | الطريقة | الوصف |
|--------|---------|-------|
| `/` | GET | الصفحة الرئيسية |
| `/api/status` | GET | فحص صحة النظام |
| `/api/run-cycle` | POST | تشغيل دورة يدوياً |
| `/api/channels/list` | GET | قائمة القنوات |
| `/api/channels/toggle` | POST | تفعيل/إيقاف قناة |

> 🔒 اللوحة مربوطة بـ `127.0.0.1` افتراضياً للأمان. لا تعرّضها للإنترنت بدون مصادقة.

---

## 📡 المصادر

20+ مصدر RSS موثوق، منها:

`CoinDesk` · `CoinTelegraph` · `Decrypt` · `U.Today` · `NewsBTC` · `CryptoNews` · `Blockworks` · `Binance Blog` · والمزيد

كل المصادر قابلة للتفعيل/التعطيل من `config.yaml` → `sources.rss_feeds`.

---

## 🔒 الأمان

- ✅ المفاتيح في `.env` **فقط** — صفر أسرار في الكود
- ✅ `.gitignore` يمنع رفع `.env`, `*.db`, `*.log`, الـ backups
- ✅ تاريخ git نظيف — صفر أسرار مكشوفة
- ✅ اللوحة على `127.0.0.1` افتراضياً
- ✅ تحقق من المدخلات على كل نقاط API

> ⚠️ **لو سرّبت مفتاحاً بالخطأ:** ألغِه فوراً من لوحة المزود وأنشئ بديلاً.

---

## 🛠️ استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| `ALL PROVIDERS FAILED` | المفاتيح انتهت حدودها (rate limit) أو نفد الرصيد — أضف مفاتيح fallback إضافية |
| لا يُنشر شيء | تأكد أن البوت **admin** في القناة، وأن القناة `active` |
| `No Arabic characters` | المزود رجّع نصاً غير عربي — النظام يرفضه ويجرّب التالي تلقائياً |
| بطء/timeout | الدورة الأولى تحمّل نموذج embeddings (~60 ثانية)، بعدها أسرع |
| `database is locked` | دورة أخرى تعمل — السكربتات تتعامل مع هذا تلقائياً |

---

## 📊 الحالة

| المكوّن | الحالة |
|---------|--------|
| جلب RSS | ✅ 20+ مصدر |
| فلترة الذكاء الاصطناعي | ✅ 4 مزودات fallback |
| الترجمة العربية | ✅ جودة احترافية + تحقق صارم |
| محرك التكرار | ✅ 4 مراحل |
| رصد العاجل | ✅ صارم (11+ مصدر) |
| النشر على تليجرام | ✅ |
| لوحة التحكم | ✅ |

---

## 📝 الرخصة

[MIT](LICENSE) © 2026 [yjlvfe](https://github.com/yjlvfe)

---

<div align="center">

**⭐ إذا أعجبك المشروع، ضع نجمة على GitHub!**

صُنع بـ ❤️ لمجتمع الكريبتو والذكاء الاصطناعي العربي

</div>
