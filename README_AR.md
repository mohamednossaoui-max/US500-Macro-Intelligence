نطاق تجميع System Health

تطبيق الخيار الثاني: الاحتفاظ بـBreadth وCross Asset في البرنامج وفي التحديثات، واستبعادهما فقط من حساب overall_health.
ارفع الملفات الأربعة مع الحفاظ على المسارات:
- system_health_monitor_v1.py
- autonomy_source_registry_v1.json
- app.py
- tests/test_health_scope_v1.py

بعد الرفع، شغّل Autonomous تشغيلًا جديدًا من main وانتظر نجاح Master ونشر البيانات. إعادة تحميل التطبيق وحدها لا تعيد توليد ملخص الصحة المنشور. لا ترفع ملفات الملخص يدويًا ولا تعدّل manifest.json.

التحقق: system_health_summary_v1.json يحتوي excluded_from_overall=[breadth,cross_asset] وassessed_layer_count=24 في التسجيل الحالي. على آخر حزمة تشخيص كانت النتيجة HEALTHY مع healthy=24 وattention=2 وstale=1. حالة كل طبقة الأصلية محفوظة. قد تبقى الحالة العامة DEGRADED/FAILED إذا ظهر سبب آخر أو تقادمت لقطة المراقبة أو فشل التحديث.
ستظهر عبارة توضيحية تحت ملخص صفحة System Health. لم يتغير تصميم البطاقات.

هذا ليس إصلاحًا للبيانات القديمة أو لتوقيت Cross Asset؛ حالات STALE وPIT_LIMITED تبقى صحيحة. لم يتغير أي حساب بحثي أو بوابة جودة أو PIT أو القرار أو محلل الأدلة أو جدول اختيار المصادر. استبعاد الوحدتين لا يغيّر DECISION READY إلى True تلقائيًا.

التراجع: إزالة affects_system_health=false وhealth_scope_reason من العقدتين، أو استعادة الملفات السابقة وإعادة تشغيل Master.
الاختبارات: 77 passed على Python 3.11؛ النتائج مرفقة.
