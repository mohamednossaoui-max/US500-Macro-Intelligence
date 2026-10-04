# US500 — بحث Edge لعمق التراجع، V3

## النتيجة الفعلية

لا توجد **ميزة تنبؤ مثبتة** أو نسبة ثقة مرتفعة موثقة حتى الآن. توسعة البيانات وتصحيح VIX لم يجعلا النموذج أفضل من الاحتمالات التاريخية. لم تُغيّر المعلمات بعد رؤية النتيجة، ولم تُحوّل الأخطاء إلى نسب نجاح.

هذه ترقية لمنهج الاختبار وجودة المدخلات وتجهيز السياق التاريخي؛ ليست نموذجًا معتمدًا للتداول. واجهة البرنامج لا تعرض احتمالات حية غير مثبتة.

## ما نُفذ

- دراسة 6728 إغلاقًا يوميًا للمؤشر النقدي ^GSPC، من 2000-01-03 إلى 2026-10-02. أسعار ES وUS500 لدى الوسيط لم تكن متاحة بهذه المدة؛ لا تنسب النتيجة إليهما.
- دراسة منفصلة تبدأ عند أول هبوط إغلاق من 3% إلى أقل من 5% من قمة إغلاق في التاريخ المتاح. لا تستخدم اختيارًا رجعيًا لما أصبح بولباك لاحقًا. حلقات القفز مباشرة إلى 5%، والعينات المبكرة وغير المكتملة مستبعدة من التدريب.
- التصنيف بعد بلوغ 3%: محدود أقل من 5%، متوسط من 5% إلى أقل من 20%، انهيار 20% فأكثر. الشهر وثلاثة الأشهر يقيسان أكبر هبوط من قمة إغلاق متحركة داخل المدة مع العمق المعروف وقت التفعيل؛ حتى الاستعادة يقيس القمة المرجعية الأصلية. هذه تعريفات بحثية وليست توقعًا عند ATH.
- تدريب زمني على نتائج اكتملت قبل كل تاريخ قرار، مع توحيد المقاييس داخل التدريب فقط. مقارنة السياق والأسعار والاحتمالات التاريخية على الحالات نفسها. تقدير عدم اليقين بكتل متتالية وتعديل للمقارنات المتعددة؛ هذا تشخيص تقريبي وليس ضمان تغطية إحصائية.
- VIX الرسمي من CBOE جُلب فعليًا HTTP 200. جميع جلسات الأسعار مطابقة بالتاريخ؛ 11 اختلافًا يتجاوز 0.02، وأكبر فرق 2.61 نقطة تقريبًا. التصحيح في staging البحث فقط، دون تغيير public_data أو manifest.
- Workflow يدوي لجلب بيانات اقتصادية ومالية كما ظهرت في vintage سابق عبر FRED/ALFRED. القيم الناقصة أو المصدر الفاشل لا تُستبدل بقراءة حالية أو قيمة حيادية.
- حفظ نتائج الاختبار وبروتوكوله وبصمات المصادر وإظهار حالة عدم إثبات edge في صفحة ATH Pullback Context. حفظ السياق اليومي السابق في Master مستمر كما في V2؛ لم يُنشر النموذج المرفوض في Autonomous.

## نتائج المقارنة

الخطأ Brier الأصغر أفضل. هذه أخطاء احتمالات متعددة الفئات، وليست نسب خسارة تداول أو نسب دقة.

| الأفق | حالات التقييم | حالات الانهيار | خطأ السياق | خطأ الأسعار | خطأ الاحتمالات التاريخية |
|---|---:|---:|---:|---:|---:|
| 1M | 16 | 0 | 0.7219 | 0.5645 | 0.5123 |
| 3M | 13 | 1 | 0.6131 | 0.5327 | 0.4864 |
| UNTIL_RECOVERY | 19 | 2 | 0.8061 | 0.6550 | 0.6177 |

كل الآفاق: **NO_CONFIRMED_EDGE**. الفترات 2019–2026 سبق فحصها في الدراسات الماضية؛ لذلك لا تمثل holdout مستقلًا جديدًا. البيانات تبدأ قرب قمة 2000 ولا تشمل تاريخًا سابقًا كافيًا لإثبات ATH قديم؛ بعض حلقات الأزمة الأولى مستبعدة، والانهيارات المؤهلة قليلة. لا يجوز تحويل أعداد العينات إلى احتمال السوق الحالي.

## مسار البيانات التاريخية الجديد

| السلسلة | الدلالة المستخدمة | الجهة الأصلية |
|---|---|---|
| PAYEMS | مستوى العمالة SA، آلاف الأشخاص؛ الفرق الشهري ×1000 يعطي وظائف NFP | BLS |
| UNRATE | معدل البطالة، شهري SA، % | BLS |
| CPIAUCSL | مؤشر CPI شهري SA؛ تغير الشهر والسنة المشتق من نفس vintage | BLS |
| PCEPILFE | مؤشر Core PCE شهري SA؛ تغير الشهر والسنة | BEA |
| A191RL1Q225SBEA | نمو GDP الحقيقي الفصلي بمعدل سنوي، قراءة مباشرة | BEA |
| INDPRO | مؤشر الإنتاج الصناعي الشهري SA | Federal Reserve |
| DFF | الفائدة الفيدرالية الفعلية اليومية؛ ليست تحليل موقف FOMC | Federal Reserve |
| T10Y3M | فارق عائد 10 سنوات و3 أشهر، نقاط مئوية | Federal Reserve / FRED |
| NFCI | ظروف مالية أسبوعية، Ending Friday، NSA | Chicago Fed |
| ANFCI | ظروف مالية معدلة أسبوعية، Ending Friday، NSA | Chicago Fed |

المصدر الوسيط هو FRED/ALFRED. الطلب يحدد realtime_start = realtime_end = اليوم السابق لتاريخ القرار المحافظ، ولا يستخدم بيانات اليوم الحالي بدل الماضي. يُراجع اسم السلسلة والتواتر والوحدات والتعديل الموسمي. تغير القيم المشتقة من مستويات متجاورة فقط، ولا تُجسر الأشهر المفقودة. قراءة المؤشر المعدل موسميًا سنويًا لا تُسمّى تلقائيًا قراءة الخبر الرسمية غير المعدلة موسميًا. مستويات المؤشرات ذات سنة أساس متغيرة ليست ميزات قابلة للمقارنة مباشرة عبر كل vintages.

تاريخ as-of الخاص بالمزود ليس تاريخ إصدار الوكالة: release_date وrelease_time يبقيان فارغين عندما لا يثبتان. تحفظ receipts غير قابلة للاستبدال بالبصمة، مع الاحتفاظ بالاستجابة المختلفة كمراجعة مستقلة. هذه طبقة ميزات بحثية، لا تستبدل ingestion المؤشرات الاقتصادية الـ14.

## ما عليك فعله الآن

1. فك ZIP في جذر المشروع مع المحافظة على الملفات الأخرى. الحزمة تراكمية وتتضمن تغييرات ATH السابقة الضرورية، ولا تتضمن المستودع الكامل.
2. من GitHub Actions شغّل **ATH Official Vintage Context Backfill**.
3. اترك `FRED_API_KEY` في Repository Secrets كما هو؛ لا ترسل قيمته إليّ. راجع سبب الفشل إن ظهر؛ يتم رفع artifact حتى عند تعذر بعض السلاسل.
4. نزّل artifact **ath-official-vintage-context-backfill** وأرسله لتحليل التغطية وتطوير اختبار السياق التالي. لا يلزم تشغيل Autonomous لجمع هذا artifact؛ هذا workflow للبحث دون publication.

الجلب التاريخي الموثق بـAPI لم يُشغّل محليًا: المفتاح داخل GitHub Secrets ولا يمكن قراءته من نسخة العمل. المحاولة المحلية توقفت صراحة برمز 2 لغياب FRED_API_KEY. اختبارات fixtures ناجحة لكنها لا تثبت تغطية كل endpoint أو كل vintage على الإنترنت.

## الاختبارات والتكامل

- `python -m pytest tests/test_ath_pullback_edge_v3.py tests/test_ath_official_vintage_backfill_v1.py -q`: **17 passed**.
- `python -m pytest -q`: **442 passed**, ستة FutureWarnings موجودة من pandas في economic modules، زمن 26.86 ثانية.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py -q`: **16 passed**.
- `python ath_pullback_edge_v3.py --official-vix research_history/ath_edge_v3/sources/VIX_History.csv --output research_history/ath_edge_v3`: نجاح، نتائج فعلية محفوظة.
- `python scripts/verify_publication_integrity.py`: **106 Match، 0 Mismatch، 0 Missing، 0 Error**. جرى استرجاع الملفين اللذين أعادت اختبارات المشروع توليدهما إلى بايتات النسخة المعتمدة؛ manifest لم يُغيّر لإخفاء mismatch.
- لا commit/push/merge/PR، ولا تداول، ولا نشر من هذه الجلسة.

## الأسرار والمصادر

FRED_API_KEY مطلوب فقط لجلب التاريخ عبر API. صفحة التسجيل: https://fred.stlouisfed.org/docs/api/api_key.html . CBOE لا يحتاج مفتاحًا لهذا الملف. لا Trading Economics مدفوع ولا أسرار داخل الكود أو artifact.

مراجع رسمية:
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
- صفحات السلاسل: https://fred.stlouisfed.org/series/PAYEMS ، وبقية IDs في الجدول بنفس المسار.

## ما يلزم لإثبات edge فعلًا

تغطية تاريخية صحيحة وقت القرار، حالات أزمات أكثر، مصادر مستقلة لأسعار ES وUS500، نموذج جديد بفرضية محددة يُعامل كتجربة جديدة، ثم اختبار مستقبلي لم يُستخدم للاختيار ومعايرة الاحتمالات. لا يمكن ضمان تحقق edge أو دقة مرتفعة حتى بعد توفيرها. هذه النسخة لا تجري ادعاء معايرة أو تضع هدف دقة مصطنعًا.

## ملفات الحزمة

`ath_pullback_edge_v3.py`: بناء الحلقات والتقييم وتصحيح VIX. `ath_official_vintage_backfill_v1.py`: جمع تاريخ as-of موثق وحفظ vintages. الاختباران الجديدان: حماية المواعيد والمعنى والمراجعات وفشل المصدر. Workflow الجديد: جلب يدوي read-only ورفع artifacts. تحديث UI: عرض البحث دون تنبؤ غير معتمد. بقية الملفات هي أساس V1/V2 للسياق والأرشيف واختبار النماذج وتكامل Master. ملفات research_history تضم النتائج والبصمات والمصدر وأدلة الاختبار.

قائمة كاملة:

- `.github/workflows/ath-official-vintage-backfill.yml`
- `.github/workflows/ath-pullback-context-audit.yml`
- `.github/workflows/us500-full-research-pipeline.yml`
- `ATH_PULLBACK_CONTEXT_README.md`
- `app.py`
- `ath_context_archive_v1.py`
- `ath_depth_model_research_v1.py`
- `ath_official_vintage_backfill_v1.py`
- `ath_pullback_context_ui_v1.py`
- `ath_pullback_context_v1.py`
- `ath_pullback_edge_v3.py`
- `research_history/ath_context_v1/snapshots/cd3c3b10f577e514ef66c7b719862194175170533bd2ca2669b19c6713c6a7ac.json`
- `research_history/ath_context_v1/snapshots/fd4307aa01bb9997cb4c28fe34a9d9a6ab76be7936ad2c7fb4ce0bc2340be5d4.json`
- `research_history/ath_depth_model_audit_v1.json`
- `research_history/ath_edge_v3/edge_v3_audit.json`
- `research_history/ath_edge_v3/edge_v3_events.csv`
- `research_history/ath_edge_v3/edge_v3_predictions.json`
- `research_history/ath_edge_v3/evidence/full-tests.log`
- `research_history/ath_edge_v3/evidence/integrity.log`
- `research_history/ath_edge_v3/evidence/live-backfill.log`
- `research_history/ath_edge_v3/evidence/pit-tests.log`
- `research_history/ath_edge_v3/protocol_record.json`
- `research_history/ath_edge_v3/sources/VIX_History.csv`
- `research_history/ath_edge_v3/sources/retrieval.json`
- `tests/test_ath_context_archive_v1.py`
- `tests/test_ath_depth_model_research_v1.py`
- `tests/test_ath_official_vintage_backfill_v1.py`
- `tests/test_ath_pullback_context_v1.py`
- `tests/test_ath_pullback_edge_v3.py`
- `tests/test_pullback_strategy_v1.py`
