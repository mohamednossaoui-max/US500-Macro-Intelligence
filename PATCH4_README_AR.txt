US500 Macro Intelligence V6.3 — PATCH 4

الملفات:
- apply_patch4.py       تطبيق Patch 4
- restore_patch4.py     استعادة النسخة السابقة

الطريقة:
1) ضع apply_patch4.py و restore_patch4.py بجانب app.py الحالي نفسه.
2) لا تنشئ app.py.pre_patch4 بنفسك؛ السكربت ينشئه تلقائياً قبل التعديل.
3) شغّل:
   python apply_patch4.py
4) يجب أن ترى:
   PATCH 4 APPLIED SUCCESSFULLY
5) تأكد أن app.py.pre_patch4 ظهر بجانب app.py.
6) اختبر الصياغة:
   python -m py_compile app.py
7) شغّل Streamlit بالطريقة المعتادة لديك وراجع الصفحات.

الحماية:
- السكربت يقبل فقط app.py المرفوع لهذا Patch ببصمة SHA-256 محددة.
- يتحقق أيضاً من بصمات V6.3 الداخلية.
- يبني التعديلات في الذاكرة ويتحقق من Python syntax قبل لمس app.py.
- ينشئ app.py.pre_patch4 قبل الكتابة.
- إذا فشل التحقق بعد الكتابة، يعيد النسخة الأصلية تلقائياً.

الاستعادة:
   python restore_patch4.py

النطاق:
Presentation/UI only. لا يغيّر loaders أو manifest أو PIT أو scoring أو governance أو Decision Engine أو Fed calculations.
الجداول الخام التي تم استهدافها تبقى متاحة داخل expanders مغلقة افتراضياً.
Data Explorer لم يتم تحويله لأنه واجهة تدقيق خام مقصودة.
