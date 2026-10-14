# إصلاح اكتشاف المؤتمر ومقارنة التقارير V2

مبني على main عند commit a5663d1bdbf6d5cdbc0edffd32666905dbce7760.
هذه الحزمة تضاف بعد إصلاح Beige Book السابق، وتستبدل ملفاتها المذكورة بنفس المسارات.

## الدمج والتشغيل

1. فك ZIP واستبدل الملفات داخل المستودع بنفس المسارات؛ أضف الملفين الجديدين
   fed_report_comparison_v2.py وfed_report_comparison_ui_v2.py والاختبارات والـfixtures.
2. احفظ التغييرات. من GitHub: Actions → Fed Intelligence → Run workflow.
3. ينتج workflow JSON حديثًا ويحدث manifest وينشرهما. بعد نجاحه، أعد فتح التطبيق
   واضغط Reload Fed snapshot.

لا توجد public_data مجمدة في الحزمة؛ تشغيل الكود مطلوب لإنتاج المقارنات الجديدة.
الكود وحده لا يجدد JSON القديم. لا تشغّل سكريبت تعديل الواجهة القديم بعد دمج هذه الحزمة.

إذا لديك تعديلات محلية أحدث، استخدم patch للتحقق والدمج بدل استبدال ملفاتك كاملة:

```bash
git apply --check Fed-Comparison-V2.patch
git apply Fed-Comparison-V2.patch
```

## ما تغير

- اكتشاف المؤتمر لم يعد يعتمد على روابط HTML الظاهرة فقط. الرابط الرسمي للنص
  قد يكون داخل إعدادات مشغل الفيديو أو تعليق HTML؛ في 16 سبتمبر كان PDF موجودًا
  رغم غياب رابط anchor ظاهر في الصفحة المفحوصة.
- يختبر البرنامج رابط PDF الرسمي المعتاد، ويتحقق من توقيع PDF، ومحتوى النص،
  ونوع الوثيقة وتاريخ الاجتماع. فشل الصفحة وحده لا يمنع محاولة جلب النص.
- النص الكامل ونص الافتتاح فقط لهما scope مختلف؛ لا تتم مقارنة النطاقين بصمت.
- تُستخرج أقوال الرئيس وحدها من المؤتمر. أسئلة الصحفيين لا تتحول إلى موقف للفيدرالي.
- البيان والمحاضر يستخرجان من محتوى article، دون القوائم والتذييل وبيانات المشاركة.
- أُصلح فك ترميز صفحات HTML إلى UTF-8 لمنع تلف علامات الاقتباس والشرطة بين الأصوات.
- مقارنة رقمية موثقة لقرار السياسة ونطاق الفائدة والتصويت عند ذكرها صراحة.
- عرض السابق والحالي لكل محور: التضخم والعمل والنمو والمخاطر والسياسة والسيولة والائتمان.
- لكل نص رابط مصدر وتاريخ اجتماع/جمع معلومات، وتاريخ نشر إذا كان مصرحًا به،
  ووقت رصد النص. تُحفظ جميع الجمل والمحاذاة في report_comparison.
- لا يوجد Keyword coverage أو Context Score في عرض Beige Book الجديد؛
  تظهر أعداد المناطق والرسائل السابقة والحالية مباشرة.
- نموذج Fed Policy Score القديم يبقى في JSON للتوافق، وعرضه داخل قسم اختياري منفصل؛
  لا يحدد نتيجة المقارنة الجديدة. مقارنة SEP الرقمية الموجودة تبقى مستقلة كما كانت.
- اختلاف الصياغة يوصف كاختلاف صياغة، ولا يتحول تلقائيًا إلى حكم hawkish/dovish.
  الأرقام التي يمكن مقارنتها تُحسب مباشرة؛ البيانات غير المدعومة تبقى غير قابلة للمقارنة.
- تقدير PCE الذي قاله الرئيس مثل «likely ... in August» يبقى بهذه الصفة والفترة في
  النص، ولا يستبدل بقيمة منشورة لاحقًا أو يحول إلى مقارنة رقمية مع فترة أخرى.
- فصل توفر المستند وحداثته عن معرفة تاريخ نشر نص المؤتمر. قد تكون كل النصوص
  والمقارنات متاحة بينما يبقى تاريخ نشر PDF غير معلوم بدقة.
- تظل PIT=UNKNOWN عند غياب إثبات تاريخ نشر النص؛ لا يستخدم تاريخ المؤتمر أو
  عنوان PDF كتاريخ نشر ولا تُفرض PIT_SAFE. Freshness يصف المستند الحالي المتحقق
  من اجتماعه، وليس ضمانًا لحفظ vintage تاريخية أو توفر المعلومات داخل اليوم.
- تواريخ as_of والعرض مبنية على UTC لتجنب تحولها إلى الغد حسب ساعة الجهاز.

## نتيجة الفحص الحي في 14 أكتوبر 2026

- الحالي: المؤتمر الرسمي لاجتماع 16 سبتمبر 2026؛ السابق: 29 يوليو 2026.
- نوع النصين: Full transcript / chair remarks؛ كلاهما قابل للقراءة.
- الفائدة: 3.50–3.75% → 3.75–4.00%، تحول النطاق +25 نقطة أساس.
- القرار: HOLD → RAISE.
- التصويت: 9–3 → إجماع في المؤتمر؛ البيان والمحاضر يذكران 12–0 صراحة.
- مقارنات النصوص جاهزة للبيان والمحاضر والمؤتمر وBeige Book: 4/4، إضافة إلى SEP.
- Beige Book: تسارع الأسعار 1 → 4 مناطق، نمو الأسعار القوي 1 → 3، نمو النشاط 10 → 9.
- تواريخ النشر للبيان وSEP والمحاضر مأخوذة من تسميات Released الصريحة.
- تاريخ نشر ملف المؤتمر نفسه غير مصرح به صراحة في المصادر المفحوصة؛
  ظهور UNKNOWN في هذا الحقل لا يعني أن المؤتمر غائب أو أن المقارنة فشلت.

## التحقق

117 اختبارًا ناجحًا: Fed والمقارنات والمصادر والتواريخ وPR-03 وPR-04 وانحدار الواجهة.
نجح فحص حي للنصين الرسميين وعرض الصفحة كاملة في Streamlit AppTest مع زر إعادة القراءة.
Publication Integrity: 106/106، mismatch=0، missing=0، error=0، للنسخة المفحوصة.
هذه الاختبارات لا تثبت دقة بقية البرنامج أو وجود قدرة تنبؤية أو edge.

لتشغيل التحقق نفسه محليًا:

```bash
python -m pip install -r requirements.txt pytest lxml
python -m pytest -q tests/test_fed_intelligence.py tests/test_fed_communication_dates_v1.py tests/test_fed_beige_evidence_v1.py tests/test_fed_report_comparison_v2.py tests/test_publication_integrity.py tests/test_point_in_time_integrity.py tests/test_ui_v3_safe_overlay.py tests/test_research_context_quality_ui.py tests/test_pr07_multi_module_ui.py tests/test_ath_ui_polish_v1.py tests/test_economic_ui_integration.py tests/test_stage15_final_ui_integration.py tests/test_ui_theme_v1.py
python fed_intelligence_export_v1.py
python scripts/verify_publication_integrity.py
```

المصادر الأساسية:
https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20260916.pdf
https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20260729.pdf
https://www.federalreserve.gov/monetarypolicy/fomcpresconf20260916.htm
https://www.federalreserve.gov/monetarypolicy/beigebook202610-summary.htm
https://www.federalreserve.gov/monetarypolicy/beigebook202608-summary.htm
