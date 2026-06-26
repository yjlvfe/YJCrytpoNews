"""محرر أخبار — ترجمة عربية احترافية بجودة عالية"""
from . import ai as ai_client
from . import config
from .log import get_logger
import re

logger = get_logger("translator")


def _call(messages: list, max_tokens: int = 4096) -> str | None:
    """ترجمة عبر سلسلة مزودين متعددة — أقصى موثوقية"""
    return ai_client.call_with_multi_fallback(messages, max_tokens=max_tokens, temperature=0.2)


def _extract_json(text: str) -> dict | None:
    return ai_client.extract_json(text)


def _build_result(data: dict, title_original: str, summary_original: str) -> dict | None:
    """تنظيف والتحقق من خرج AI. يرجع dict مُنظف أو None إذا غير صالح."""
    title_ar = (data.get("title_ar") or "").strip()
    body_ar = (data.get("body_ar") or data.get("summary_ar") or "").strip()
    title_emoji = (data.get("title_emoji") or "").strip()
    body_emoji = (data.get("body_emoji") or "").strip()

    if not title_ar or title_ar == title_original:
        return None

    # 🛡️ إزالة رمز البيتكوين المحظور إذا تسرب من الـ AI (ممنوع منعاً باتاً)
    banned_bitcoin_symbol = "\u20bf"
    title_ar = title_ar.replace(banned_bitcoin_symbol, "").strip()
    body_ar = body_ar.replace(banned_bitcoin_symbol, "").strip()

    # 🛡️ إزالة الحروف الصينية والكورية واليابانية (CJK) — الـ minimax يخلط أحياناً
    # المشكلة: minimax-m2.5-free أخرج "扩张" بعد "UTC+8" في خبر بينانس (POST 3608)
    # وأيضاً "期待" + "，" (فاصلة عرض كامل U+FF0C) في خبر BUILDon (POST 3614)
    cjk_pattern = re.compile(
        r'[\u3000-\u303F\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF'
        r'\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]'
    )
    title_ar = cjk_pattern.sub('', title_ar).strip()
    body_ar = cjk_pattern.sub('', body_ar).strip()
    
    # 🛡️ إزالة المسافات المتكررة (الـ AI أحياناً يضيف مسافات زائدة)
    title_ar = re.sub(r' {2,}', ' ', title_ar).strip()
    body_ar = re.sub(r' {2,}', ' ', body_ar).strip()

    # Fix merged coin names (Arabic verb + coin name without space)
    _coin_names = ['بيتكوين', 'إيثريوم', 'إيثيريوم', 'سولانا', 'عملة', 'ريبل']
    _arabic_letters = 'ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئ'
    _coin_pattern = re.compile(r'([{0}])({1})'.format(_arabic_letters, '|'.join(_coin_names)))
    title_ar = _coin_pattern.sub(r'\1 \2', title_ar).strip()
    body_ar = _coin_pattern.sub(r'\1 \2', body_ar).strip()

    # Fix detached preposition "ل" and "لل" from nouns — must be AFTER coin merge
    # Updated 2026-05-13 06:00: added إ and آ (were missing, causing "لل إيثيريوم" to not be fixed)
    title_ar = re.sub(r'(^| )ل +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1ل', title_ar)
    body_ar = re.sub(r'(^| )ل +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1ل', body_ar)
    title_ar = re.sub(r'(^| )لل +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1لل', title_ar)
    body_ar = re.sub(r'(^| )لل +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1لل', body_ar)

    # Fix detached "ال" (definite article) from nouns — must be AFTER ل/لل fix
    # Updated 2026-05-13: fixed \b (ASCII-only) + added missing letters (إأآءؤئ)
    # Moved after coin merge + ل/لل fix because coin merge reverses ال fix
    title_ar = re.sub(r'(^| )ال +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1ال', title_ar)
    body_ar = re.sub(r'(^| )ال +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1ال', body_ar)

    # Fix detached "الإ" (alef with hamza below + lam) from nouns
    # المشكلة: الـ AI يكتب أحياناً "الإ تسجل" بدلاً من "الإتسجل" (ظهر 2026-05-16 08:00)
    # "الإ " هي أداة التعريف بهمزة تحت متبوعة بمسافة — الـ regex أعلاه يبحث عن "ال " فقط
    # مثال: "صناديق Ethereum الإ تسجل" ← "صناديق Ethereum الإتسجل"
    # ⚠️ هذا ليس صحيحاً نحوياً (الإ + فعل) ولكن دمجها أفضل من تركها منفصلة
    # التحسين المستقبلي: كشف "الإ + فعل" وحذف أداة التعريف بالكامل
    title_ar = re.sub(r'(^| )الإ +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1الإ', title_ar)
    body_ar = re.sub(r'(^| )الإ +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1الإ', body_ar)

    # 🛡️ إصلاح "الإ" الموصولة قبل الأفعال — الـ AI أحياناً يلصق أداة التعريف بفعل
    # المشكلة: في POST 2026-05-16 15:00 كتب الـ AI "صناديق Ethereum الإتسجل خروجاً..."
    # بدلاً من "صناديق Ethereum تسجل خروجاً..."
    # النمط: "الإت" (أداة تعريف + تاء الفعل) متبوعة بـ 3+ أحرف عربية = خطأ نحوي
    # الحل: نحذف "الإ" ونبقي الفعل كما هو — آمن لأن "الإت" كبداية لاسم عربي صحيح نادر جداً
    # أمثلة آمنة: لا يؤثر على "الإيثيريوم" (إي، ليس إت)
    _verb_prefix = re.compile(r'الإت(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئى]{3,})')
    title_ar = _verb_prefix.sub('ت', title_ar)
    body_ar = _verb_prefix.sub('ت', body_ar)

    # 🛡️ إصلاح "صندوقانية" (مزيج مثنى + ية خاطئ)
    # المشكلة: في POST 2026-05-16 15:00 كتب الـ AI "هذان الصندوقانية" بدلاً من "هذان الصندوقان"
    title_ar = re.sub(r'الصندوقانية', 'الصندوقان', title_ar)
    body_ar = re.sub(r'الصندوقانية', 'الصندوقان', body_ar)

    # Fix detached preposition+ال combinations (بال, فال, كال, وال)
    # المشكلة: الـ AI يكتب أحياناً "بال بيتكوين" بدلاً من "بالبيتكوين" (POST 3698)
    # و "فال إيثريوم" بدلاً من "فالإيثريوم"، إلخ
    for prefix in ['بال', 'فال', 'كال', 'وال']:
        title_ar = re.sub(
            rf'(^| ){prefix} +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])',
            rf'\1{prefix}', title_ar
        )
        body_ar = re.sub(
            rf'(^| ){prefix} +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])',
            rf'\1{prefix}', body_ar
        )

    # Fix detached conjunction "و" (and) — same pattern as ل/لل/بال/فال/كال/وال
    # المشكلة: الـ AI يكتب أحياناً "و إيثريوم" بدلاً من "وإيثريوم" (اكتشف 2026-05-13 11:00)
    # الترتيب مهم: بعد بال/فال/كال/وال fix وقبل الكلمات الممنوعة
    title_ar = re.sub(r'(^| )و +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1و', title_ar)
    body_ar = re.sub(r'(^| )و +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1و', body_ar)

    # Fix detached preposition "ب" (باء الجر — with/by) from nouns
    # المشكلة: الـ AI يكتب أحياناً "ب إيثيريوم" بدلاً من "بإيثيريوم" (اكتشف 2026-05-13 19:00)
    # مثال: "صناديق ETF الخاصة ب إيثيريوم" ← "صناديق ETF الخاصة بإيثيريوم"
    title_ar = re.sub(r'(^| )ب +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1ب', title_ar)
    body_ar = re.sub(r'(^| )ب +(?=[ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئإآةى])', r'\1ب', body_ar)

    # Remove banned filler words
    for banned_word in ["حيث", "الجدير بالذكر", "جدير بالذكر"]:
        title_ar = title_ar.replace(f" {banned_word} ", " ").replace(f"{banned_word} ", "").replace(f" {banned_word}", "").strip()
        body_ar = body_ar.replace(f" {banned_word} ", " ").replace(f"{banned_word} ", "").replace(f" {banned_word}", "").strip()

    # 🛡️ إزالة الكلمات الإنجليزية الموصولة بـ (_) مع العربية
    # مثال: "تأكيد_targetهم" ← "تأكيدهم" (نحذف الإنجليزي والunderscore)
    # المشكلة: الـ AI أحياناً يكتب "تأكيد_targetهم" بدلاً من "تأكيد هدفهم"
    def _clean_eng_underscore(t: str) -> str:
        t = re.sub(r'([\u0600-\u06FF]+)_[A-Za-z]+([\u0600-\u06FF]+)', r'\1\2', t)  # عربي_إنجليزيعربي → عربيعربي
        t = re.sub(r'([\u0600-\u06FF]+)_[A-Za-z]+', r'\1', t)  # عربي_إنجليزي → عربي
        t = re.sub(r'[A-Za-z]+_([\u0600-\u06FF]+)', r'\1', t)  # إنجليزي_عربي → عربي
        return t.strip()
    title_ar = _clean_eng_underscore(title_ar)
    body_ar = _clean_eng_underscore(body_ar)

    # 🛡️ إزالة الحروف اللاتينية الموصولة مباشرة بالعربية (فساد في خرج AI بدون underscore)
    # مثال: "الشutores" ← "الش" (يتبع الـ AI حرف عربي بأحرف لاتينية منخفضة)
    # المشكلة: في POST 3682 كتب الـ AI "مجلس الشutores" بدلاً من "مجلس الشيوخ"
    # تحديث 2026-05-13: إضافة معالجة لحالة إنجليزية وسط عربي + أحرف إنجليزية كبيرة
    # مثال: "المInstitutionي" ← "المي", "صندوقJPMorgan" ← "صندوق" (ظهر في POST 3702 كـ #التمويل_المInstitutionي)
    def _clean_latin_from_arabic(t: str) -> str:
        # نمط واحد شامل: أي حرف عربي متبوع بحرفين+ لاتينيين (كبير/صغير) بدون مسافة — يحذف اللاتينية
        t = re.sub(r'([\u0600-\u06FF])[A-Za-z]{2,}', r'\1', t)
        return t
    title_ar = _clean_latin_from_arabic(title_ar)
    body_ar = _clean_latin_from_arabic(body_ar)

    # 🛡️ إزالة الحروف السيريلية وغير العربية/اللاتينية (فساد في خرج minimax)
    # المشكلة: في POST 3699 كتب الـ AI "شركة держат.eth" بدلاً من "شركة حاملة إيثريوم"
    # النمط: أحرف سيريلية (روسية) تظهر في نص عربي — الـ minimax يخلط أحياناً
    def _clean_foreign_scripts(t: str) -> str:
        t = re.sub(r'[\u0400-\u04FF]+', '', t)   # Cyrillic
        t = re.sub(r'[\u0370-\u03FF]+', '', t)   # Greek
        t = re.sub(r'[\u0530-\u058F]+', '', t)   # Armenian
        t = re.sub(r'\s{2,}', ' ', t)
        return t.strip()
    title_ar = _clean_foreign_scripts(title_ar)
    body_ar = _clean_foreign_scripts(body_ar)

    # 🛡️ إصلاح ازدواج الحروف العربية — الـ AI أحياناً يدمج كلمتين بنفس الحرف
    # المشكلة: "مصرففيون" (مصرف + فيون) → الصحيح: "مصرفيون" (مصرف + يون)
    # الـ AI يكرر الحرف عند دمج كلمة تنتهي بحرف مع كلمة تبدأ بنفس الحرف
    # النمط: [حرف][نفس الحرف]يون → [حرف]يون (مثلاً مصرففيون → مصرفيون)
    _arabic_dedup = re.compile(r'([ابتثجحخدذرزسشصضطظعغفقكلمنهويءأؤئى])\1يون')
    title_ar = _arabic_dedup.sub(r'\1يون', title_ar)
    body_ar = _arabic_dedup.sub(r'\1يون', body_ar)

    # 🛡️ إصلاح صيغ الجمع الخاطئة — الـ AI أحياناً يضيف "ار" زائدة بعد "ور" قبل "ات"
    # مثال: "السيناتورارات" ← "السيناتورات" (ظهرت في POST 3673)
    # النمط العام: أي كلمة فيها "ورارات" ← "ورات" (الـ "ار" الزائدة قبل "ات" الجمع)
    title_ar = re.sub(r'ورارات', 'ورات', title_ar)
    body_ar = re.sub(r'ورارات', 'ورات', body_ar)

    # 🛡️ إزالة "للبرميل" (تسرب من مصطلحات النفط — الـ AI يخلط بين صياغة تقارير النفط والكريبتو)
    # المشكلة: في POST 3770 كتب الـ AI "79,997.70 دولار للبرميل" بدلاً من "79,997.70 دولار"
    body_ar = re.sub(r'دولار للبرميل', 'دولار', body_ar)

    # 🛡️ إزالة الكلمات الإسبانية والأجنبية المنفصلة التي تتسرب من الـ AI
    # المشكلة: في POST 3804 كتب الـ AI "تُتيح acceso إلى" بدلاً من "تُتيح الوصول إلى"
    # "acceso" = كلمة إسبانية معناها "الوصول" — تظهر ككلمة مستقلة بمسافات حولها
    body_ar = body_ar.replace(" acceso ", " الوصول ")
    body_ar = body_ar.replace("acceso ", "الوصول ")
    body_ar = body_ar.replace(" acceso", " الوصول")
    title_ar = title_ar.replace(" acceso ", " الوصول ")
    title_ar = title_ar.replace("acceso ", "الوصول ")
    title_ar = title_ar.replace(" acceso", " الوصول")

    # 🛡️ إزالة الكلمة الإسبانية "parte" (جزء) التي يتسرب minimax أحياناً
    # المشكلة: في POST 3815 كتب الـ AI "لدى parte من المستثمرين" بدلاً من "لدى جزء من المستثمرين"
    # "parte" = كلمة إسبانية معناها "جزء" — تظهر ككلمة مستقلة بمسافات حولها
    body_ar = body_ar.replace(" parte ", " جزء ")
    body_ar = body_ar.replace("parte ", "جزء ")
    body_ar = body_ar.replace(" parte", " جزء")
    title_ar = title_ar.replace(" parte ", " جزء ")
    title_ar = title_ar.replace("parte ", "جزء ")
    title_ar = title_ar.replace(" parte", " جزء")

    # 🛡️ إصلاح ازدواج "و" قبل "وغير" (حرف العطف قبل غير التي تبدأ بالواو)
    # المشكلة: في POST 3803 كتب الـ AI "Coinbase و وغيرهما" بدلاً من "Coinbase وغيرهما"
    # النمط: "و " (مسافة) قبل "وغير" — نزيل المسافة وندمج الواوين
    # مثال: "و وغيرهما" ← "وغيرهما"
    # ملاحظة: نستخدم "وغير" تحديداً لتجنب false positives مع كلمات مثل "و وافق" أو "و واحد"
    title_ar = re.sub(r'(^| )و +وغير', r'\1وغير', title_ar)
    body_ar = re.sub(r'(^| )و +وغير', r'\1وغير', body_ar)

    # 🛡️ إزالة علامات الترقيم الصينية/الكاملة (CJK) التي يتسرب minimax
    # المشكلة: في POST 3787 كتب الـ AI "تراجعات كبرى。。" بنقطتين صينيتين في نهاية النص
    # النمط: U+3000-U+303F (CJK symbols), U+FF00-U+FFEF (fullwidth forms)
    def _clean_cjk_punct(t: str) -> str:
        t = re.sub(r'[\u3000-\u303f\uff00-\uffef]+', '', t)
        return t.strip()
    title_ar = _clean_cjk_punct(title_ar)
    body_ar = _clean_cjk_punct(body_ar)

    # 🛡️ إصلاح الألفين المزدوجين (أا → أ) — الـ AI أحياناً يكتب "أادت" بدلاً من "أدت"
    # المشكلة: minimax ينتج أحياناً "أادت" بدلاً من "أدت" (ألفين متتاليتين خطأ نحوي)
    # الألفين "أا" غير صحيحتين نحوياً في العربية الفصحى — ندمجهما
    title_ar = re.sub(r'أا', 'أ', title_ar)
    body_ar = re.sub(r'أا', 'أ', body_ar)

    # 🛡️ إصلاح كلمة "المش" الوهمية قبل الأرقام — minimax يهلوس أحياناً وينتج "المش 13F" بدلاً من "الـ 13F"
    # المشكلة: في POST 3850 كتب الـ AI "كشف تقرير المش 13F" بدلاً من "كشف تقرير الـ 13F"
    # كلمة "المش" غير موجودة في العربية الفصحى — هي هلوسة من الـ minimax
    # النمط: "المش " (منفصلة بمسافة) متبوعة برقم — نستبدلها بـ "الـ "
    title_ar = re.sub(r'(^| )المش +(?=\d)', r'\1الـ ', title_ar)
    body_ar = re.sub(r'(^| )المش +(?=\d)', r'\1الـ ', body_ar)

    # 🛡️ التحقق من الإيموجي — إذا الAI ما اختار، نستخدم fallback
    if not title_emoji or len(title_emoji) < 1:
        title_emoji = ""
    if not body_emoji or len(body_emoji) < 1:
        body_emoji = ""
    # 🛡️ ممنوع 📰 و  في الإيموجي
    for forbidden in ("📰", ""):
        if forbidden in title_emoji:
            title_emoji = ""
        if forbidden in body_emoji:
            body_emoji = ""

    # 🎯 استخراج الهاشتاقات — 1+ هاشتاق بمحتوى دقيق من الـ AI
    hashtags_raw = data.get("hashtags")
    if isinstance(hashtags_raw, list) and len(hashtags_raw) >= 1:
        # تنظيف كل هاشتاق: إزالة # إن وُجدت، وإزالة المسافات
        hashtags = []
        for h in hashtags_raw:
            h = str(h).strip().replace("#", "").replace(" ", "_").replace(".", "")
            # 🛡️ إزالة أي كلمات إنجليزية مدسوسة داخل الهاشتاق العربي أو ملتصقة به
            # مثال: "التمويل_المInstitutionي" ← "التمويل_المي" (إزالة Institution من الوسط)
            h = re.sub(r'([\u0600-\u06FF])[A-Za-z]{2,}', r'\1', h)  # إنجليزي ملتصق بعربي
            h = re.sub(r'[A-Za-z]{2,}', '', h)  # نص إنجليزي كامل في الهاشتاق
            h = re.sub(r'_+', '_', h).strip('_')  # تنظيف underscores بعد الحذف
            if h:
                hashtags.append(h)
        # إذا بعد التنظيف ما صار في شيء، نستخدم fallback
        if not hashtags:
            hashtags = ["أخبار_الكريبتو"]
    else:
        # 🛡️ دعم backward compatibility: لو ال AI لسا جاب hashtag مفرد بدلاً من مصفوفة
        single = (data.get("hashtag") or "").strip().replace("#", "").replace(" ", "_").replace(".", "")
        if single:
            hashtags = [single, "أخبار_الكريبتو"]
        else:
            hashtags = ["أخبار_الكريبتو"]

    return {
        "title_ar": title_ar,
        "body_ar": body_ar or summary_original,
        "title_emoji": title_emoji,
        "body_emoji": body_emoji,
        "hashtags": hashtags,
    }


def translate(title: str, summary: str) -> dict:
    """ترجمة احترافية — مع إيموجي ذكي وهاشتاق ديناميكي يختاره AI حسب سياق الخبر"""
    prompt = f"""أنت محرر أخبار مالية دولي محترف في قناة تيليجرام. اكتب خبراً عربياً جذاباً واحترافياً واختر إيموجيين مناسبين.

المطلوب:
1. **عنوان يبدأ باسم الموضوع** وليس بفعل
   - صح: "بيتكوين يتجاوز 81 ألف دولار" أو "مؤشر S&P 500 يسجل قمة جديدة"
   - خطأ: "يتجاوز بيتكوين حاجز 81 ألف دولار"
2. **🚫 ممنوع قطعاً أن يبدأ العنوان بكلمة إنجليزية أو اسم مشروع إنجليزي**
   - خطأ: "S&P 500 يسجل..." ✗ → صح: "مؤشر S&P 500 يسجل..." ✓
   - خطأ: "Trump Media تخسر..." ✗ → صح: "شركة ترامب ميديا تخسر..." ✓
   - إذا اسم المشروع/الشركة إنجليزي: أضف قبله كلمة عربية مثل (منصة، شركة، بروتوكول، مؤشر، عملة، تطبيق، شبكة)
3. **🏷️ أسماء الشركات والمشاريع تبقى كما هي بدون ترجمة**:
   - "NVIDIA" تبقى "NVIDIA"، "BlackRock" تبقى "BlackRock"، "Apple" تبقى "Apple"
   - الأسماء التجارية لا تُترجم أبداً — هذا يغير معناها وقد يكون مخالفاً قانونياً
4. ملخص جملتين إلى ثلاث بأسلوب صحفي مشوق
5. **🚫 ممنوع استخدام كلمة "حيث"** — هي كلمة حشو ركيكة:
   - ❌ "حيث سجل المؤشر ارتفاعاً..." ← ✅ مباشرة: "سجل المؤشر ارتفاعاً..."
5b. **🚫 ممنوع استخدام كلمات إنجليزية عشوائية أو كلمات بلغات أجنبية أخرى (فيتنامية، صينية، كورية، إسبانية) في النص العربي** — فقط المصطلحات العالمية (ETF, DeFi, NFT, AI, API, GDP, CPI, IPO)
   - ❌ "giao ngay" (فيتنامية) في نص عربي — خطأ، يجب ترجمتها لـ "فوري" أو "سبوت"
   - ❌ "acceso" (إسبانية) — خطأ، يجب ترجمتها لـ "الوصول"
   - المصدر قد يكون بأي لغة (إنجليزية، فيتنامية، صينية...)، لكن الترجمة العربية يجب أن تكون عربية خالصة
5c. **🚫 ممنوع استخدام أداة التعريف (ال/الإ) قبل الأفعال** — الأفعال لا تأخذ أداة تعريف أبداً
   - ❌ "صناديق Ethereum الإتسجل خروجاً..." — خطأ، "الإ" قبل فعل "تسجل"
   - ✅ "صناديق Ethereum تسجل خروجاً..." — صح، بدون أداة تعريف
5d. **🚫 ممنوع استخدام صيغ مزجية للجمع والمثنى** — استخدم الصيغ الصحيحة فقط
   - ❌ "هذان الصندوقانية" — خطأ، "صندوقانية" ليست صيغة صحيحة (مزيج مثنى + ية)
   - ✅ "هذان الصندوقان" — صح، مثنى صحيح
6. **لا تضف معلومات غير موجودة في النص الأصلي** — ممنوع الهلوسة تماماً:
   - ⚠️ إذا الخبر عن شركة تقنية، **لا تضف** كلمة كريبتو أو بيتكوين إذا لم تذكر في النص
   - ⚠️ إذا الخبر عن سياسة أو اقتصاد عام، **لا تربطه** بالعملات الرقمية
   - ⚠️ كن دقيقاً: ترجم فقط ما هو موجود، لا تخترع علاقات
   - ⚠️ **⚠️ خطر الهلوسة الرقمية: لا تخترع أبداً أرقاماً أو إحصائيات وارقاماً غير موجودة في النص الأصلي.** إذا النص لم يذكر رقماً محدداً لحيازات البيتكوين (مثلاً 214 ألف BTC أو 14 مليار دولار)، **لا تضف أي رقم** من عندك. الأرقام الوهمية تضر بالمصداقية.
   - ⚠️ **أمثلة حقيقية على الهلوسة:** خبر عن شركة Strategy (تمتلك ~214 ألف BTC بقيمة ~14 مليار دولار) — الـ AI كتب "576 مليار دولار" وهو رقم غير موجود في النص الأصلي بتاتاً. هذا يضر بمصداقية القناة.
   - ✅ الصواب: "تمتلك الشركة حيازات كبيرة من بيتكوين" (بدون رقم محدد) إذا الرقم غير مذكور في النص.
7. **لا تبدأ الجملة الأولى بـ "ي" المضارع أو "ت" المضارع** — ابدأ باسم الموضوع أو العملة
8. **📝 تأكد من اكتمال الجمل بفعل رئيسي**

🎯 **اختيار الهاشتاقات الذكية:**
- **hashtags**: مصفوفة من 3 هاشتاقات بالعربية تعبر عن الموضوع بدقة
  - أخبار كريبتو: ["بيتكوين", "استثمار", "عملات_رقمية"]
  - أخبار أسهم: ["أسهم", "وول_ستريت", "اقتصاد"]
  - أخبار اقتصاد: ["اقتصاد", "فائدة", "تضخم"]  
  - أخبار سياسة: ["سياسة", "أسواق", "اقتصاد_عالمي"]
  - أخبار تكنولوجيا: ["تقنية", "ذكاء_اصطناعي", "استثمار"]
  - يجب أن يكون 3 هاشتاقات على الأقل

🎯 **اختيار الإيموجي الذكي:**
- **title_emoji**: إيموجي واحد حسب **مجال الخبر**
  - كريبتو: 🪙💰🚀📊
  - أسهم: 📈📉🏛️📊
  - اقتصاد: 🏦📊💰🌍
  - سياسة: 🏛️🌐⚖️⚔️
  - تكنولوجيا: 🤖💻🔬⚡
  - طاقة: 🛢️⚡🔋
  - ذهب/سلع: 🥇🪙

- **body_emoji**: إيموجي واحد يعبر عن **اتجاه الخبر** (مختلف عن title_emoji)
  - 📈 للارتفاعات والإيجابي
  - 📉 للانخفاضات والسلبي
  - 🚀 للنمو والطفرة
  - ⚡ للتطورات السريعة
  - 🔥 للأخبار العاجلة
  - 💰 للأموال والتمويل
  - 🛡️ للأمن
  - 🎯 لتحقيقات وأهداف

- **⚠️ مهم:** title_emoji و body_emoji مختلفين
- **❌ ممنوع:** 📰 أبداً،  ممنوع

الخبر:
العنوان: {title}
الملخص: {summary}

أخرج JSON فقط:
{{"title_ar":"عنوان عربي يبدأ بكلمة عربية","body_ar":"ملخص عربي جذاب بدون أي إيموجي","title_emoji":"🚀","body_emoji":"📈","hashtags":["بيتكوين","استثمار","أخبار"]}}"""

    result = _call([
        {"role": "system", "content": "أنت محرر أخبار مالية دولي محترف. تكتب بالعربية الفصيحة بأسلوب صحفي مشوق. ممنوع الهلوسة — لا تضف كريبتو إذا لم يذكر. أخرج JSON فقط. تحذير شديد: ممنوع قطعاً أن يبدأ العنوان بكلمة إنجليزية — أضف كلمة عربية قبله."},
        {"role": "user", "content": prompt},
    ])

    if result:
        data = _extract_json(result)
        if data:
            result_dict = _build_result(data, title, summary)
            if result_dict:
                # 🛡️ فحص: العنوان يبدأ بعربي؟ لا ننشر إنجليزي أول الكلمة
                if re.match(r'^[A-Za-z]', result_dict["title_ar"]):
                    first_word = result_dict["title_ar"].split()[0] if result_dict["title_ar"].split() else "English"
                    logger.warning("العنوان يبدأ بانجليزي! محاولة مرة ثانية بتعليمات أشد: %s", result_dict["title_ar"][:50])
                    # محاولة ثانية بتعليمات صريحة: أضف كلمة عربية قبل الإنجليزي
                    retry_msg = [
                        {"role": "system", "content": f"⚠️ العنوان الذي أنتجته يبدأ بكلمة إنجليزية: '{first_word}'. أعد كتابة العنوان بحيث يبدأ بكلمة عربية مثل: 'منصة {first_word}' أو 'شركة {first_word}' أو 'بروتوكول {first_word}' أو 'عملة {first_word}'. أخرج JSON فقط فوراً."},
                        {"role": "user", "content": prompt},
                    ]
                    retry_result = _call(retry_msg)
                    if retry_result:
                        retry_data = _extract_json(retry_result)
                        if retry_data:
                            retry_dict = _build_result(retry_data, title, summary)
                            if retry_dict and not re.match(r'^[A-Za-z]', retry_dict["title_ar"]):
                                # نجحت المحاولة الثانية
                                return retry_dict
                    # فشلت المحاولة الثانية — نتخطى الخبر
                    logger.warning("❌ فشلت المحاولة الثانية — العنوان لا يزال يبدأ بانجليزي: %s", result_dict["title_ar"][:50])
                else:
                    return result_dict

    print("   ❌ فشلت الترجمة — تخطي الخبر")
    logger.warning("فشلت الترجمة — تخطي الخبر")
    return {"title_ar": "", "body_ar": ""}
