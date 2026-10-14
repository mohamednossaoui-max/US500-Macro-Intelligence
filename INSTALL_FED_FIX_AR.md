# إصلاح Beige Book وجودة بيانات Fed

الحزمة مبنية على main عند commit:
0992528d5590bb15d0a8d6254f236fc5fc608c02

## الدمج اليدوي

1. فك ZIP واستبدل ملفات الكود والاختبارات وworkflow في نفس المسارات داخل المستودع.
2. أضف الملفين الجديدين fed_beige_evidence_v1.py وfed_snapshot_ui_v1.py، ومجلد اختبارات fixtures.
3. احفظ التغييرات في GitHub. ثم Actions → Fed Intelligence → Run workflow.
4. بعد نجاح التشغيل ونشر JSON وmanifest، أعد فتح التطبيق واضغط Reload Fed snapshot.

لا تتضمن الحزمة public_data جاهزة: يصنع workflow البيانات الحديثة من المصدر الرسمي
وقت التشغيل ويحدّث manifest. استبدال الكود وحده لا يجدد JSON القديم.

إذا لديك تعديلات أحدث في app.py أو الملفات الأخرى، استخدم Fed-Evidence-Fix.patch
بدلاً من استبدال ملفاتك بالكامل. تحقق من قابلية تطبيقه أولاً:

```bash
git apply --check Fed-Evidence-Fix.patch
git apply Fed-Evidence-Fix.patch
```

## تحقق محلي بديل

```bash
python -m pip install -r requirements.txt pytest lxml
python -m pytest -q tests/test_fed_intelligence.py tests/test_fed_communication_dates_v1.py tests/test_fed_beige_evidence_v1.py tests/test_publication_integrity.py tests/test_point_in_time_integrity.py
python fed_intelligence_export_v1.py
python scripts/verify_publication_integrity.py
```

الاختبارات المحددة: 65 passed في التحقق المنجز لهذه الحزمة.

## السلوك المصحح

- Issue month يعرض YYYY-MM، وليس يوم 1 اصطناعيًا. يبقى مفتاح issue_date موجودًا بقيمة null للتوافق.
- publication_date من تسمية النشر الصريحة في فهرس Beige Book الرسمي؛ Last Update لا يستخدم كتاريخ نشر.
- فصل تاريخ جمع المعلومات information_cutoff_date عن النشر وعن retrieved_at.
- اختيار الإصدار حسب تاريخ النشر، وحجب إصدار منشور بعد as_of حتى لو كان شهر الرابط سابقًا.
- تحميل الإصدار السابق من النوع نفسه؛ فشل الإصدار الجديد لا يستبدل به إصدار قديم مع تسمية CURRENT.
- استخراج الملخص الوطني فقط: النشاط والعمل والأسعار؛ حذف القوائم والتذييل وملخصات المناطق من الحساب.
- مقارنة الأعداد المذكورة صراحة، وحفظ جمل الاستهلاك والائتمان والأسعار مع روابط المصدرين.
- العبارات والأعداد غير المدعومة تبقى مفقودة؛ غياب جملة ائتمانية لا يعني ثبات الائتمان.
- إزالة العد المتداخل لعبارات الدرجة. الأبعاد غير المتعرف عليها لا تحصل على 50 محايدة.
- حجب الدرجة الكلية عندما لا تتعرف الكلمات على 3 أبعاد و50% من الأوزان على الأقل.
  هذا حد تغطية للقراءة الآلية، وليس حد ثقة اقتصادية أو معيارًا للفيدرالي.
- أسماء Keyword balance توضح أن درجة Beige Book ليست موقف اللجنة من الفائدة.
- صفحة المؤتمر التي تحتوي فيديو أو روابط فقط لا تعتبر نص مؤتمر؛ يلزم PDF رسمي فعلي قابل للقراءة.
- عدم اشتقاق تاريخ نشر النص من تاريخ المؤتمر أو العنوان. غياب تاريخ نشر صريح يبقى UNKNOWN.
- التحقق من بيانات التاريخ لكل وثيقة؛ DATE_CHECKED يعني ترتيب تواريخ على مستوى اليوم فقط،
  ولا يضمن point-in-time داخل اليوم أو صحة vintage تاريخية. PIT_SAFE لا يسند تلقائيًا.
- اللقطة السابقة ليوم العرض توصف STALE، والوثائق الناقصة/التواريخ المفقودة توصف UNVERIFIED.
- قراءة ملف Fed مباشرة عند إعادة العرض وإظهار generated_at ومعرف بصمة اللقطة؛
  لا تستخدم طبقات التخزين المؤقت القديمة لهذا الملف. يظل الملف المحلي هو المصدر الأول.
  إن تأخر نشر checkout التطبيق، سيظهر معرف اللقطة القديمة؛ زر إعادة القراءة لا يحدّث GitHub بنفسه.

## النتيجة التي تحققت في 14 أكتوبر 2026

المصدر الحالي: publication 2026-10-14، information cutoff 2026-10-05.
السابق: publication 2026-09-02، information cutoff 2026-08-24.
- تسارع الأسعار: 1 → 4 مناطق.
- نمو الأسعار القوي: 1 → 3 مناطق.
- اتساع نمو النشاط: 10 → 9 مناطق.
- التوظيف المتواضع: 3 → 3؛ الطفيف: 4 → 5؛ الثابت: 5 → 4.

لم تكن تغطية الكلمات في التقرير الحالي كافية: score=null مع عرض الأدلة والمقارنة.
ظهر نص المؤتمر الصحفي مفقودًا في الاستخراج؛ لذلك DEGRADED وUNKNOWN/UNVERIFIED
مخرجات مقصودة، ولا ينبغي إجبارها على HIGH أو PIT_SAFE.

قد تتغير درجة Fed Policy بعد حذف صفحة المؤتمر من أدلة الحساب؛
آلية استبعاد المستندات المفقودة وإعادة توزيع الأوزان الموجودة تبقى كما هي.
Beige Book يبقى سياقيًا ولا يدخل مباشرة في Fed Policy Score.

## أدلة التحقق

- 65 اختبارًا: Fed وPR-03 وPR-04 والسيناريوهات الجديدة.
- فحص حي للاستخراج والمقارنة من مصادر الفيدرالي.
- تشغيل صفحة Fed في Streamlit AppTest على JSON القديم وعلى اللقطة الحية الجديدة، وزر إعادة القراءة، دون استثناءات.
- Publication Integrity: 106/106، mismatch=0، missing=0، error=0.
  هذا دليل سلامة نشر ملفات النسخة المفحوصة، وليس إثباتًا عامًا لصحة الاقتصاد أو البرنامج كله.

المصادر:
https://www.federalreserve.gov/monetarypolicy/publications/beige-book-default.htm
https://www.federalreserve.gov/monetarypolicy/beigebook202610-summary.htm
https://www.federalreserve.gov/monetarypolicy/beigebook202608-summary.htm
