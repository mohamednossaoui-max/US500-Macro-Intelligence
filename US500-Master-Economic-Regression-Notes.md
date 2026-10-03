# US500 — إصلاح أخطاء Master الاقتصادية الثلاثة

## السبب المؤكد

قورنت الملفات الفعلية من GitHub مع نسخة العمل. أُعيد إنتاج أخطاء الصورة الثلاثة باستخدام الاختبارات القديمة وكاشف due الموجود في GitHub والبيانات المنشورة ذات 613 صفًا: 3 failed.

1. test_all_14_staging_merge_and_downstream_e2e كان يستخدم canonical الإنتاج المتغير مع NOW تجريبي 2026-10-02. البيانات الإنتاجية تحتوي vintages متاحة منذ 2026-10-03، فلا تستطيع fixture الأقدم استبدال ما هو أحدث عند بوابة المطابقة؛ هذا سلوك PIT الصحيح. أصبح الاختبار يبني baseline اقتصاديًا ثابتًا بتاريخ سابق للـfixture، مع تاريخ كافٍ ومتغير لتشغيل Surprise/Regime/Analog/Decision، ثم يتحقق من المصدر → merge → downstream بنفس الشروط. لا تغييرات على production gates أو قيم الإنتاج.
2. test_price_series_publish_mom_and_yoy_for_ui كان يختار الصف الأخير بعد ترتيب release_date وحده. المراجعات والإثراء تتشارك التاريخ؛ لذلك قد يختار فترة تاريخية لا تحمل YoY. يستخدم الآن economic_observation_order_v1.latest، كما تستخدم الواجهة المصححة. شرطا وجود mom وyoy ما زالا إلزاميين لجميع مؤشرات الأسعار الستة.
3. autonomy_due_detector_v1.py في GitHub كان يعتبر تعديل ملف اليوم دليلًا على عدم الحاجة إلى الجلب. أصبح Economic وEvent News والجذور release_driven مرشحة لفحص المصادر عند كل تشغيل، ولو أعيد بناء الملفات الآن. القرار بأن المصدر CURRENT يبقى مسؤولية ingestion release-aware، لا عمر الملف. اختبار Economic يتحقق أيضًا مع cadence daily قديمة لمنع تخطيه نتيجة registry قديمة.

## الملفات

- autonomy_due_detector_v1.py: إصلاح قرار وجوب فحص مصدر Economic.
- tests/test_economic_official_ingestion_v1.py: fixture اقتصادي ثابت، حفظ حالة الدمج في بيئة E2E، تاريخ context صريح داخل الاختبار، واختبار cadence قديمة.
- tests/test_economic_ui_integration.py: اختيار أحدث فترة ومعرفة بالطريقة المعتمدة؛ لم تخفف شروط الحقول.

لا تغيير في app.py أو public_data أو manifest أو workflows في هذه الحزمة.

## التحقق الفعلي

قبل الإصلاح في نسخة معزولة: الاختبارات الثلاثة نفسها: **3 failed**.

بعد الإصلاح:

`python -m pytest -q tests/test_economic_official_ingestion_v1.py::test_all_14_staging_merge_and_downstream_e2e tests/test_economic_official_ingestion_v1.py::test_economic_due_even_after_file_rebuild tests/test_economic_ui_integration.py::test_price_series_publish_mom_and_yoy_for_ui`

**3 passed in 7.60s**.

`python -m pytest -q`

**336 passed, 6 warnings in 17.37s** في نسخة العمل المحلية. عدد اختبارات نسختك في GitHub قد يختلف لأن ملفات إضافية موجودة هناك؛ لم ندّع تشغيلها جميعًا من البيئة المحلية. pandas FutureWarnings فقط.

`python scripts/verify_publication_integrity.py --public-data public_data`

**101 MATCH; Mismatch=0; Missing=0; Error=0** على البيانات الرسمية المثرية السابقة دون تعديلها.

## التثبيت والخطوة التالية

فك ZIP. استبدل autonomy_due_detector_v1.py في الجذر، والملفين الآخرين داخل tests بنفس الأسماء. لا تضعهما في مجلد فرعي إضافي.

ثم أعد تشغيل **Complete US500 Research Pipeline** من GitHub Actions. النجاح المحلي ليس إعلانًا بأن تشغيل GitHub الجديد أو نشره قد حدث؛ يجب الاطلاع على نتيجة التشغيل بعد تركيب هذه الملفات.

لا مفاتيح جديدة، ولا commit/push/merge أو تداول من جانبي.

## محتويات ZIP

- autonomy_due_detector_v1.py
- tests/test_economic_official_ingestion_v1.py
- tests/test_economic_ui_integration.py
- US500-Master-Economic-Regression-Notes.md
