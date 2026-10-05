# US500 — إصلاح ISM Services عند الإصدار الجديد

## السبب الجذري المثبت

تشغيل 2026-10-05T15:11:07Z رفض ISM_SERVICES_PMI برسالة:
`ISM current-report period differs from latest dated calendar release`.

HTML المحفوظ من المصدر المباشر يحمل عنوان SEO ومسار تنقل قديمين: September 2025 ISM Services PMI Report. لكن عناوين h1 ومتن التقرير تحمل September 2026 وServices PMI 54.9. المحلل السابق كان يفرد الصفحة كلها ويأخذ أول تطابق للشهر/السنة، فاختار السنة القديمة قبل الوصول إلى التقرير المرئي. رزنامة ISM الصحيحة تعلن إصدار 5 أكتوبر 2026، فتوقف الدمج قبل canonical merge كما ينبغي.

كان المسار البديل لبيان ISM المنشور عبر PR Newswire محصورًا أيضًا في التصنيع، رغم أن صفحة ISM لدى الموزع تضمنت بيان الخدمات الجديد.

## التغيير

1. economic_official_sources_v1.py: إزالة head/title/scripts/styles من النص، وتحديد الفترة من عناوين h1 الخاصة بالتقرير. رفض الفترة المفقودة أو المتعددة، ثم الاستمرار في مقارنتها بأحدث إصدار مستحق في رزنامة ISM. لا تخفيف لبوابات التحقق ولا تواريخ ثابتة.
2. الملف نفسه: دعم Services في المسار البديل الموجود لبيانات ISM عبر PR Newswire. التحقق يشترط ملف الناشر ISM، رابط القطاع الصحيح، تطابق عنوان البيان ومرجعه وقيمته مع المتن، وdatePublished ذي timezone، ومطابقة يوم/وقت النشر مع الرزنامة الرسمية. فشل هذا البديل يبقى METADATA_UNVERIFIED/SOURCE_ERROR.
3. tests/test_ism_issuer_distribution.py: regressions لعنوان SEO ومسار تنقل قديمين مع تقرير صحيح، وSEO حديث مع تقرير مرئي قديم يظل مرفوضًا، ومسار الخدمات البديل، ورفض جهة إصدار أو وقت أو قيمة أو metadata غير صحيحة، وعدم استعمال بيان التصنيع للخدمات.

لا يتغير app.py أو منطق الاندماج أو Surprise/Regime أو Master/Autonomous أو manifest أو secret. لا توجد hard-coded قراءة 54.9 داخل كود المصدر. الأرقام الفعلية أدناه ناتجة عن تحليل الاستجابات، لا fixtures.

## التحقق بالاستجابات الحقيقية

- الصفحة المباشرة من ZIP المستخدم أعطت بعد الإصلاح: September 2026، actual=54.9، release_date=2026-10-05.
- اكتشاف بيان ISM لدى PR Newswire أعطى نفس المرجع والقيمة، وdatePublished=2026-10-05T10:00:00-04:00.
- الرابط المكتشف ديناميكيًا:
https://www.prnewswire.com/news-releases/services-pmi-at-54-9-september-2026-ism-services-pmi-report-302898421.html
- الجهة المثبتة: Institute for Supply Management.
- الرزنامة:
https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/

## الاختبار end-to-end

في نسخة معزولة: إعادة استخدام observations الرسمية الـ139 المحفوظة في تدقيق المستخدم للمؤشرات الـ13 الأخرى، وتحليل HTML ISM الأصلي مع الإصلاح، ثم validation للمؤشرات الـ14 → canonical merge → Surprise → Regime.

نجحت بوابة المؤشرات الـ14. أحدث Services observation في Surprise يساوي 54.9، بتاريخ 2026-10-05. تتطابق معه قراءة الصفحة المباشرة وبيان المصدر الموزع. إعادة الدمج أضافت صفر سجلات وكانت بايتات canonical الناتجة متطابقة. بقي vintage السابق محفوظًا وفق كود merge الحالي.

هذا اختبار إعادة تشغيل من الاستجابات الرسمية المحفوظة، مع جلب بيان ISM الموزع فعليًا؛ ليس إعادة اكتساب حية لكل المؤشرات الـ14. لم نكتب outputs الجديدة في public_data الحقيقي أو نسلمها كمنشورات. التشغيل التالي في GitHub يجلب المصادر مجددًا قبل النشر.

## الاختبارات

- `python -m pytest -q`: 488 passed، 6 pandas FutureWarnings، 26.26 ثانية.
- `python -m pytest tests/test_ism_issuer_distribution.py tests/test_economic_official_ingestion_v1.py -q`: النتيجة الفعلية في targeted-tests.log.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py -q`: 16 passed.
- `python scripts/verify_publication_integrity.py`: Match 106، Mismatch 0، Missing 0، Error 0.

أُعيدت بايتات ملفين يولدهما الاختبار القديم إلى النسخ الأصلية المطابقة للـmanifest بعد suite. لم يعدّل manifest لإخفاء mismatch. السجلات ونتيجة e2e موجودة في research_history/ism_services_parser_fix/evidence.

## التطبيق

فك ZIP في جذر نسخة المشروع الحالية، واستبدل الملفين Python المذكورين وارفعهما بطريقتك اليدوية. الحزمة تكمل النسخة الحالية ولا تستبدل المستودع كله. لم نقم commit أو push أو merge.

شغّل **Official Economic Ingestion Audit** أولًا. إذا نجح تحقق المؤشرات الـ14، شغّل **Autonomous Intelligence** مجددًا. إذا فشل مصدر آخر، تبقى بوابة التحقق مغلقة وتحتاج مراجعة artifact؛ هذا الإصلاح لا يضمن توفر كل المصادر دائمًا.

لا يلزم secret جديد أو اشتراك مدفوع. لا توجد بيانات وهمية أو تحايل على وصول مسجل/مدفوع. PR Newswire هنا موزع لبيان ISM الأصلي مع تحقق من جهة الإصدار، وليس تقويمًا تجاريًا بديلًا.

## محتويات ZIP

- economic_official_sources_v1.py
- tests/test_ism_issuer_distribution.py
- research_history/ism_services_parser_fix/evidence/full-tests.log
- research_history/ism_services_parser_fix/evidence/targeted-tests.log
- research_history/ism_services_parser_fix/evidence/publication.log
- research_history/ism_services_parser_fix/evidence/integrity-tests.log
- research_history/ism_services_parser_fix/evidence/e2e-result.json
- هذا التقرير
- PATCH_CONTENTS.json: المسارات وبصمات SHA-256.
