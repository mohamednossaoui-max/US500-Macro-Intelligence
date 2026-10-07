# ATH Cause and Drawdown Depth V1

هذه إضافة بحثية إلى صفحة ATH الموجودة. تُظهر أدلة الحالات المحتملة، ولا تدعي معرفة السبب الحقيقي أو احتمال موثوق لعمق التراجع.

## التركيب والتشغيل

انسخ محتويات ZIP إلى جذر النسخة الحالية من المشروع مع الحفاظ على المجلدات. الإضافة تعتمد على الوحدات القائمة `ath_ema19_touch_research_v12.py` و`ath_extended_history_research_v10.py` وطبقة Publication Integrity. لا يلزم تغيير app.py أو secret جديد.

```bash
python -m pip install 'pandas>=2,<4' numpy pytest streamlit requests 'yfinance>=0.2,<2' 'pandas_market_calendars==5.5.0'
python -m pytest -q tests/test_ath_cause_context_v1.py tests/test_ath_cause_depth_research_v1.py
python scripts/verify_publication_integrity.py --public-data public_data
python ath_ema19_touch_research_v12.py --mode acquire --output ath_cause_run/acquisition
python ath_cause_depth_research_v1.py --cache ath_cause_run/acquisition --archive research_history/ath_cause_v1 --output ath_cause_run/study
```

يمكن تشغيل Workflow اليدوي **ATH Cause and Drawdown Depth Audit** دون تشغيل Autonomous Intelligence. يقرأ البيانات المنشورة الحالية؛ تشغيله لا يجلب تلقائيًا أحدث أخبار/سياق من جميع collectors. حدّث تلك الطبقات بالمسار المعتاد أولًا إذا كانت قديمة.

## الحفاظ على الأرشيف

نتائج GitHub Actions توجد في artifact باسم `ath-cause-and-depth-audit`. احتفظ بملفات `research_history/ath_cause_v1/snapshots/` الجديدة وأعدها إلى نفس مجلد المشروع قبل التشغيل التالي. الـworkflow لا يعمل commit أو push؛ بدون حفظ الـartifact لا يستمر تراكم الأرشيف بين runners. لا تغير `recorded_at` أو `available_at` إلى تاريخ المصدر: تاريخ الالتقاط الفعلي هو بداية المعرفة. نفس الأدلة لا تضيف snapshot مكررة.

ملف `ath_cause_depth_audit_v1.json` في مجلد الأرشيف ملخص اختبار سابق للعرض فقط، وليس توقعًا حيًا. لتحديث عرضه انسخ الملف الناتج من `ath_cause_run/study/` إلى مجلد الأرشيف بعد نجاح الاختبار. لا تنسخ أي مخرجات إلى public_data. عرض الصفحة نفسه للقراءة فقط ولا يكتب snapshot؛ الالتقاط يحدث عبر الأمر/الworkflow.

## تعريف الاختبار

أول إغلاق عند تراجع 3% من أعلى High معروف في الملف، مرة واحدة لكل دورة قمة. القرار متاح في اليوم التالي كـproxy؛ الهدف هو لمس −5/−10/−20/−30% خلال 63 جلسة لاحقة وقبل استعادة القمة. تُستبعد الأهداف الملموسة بالفعل وحالات غموض ترتيب الهدف واستعادة القمة داخل الشمعة. التدريب يستخدم فقط نتائج اكتمل رصدها قبل القرار وبحد أدنى 30 حالة. المرجع هو تكرار تاريخي متوسع مع smoothing، ويقارن به نموذج سعر ثم نموذج سعر وسياق على العينة المشتركة نفسها.

## ما لا تثبته الإضافة

قواعد العناوين الإنجليزية تنتج candidates فقط، اعتمادًا على feeds البرنامج القائمة؛ لا يوجد جمع جديد شامل من Reuters/AP. غياب الخبر يعني UNVERIFIED وليس غياب الخطر. التضخم والعمل والنمو directional surprise scores، وليست مستويات اقتصادية أو احتمال ركود. القواعد العددية thresholds بحثية معلنة، غير معايرة كاحتمالات. نموذج السياق يختبر خمس قنوات عددية، ولا يدّعي تدريب الأسباب الثمانية كأثر سببي.

بيانات الاختبار طويلة المدى هي ^GSPC النقدي، وليست ES أو أسعار US500 الخاصة بوسيطك. قمة الملف ليست بالضرورة ATH كاملًا. البيانات سبق فحصها في الأبحاث السابقة، فلا توجد عينة نهائية مستقلة. الاختبار قد ينتهي بنجاح تقني مع حالة INSUFFICIENT_HISTORICAL_CAUSE_VINTAGES؛ ذلك ليس نجاحًا للتوقع. الاحتمالات الحية محجوبة دائمًا في هذه النسخة حتى اختبار مستقل ومعايرة كافية. لا توجد أوامر تداول.
