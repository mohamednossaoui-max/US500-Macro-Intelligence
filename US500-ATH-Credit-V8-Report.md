# US500 — اختبار عامل الائتمان V8

حزمة تكميلية فوق V7. تنفيذ إطار البحث والجلب والتحقق مكتمل؛ تقييم العامل على بيانات الائتمان الفعلية ينتظر تشغيل Workflow بمفتاح FRED الموجود لدى المستخدم. لا توجد نتيجة edge جديدة الآن.

## العامل المختار وما يقيسه

BAA10Y: فرق عائد سندات الشركات Baa وعائد الخزانة لعشر سنوات. المصدر FRED / Federal Reserve Bank of St. Louis، وحدة Percent، Daily، Not Seasonally Adjusted. هذا ليس Excess Bond Premium وليس Option-Adjusted Spread؛ لا ننقل له نتائج دراسة EBP كأنها إثبات لهذا العامل.

High Yield OAS كان مرشحًا، لكن صفحة BAMLH0A0HYM2 الرسمية تذكر أن السلسلة أصبحت تعرض 3 سنوات بدءًا من أبريل 2026، لذلك لم نعتمدها لأرشيف منذ 2000. مدى توفر vintages BAA10Y نفسه سيُثبت عبر API عند الاكتساب، ولا نفترض أن التاريخ كله متاح.

المصادر التي روجعت:
- https://fred.stlouisfed.org/series/BAA10Y
- https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- https://www.federalreserve.gov/econresdata/notes/feds-notes/2016/recession-risk-and-the-excess-bond-premium-20160408.html

## البروتوكول قبل جلب النتائج

- نفس قمم V6، ونفس التصنيفات والآجال ونفس المعلومات الزمنية المتاحة. لا نختار قممًا بناءً على التراجع الذي حدث بعدها.
- خاصيتان من عامل واحد: مستوى spread وتغيره خلال 30 يومًا تقويميًا، بوحدة النقاط المئوية، لا معدل العائد النسبي ولا basis points.
- المقارنة الأساسية: MARKET_PLUS_CREDIT مقابل MARKET والمرجع CLIMATOLOGY خلال 3 أشهر. المقارنات الأخرى استكشافية: PRICE، CREDIT_ONLY، PRICE_PLUS_CREDIT؛ الشهر وحتى الاستعادة آجال ثانوية.
- تدريب walk-forward بحد أدنى 12 حالة مكتملة، باستخدام نتائج أصبحت معلومة قبل القرار فقط. Ridge penalty=10 كما في V6، ولا يتم ضبط المعلمات بعد رؤية أداء الائتمان.
- جميع النماذج والمرجع على نفس الحالات ذات الميزات المكتملة. لا نقارن أرقامًا من عينات مختلفة.
- السنوات سبق فحصها؛ هذه دراسة استكشافية وليست عينة مستقلة جديدة. لا يثبت Brier أفضل وحده edge ولا يفتح توقعات حية.

## حماية البيانات

لكل قمة: as-of هو اليوم السابق لتاريخ القرار المحافظ. API يجب أن يعيد realtime_start=end بنفس اليوم؛ بيانات اليوم لا تحل محل vintage تاريخي. عمر آخر observation لا يزيد على 10 أيام؛ خط أساس التغير عند آخر تاريخ متاح قبل مستوى اليوم ناقص 30 يومًا، وبتأخر أقصاه 10 أيام. لا نستخدم تاريخًا لاحقًا لسد فجوة الخط الأساس.

الفشل أو stale أو خط الأساس المفقود يمنع القيمة. الفجوة قبل أول vintage يجب أن تكون مثبتة عبر series/vintagedates. الاستجابات تُحفظ ببصمة SHA-256 ولا تستبدل مراجعة سابقة؛ تعارض بصمات vintage واحد يتوقف للمراجعة. لا نختلق agency release_date من provider as-of.

لم نضع سجلات ائتمان حقيقية أو API keys في ZIP. لا توجد البيانات المطلوبة في cache السابق؛ التشغيل المحلي الفعلي أعطى BLOCKED_INSUFFICIENT_VERIFIED_CREDIT، صفر حالات تقييم، ودرجات null. هذه نتيجة منع مقصودة وليست اختبار أداء ناجحًا. لا توجد fallback محايدة أو forecast حية.

## الاختبارات الفعلية

- `python -m pytest -q`: 480 passed، 6 pandas FutureWarnings، 25.27 ثانية.
- `python -m pytest tests/test_ath_credit_edge_research_v8.py tests/test_ath_record_high_research_v6.py -q`: 21 passed.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py -q`: 16 passed.
- `python scripts/verify_publication_integrity.py`: 106 Match، 0 Mismatch، 0 Missing، 0 Error.
- end-to-end بfixtures معلنة: جلب 16 vintage → SHA/semantics/as-of validation → المقارنة → إعادة التشغيل بنتائج متطابقة بالبايت ودون تضخم receipts. هذه fixtures تتحقق من البرنامج ولا تثبت اتصال المصدر أو وجود edge.
- التشغيل الفعلي دون بيانات ائتمان منع التقييم، exit 1. التشغيل الشبكي لم ينفذ محليًا لأن FRED_API_KEY غير موجود هنا؛ لم نطلب قيمته من المستخدم.

اختبارات المشروع القديمة تعيد توليد وقت داخل ملفين من public_data؛ أُعيدت بايتاتهما الأصلية المطابقة للـmanifest بعد الاختبار. لم يتغير manifest أو app.py أو بيانات النشر أو Master/Autonomous.

## ما يفعله المستخدم الآن

1. فك ZIP في جذر نسخة المشروع بعد تطبيق V7، مع الحفاظ على المجلدات.
2. أضف الملفات إلى GitHub بطريقتك اليدوية المعتادة؛ لم نقم بأي commit أو push.
3. GitHub → Actions → **ATH Credit Edge Audit** → Run workflow.
4. بعد التشغيل نزّل artifact **ath-credit-edge-audit** وأرسله للمراجعة.

Secret: **FRED_API_KEY**، إلزامي للاكتساب الشبكي، وهو الموجود بالفعل لديك. الحصول عليه مجاني من https://fred.stlouisfed.org/docs/api/api_key.html . لا حاجة إلى مفتاح جديد أو خدمة مدفوعة، ولا ترسل قيمة المفتاح في المحادثة.

Workflow يدوي، contents: read؛ يسجل البروتوكول أولًا، يعيد اختيار قمم V6 من بيانات المشروع، يجلب BAA10Y عند التواريخ المطلوبة، ويتوقف قبل المقارنة إذا فشل التحقق من المصدر. يحفظ التشخيص حتى عند الفشل. لا يكتب public_data ولا ينشر أو ينفذ تداولًا. استجابات المصدر محفوظة في staging البحثي؛ السلسلة تتضمن حقوق Moody’s، فلا تُضف الاستجابات الخام إلى المستودع العام.

لا يلزم تشغيل Autonomous لهذا الاختبار. نتائجه لا تُدمج في توقع حي. لم نضف breadth بعد؛ سنختبر الائتمان أولًا دون خلط عدة تعديلات.

## الملفات

- ath_credit_edge_research_v8.py: جلب/تحقق/حساب خاصيتي الائتمان ومقارنة walk-forward، CLI protocol/acquire/study.
- tests/test_ath_credit_edge_research_v8.py: regressions والتحقق من source failure وPIT وidempotency وend-to-end.
- .github/workflows/ath-credit-edge-audit.yml: التدقيق اليدوي باستخدام Secret الموجود.
- research_history/ath_credit_v8/credit_v8_protocol.json: الفرضية والقواعد الثابتة قبل الاكتساب الحقيقي.
- research_history/ath_credit_v8/credit_edge_v8_audit.json: نتيجة التشغيل المحلي الممنوع لغياب vintages.
- research_history/ath_credit_v8/evidence/: سجلات الاختبارات والسلامة والتشغيل المحلي.

PATCH_CONTENTS.json يسرد كل مسار وبصمته. هذه حزمة دراسة مكتملة تقنيًا، وليست إعلان نجاح تنبؤي؛ الحكم على العامل يحتاج تشغيل البيانات الحقيقية والتحقق من النتائج.
