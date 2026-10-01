US500 Macro Intelligence V6.3 — Patch 3 Safe ZIP

هذا ZIP لا يستبدل app.py بنسخة مُعاد بناؤها من الذاكرة.
بدلاً من ذلك، يحتوي على سكربت آمن يغيّر فقط المواضع المتفق عليها في app.py الحالي.

الاستعمال:
1) فك ZIP.
2) انسخ apply_patch3.py إلى جذر المشروع بجانب app.py.
3) شغّل:
   python apply_patch3.py

الحماية:
- يتحقق السكربت من تطابق جميع المقاطع المستهدفة قبل تعديل الملف.
- إذا لم يتطابق أي مقطع، يتوقف بدون تعديل app.py.
- ينشئ نسخة احتياطية: app.py.pre_patch3
- لا يلمس public_data أو backend أو PIT أو scoring أو governance.

بعد التطبيق:
   python -m py_compile app.py
   python -m pytest -q

ولفحص الرموز المتبقية اختيارياً:
   grep -nE '▲|▼|↑|↓|→|✓|✔|⏳' app.py

لا تحذف أي نتيجة متبقية آلياً؛ راجعها أولاً.
