# US500 ATH — إصلاح التحقق من السياق V7

هذه حزمة تكميلية فوق V6، وليست مستودعًا كاملًا. فك محتويات ZIP في جذر نسخة المشروع مع الحفاظ على المجلدات. لم يتم commit أو push أو تشغيل تداول، ولم يتغير app.py أو public_data أو manifest.

## ما تم إصلاحه

- CPIAUCSL في vintage 2026-01-06: نوفمبر 2025 متاح وأكتوبر مفقود. كان رفض MoM يرفض أيضًا مستوى المؤشر وYoY رغم إمكان حسابهما. أصبح MoM = null مع UNAVAILABLE_CONSECUTIVE_MONTH؛ يُحسب YoY فقط من الشهر نفسه قبل 12 شهرًا داخل vintage نفسه. لم يُجسر الشهر المفقود ولم تُخترع بيانات.
- Core PCE: كان العمر محسوبًا من بداية سبتمبر، 127 يومًا. أصبح من نهاية الفترة، 98 يومًا، مع إبقاء حد 120 يومًا؛ التحقق يرفض شهرًا غير مكتمل أو تاريخًا شهريًا ليس بداية الشهر. هذا فحص عمر إضافي وليس إثبات latest agency release.
- أضيف replay مستقل دون شبكة يطابق SHA-256 للاستجابات مع تدقيق الاكتساب وتواريخ القرار. لا يحصل على بيانات جديدة، ويرفض نقص/اختلاف الاستجابات. NFP يظل فرق مستويات الوظائف ×1000، وأي فجوة شهرية تمنع حسابه.
- تعرض الواجهة مقارنة السياق الكامل بالمرجع على نفس الحالات. أضيفت اختبارات replay إلى workflow اليدوي الموجود؛ Master وAutonomous لم يتغيرا لأن الدراسة لا تزال بحثية.

## نتائج إعادة التحقق الفعلية

350 صفًا: 333 ASOF_VERIFIED، 17 UNAVAILABLE_ARCHIVE، صفر SOURCE_ERROR، صفر STALE. حالة التغطية VERIFIED_AVAILABLE_ARCHIVE_PARTIAL_TOTAL. يوجد حقل مشتق واحد غير متاح: CPI MoM. بقاء الصف متحققًا لا يعني أن هذا الحقل أصبح متاحًا. تاريخ/وقت إصدار الوكالة غير مثبتين من provider as-of؛ لا تُعلن CURRENT أو اكتمال التغطية الكلية.

حُفظت الاستجابات الخام الـ333 الجديدة دون تعديل، ليصبح إجمالي cache 693 استجابة. تطابقت events وpredictions بالبايت عند إعادة الحساب من cache المدمج. أصبحت 27 من 35 قمة ذات سياق كامل. معلمات النموذج وقواعد اختيار القمم لم تتغير.

## هل يوجد edge؟

الأرقام التالية Brier، والأقل أفضل، وجميع الأعمدة تقارن نفس الحالات:

| المدة | الحالات | السعر | السوق | المرجع التاريخي | السياق الكامل |
|---|---:|---:|---:|---:|---:|
| 1M | 15 | 0.4071 | 0.4429 | 0.2963 | 0.3183 |
| 3M | 14 | 0.7704 | 0.8402 | 0.7467 | 0.8757 |
| UNTIL_RECOVERY | 15 | 0.0604 | 0.0390 | 0.0465 | 0.1742 |

النتيجة NO_CONFIRMED_EDGE. السياق الكامل أفضل من السعر والسوق لشهر واحد ولكنه أسوأ من المرجع التاريخي البسيط. لثلاثة أشهر أسوأ من الثلاثة. العينة صغيرة: حادث crash واحد في اختبار الثلاثة أشهر، وصفر في الشهر. جميع اختبارات حتى الاستعادة هنا بلا تراجع مهم؛ هذه المدة تنتهي بمجرد العودة إلى القمة الأصلية، وقد تنتهي في الجلسة التالية، وليست احتمال أزمة مستقبلية. لا توجد احتمالات حية معتمدة أو ضمان عمق التراجع.

الدراسة تختبر قمم إغلاق المؤشر النقدي المتاحة منذ 2000، وليست إثبات ATH داخل الجلسة أو أسعار ES/US500 الخاصة بالوسيط. السنوات سبق فحصها، فهذه دراسة استكشافية لا holdout مستقل. تاريخ توفر أسعار الإغلاق مؤشَّر محافظ لليوم التالي، وليس timestamp إصدار مثبتًا. أرشيف VIX الرسمي الحالي ليس إثبات vintages تاريخية كاملة.

## الاختبارات

- `python -m pytest -q`: 467 passed، 6 تحذيرات pandas FutureWarning، 25.23 ثانية؛ لا failures.
- `python -m pytest tests/test_ath_record_high_research_v6.py tests/test_ath_official_vintage_backfill_v1.py tests/test_ath_macro_edge_research_v4.py tests/test_ath_vintage_receipt_replay_v1.py -q`: النتيجة محفوظة في evidence/v7/targeted-tests.log.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py -q`: 16 passed.
- `python scripts/verify_publication_integrity.py`: 106 Match، 0 Mismatch، 0 Missing، 0 Error.

الاختبارات الموجودة تولد وقتًا جديدًا في ملفين من public_data؛ أُعيدت بايتاتهما الأصلية المطابقة للـmanifest بعد الاختبار. لم يُعدّل manifest لإخفاء اختلاف.

## إعادة التنفيذ دون شبكة

من جذر المشروع بعد تطبيق الحزمة:

```bash
python ath_vintage_receipt_replay_v1.py --events research_history/ath_record_high_v6/record_high_v6_events.csv --acquisition-audit research_history/ath_official_vintages_v1/record_high_acquisition_audit_2026_10_05.json --cache research_history/ath_official_vintages_v1 --output ath_record_replay/vintages
python ath_record_high_research_v6.py --official-vix research_history/ath_record_high_v6/sources/VIX_History.csv --cache ath_record_replay/vintages --output ath_record_replay/study
python scripts/verify_publication_integrity.py
```

لجلب vintages جديدة لاحقًا استخدم ATH Record High Context Audit. يتطلب الاكتساب الشبكي Secret الموجود FRED_API_KEY؛ replay لا يتطلب أي مفتاح. لا يلزم تشغيل Autonomous لقراءة نتائج هذه الدراسة؛ هذه الحزمة لا تنشر توقعات حية.

## محتويات الحزمة

- طبقة backfill: تصحيح عمر الفترة والتحقق المستقل للحقول المشتقة.
- replay جديد، وملفا regression tests.
- واجهة الدراسة: مقارنة درجات النموذج والمرجع.
- workflow التدقيق: تشغيل اختبارات replay.
- استجابات رسمية جديدة، وتدقيق الاكتساب الأصلي وإعادة التحقق.
- نتائج V6 المعاد حسابها، VIX المدخل الفعلي، وسجلات الاختبارات والسلامة.

القائمة الكاملة والمسارات وSHA-256 موجودة في PATCH_CONTENTS.json داخل ZIP. يُطبق فوق ملفات V6 السابقة، بما فيها ath_record_high_research_v6.py؛ نموذج V6 نفسه لم يتغير. تحسين جودة المدخلات هنا لا يثبت أفضلية تنبؤية. الخطوة البحثية التالية تحتاج تعريفًا مستقرًا للهدف وعينة أوسع واختبارًا مستقلًا قبل أي توقع حي.
