# دمج أدلة Fed داخل واجهة البرنامج

هذه الحزمة تربط العرض بصفحة Fed Intelligence الحالية، وتقرأ مقارنة الوثائق من
اللقطة المنشورة الفعلية fed_intelligence_output_v1.json عبر المسار الموجود أصلًا
في app.py. لا تعتمد على مجلد التجربة السابق ولا تقرأ بيانات المثال التوضيحي.

## التركيب

فك ضغط الحزمة، ثم انسخ محتوياتها إلى جذر المستودع على فرع main مع حفظ المسارات:

- أضف fed_evidence_panel_v1.py بجانب app.py.
- استبدل fed_report_comparison_ui_v2.py بالنسخة المرفقة.
- أضف tests/test_fed_evidence_panel_v1.py داخل مجلد tests.

يجب حفظ الملفين الأولين في المستودع معًا، ثم حفظ التغييرات Commit changes.
لا ترفع ZIP نفسه بوصفه ملف البرنامج؛ ارفع محتوياته بعد فك الضغط. عند تحديث
الشفرة في main سيعيد Streamlit تحميلها. حدّث صفحة التطبيق ثم افتح Fed Intelligence.

لا يلزم تعديل app.py: صفحته تستدعي compact_comparison بالفعل، وقد أضيف الربط
داخل هذه الدالة. لا يلزم تشغيل Autonomous لتظهر الواجهة الجديدة.

## ما الذي يجب أن يظهر؟

داخل قسم Communication — Current vs Previous، أسفل بطاقة FOMC Statement:

**Fed Evidence — What changed?**

أربع بطاقات للسابق والحالي: Policy decision وTarget range وVote وDissent preference.
تُميّز CHANGED وUNCHANGED وNOT COMPARABLE، وتعرض أبرز تغيرين نصيين في الأدلة
المستخرجة. تبقى المقارنة التفصيلية القديمة متاحة أسفلها.

أسفل بطاقة المؤتمر يظهر **Press Conference — Evidence & timing**. لا تُنسب
اعتراضات أعضاء اللجنة إلى أسئلة الصحفيين، ولا تتم مقارنة افتتاحية بنص كامل.

يمكن فتح sources and timing لرؤية المصدر الرسمي وتاريخ الاجتماع وتاريخ النشر
ووقت التقاط النسخة ونطاق النص وبصمته إذا كانت مسجلة. يظل وقت النشر غير موثق
إذا كان المتاح تاريخًا فقط، ولا يُفترض أن النص FINAL أو PRELIMINARY ما لم يسجله
الجامع صراحة. هذه معلومات عرض؛ لا تعيد تصنيف PIT أو Quality Gate.

في لقطة 28 أكتوبر المرفوعة سابقًا، تعرض البطاقات HOLD واعتراضًا باتجاه RAISE.
هذه قيم تلك اللقطة فقط، وليست أرقامًا ثابتة في الواجهة. إذا تغير التقرير المنشور
لاحقًا ستقرأ الواجهة قيمه الجديدة تلقائيًا.

## ما الذي لا تعالجه الحزمة؟

الحزمة لا تجلب إصدارات جديدة ولا تصلح تأخر البيانات بذاتها. إن كانت اللقطة
المنشورة قديمة، تظهر الإضافة الجديدة مع بياناتها الحالية وتواريخها الأصلية.
ولا تضيف وزنًا لـFed إلى Decision Engine، ولا تغيّر Decision State أو درجات
Fed أو System Health أو ملفات public_data أو manifest.json.

لا تُحسب نبرة hawkish/dovish من اختلاف الكلمات في هذه الإضافة، ولا يُستنتج
أن tightened تعني أن المستوى tight. النص المعروض هو الدليل للمراجعة البشرية.

## التحقق

```bash
python -m pytest -q tests/test_fed_evidence_panel_v1.py tests/test_fed_report_comparison_v2.py tests/test_fed_intelligence.py tests/test_fed_communication_dates_v1.py tests/test_fed_beige_evidence_v1.py tests/test_publication_integrity.py tests/test_point_in_time_integrity.py tests/test_ui_theme_v1.py
```

تم التحقق محليًا ضمن مجموعة أوسع: 168 اختبارًا ناجحًا، تتضمن فتح صفحة Fed
Intelligence الفعلية واختيارها من قائمة التنقل، وثبات الدرجة المعروضة، وصفحة
Financial Stress وسلامة النشر وPIT. لم تُجرَ عملية نشر إلى GitHub أو Streamlit
من هذه الجلسة؛ الحزمة جاهزة للنسخ إلى المستودع.

للرجوع: استعد النسخة السابقة من fed_report_comparison_ui_v2.py، ثم احذف
fed_evidence_panel_v1.py. لا يلزم تعديل اللقطة المنشورة أو إعادة حساب الدرجات.
