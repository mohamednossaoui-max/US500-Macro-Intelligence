# US500 — Canonical Workspace Gate Fix

## السبب المثبت
فحص الكود الحالي من main على GitHub كشف أن economic_canonical_input_v2.py القديم لا يستخدم argparse ولا يقرأ --workspace. رغم تمرير الخيار من refresh_research_data_v2.py، يعيد الملف القديم نسخ canonical من public_data فوق المخرجات التي نجح ingestion في دمجها. لذلك تفشل بوابة release-aware، وهو السلوك الذي ظهر في الصورة.
أُعيد إنتاج الفشل بنسخة الملف الفعلية المحمّلة من GitHub، باستخدام canonical merged الحقيقي من economic-official-source-audit.zip. فشلت المطابقة في NFP، UNEMPLOYMENT_RATE، AVERAGE_HOURLY_EARNINGS، CORE_PPI، GDP، PCE_PRICE_INDEX، CORE_PCE، RETAIL_SALES، INITIAL_JOBLESS_CLAIMS، ISM_MANUFACTURING_PMI.
النسخة المصححة --workspace تتحقق من ملفات workspace دون نسخ public_data؛ حافظت على bytes البيانات المدموجة تمامًا، ونجحت مطابقة 14/14.

## التثبيت
استبدل ملفات الحزمة في نفس المسارات داخل المشروع. الملفات الثلاثة الأولى في جذر المستودع، والاختبارات في tests/.
شغّل من جديد Workflow: Official Economic Validated Refresh.
عند النجاح نزّل artifact: economic-official-validated وأرسله للمراجعة قبل تثبيت public_data وتوليد manifest بالطريقة المعتمدة.
هذا التصحيح لا يغير workflow أو المفاتيح، ولا يحتاج self-hosted. لا تعطّل بوابة التحقق.

## الملفات
- economic_canonical_input_v2.py
- economic_surprise_engine_v1.1.py
- economic_regime_classifier_v1.5.py
- tests/test_canonical_workspace_bridge.py
- tests/test_economic_official_ingestion_v1.py
- US500-Canonical-Workspace-Gate-Notes.md

## لماذا تضم الحزمة Surprise وRegime؟
مقارنة الملفات الحالية على GitHub بالنسخ المصححة كشفت أن تعديلات PIT الخاصة بمراجعات المصدر لم تكن موجودة في نسختي المحركين أيضًا.
Surprise يستخدم available_as_of كتاريخ المعرفة ويحافظ على المراجعات التاريخية، ويستبعد source_snapshot_history من عينات الصدمات المستقلة وrolling Z-score. Regime يختار السجلات حسب تاريخ المعرفة الفعلي ويضيف أيام المعرفة إلى تواريخ snapshots. هذه التعديلات تمنع backdating revision أو تضخم عينات history، ولا تغيّر بوابات قبول المصادر.
الاختبارات تغطي workspace bytes preservation، missing workspace fail-closed، legacy staging، مصدر/metadata/revision/idempotency/PIT وdownstream.
point_in_time.py الموجود حاليًا على GitHub يطابق النسخة المصححة؛ لم يُضف إلى الحزمة لأن تغييره غير لازم.

## التحقق الفعلي
- python -m pytest -q tests: 324 passed, 19 existing pandas FutureWarnings, 21.36s.
- إعادة إنتاج الفشل من نسخة GitHub الحالية: PASS (confirmed old bridge overwrites merged canonical).
- نفس actual merged input مع النسخة المصححة: exact bytes preservation و14/14 latest-release parity PASS.
- Replay isolated end-to-end باستخدام observations.csv الفعلي من economic-official-source-audit.zip: validation -> canonical merge -> workspace bridge -> Surprise -> Regime -> release-aware gate -> Macro/Research/Decision rebuild -> canonical manifest rebuild -> integrity PASS.
- Historical records محفوظة؛ merge أضاف 51 سجلًا وإعادته أضافت 0.
- Canonical وSurprise يطابقان official latest reference/date/value للمؤشرات الـ14.
- درجات وتاريخ snapshot Regime/Macro/Research متطابقة بعد إعادة البناء.
- Publication Integrity للمخرجات المعاد بناؤها: Total 101, Match 101, Mismatch 0, Missing 0, Error 0.
- Publication Integrity للنسخة الأصلية بعد استعادة بيانات اختبارات regression: 101/101 PASS أيضًا.

## حدود النتيجة
الـReplay يستخدم evidence وobservations من الجلب الحقيقي الناجح على GitHub؛ لا يدّعي إجراء جلب حي جديد محليًا. إعادة تشغيل workflow تجلب من المصادر وتتحقق قبل الدمج.
لم يجرِ commit/push/merge/PR/deploy أو تعديل public_data بالمستودع الأصلي. app.py غير معدل. لا تداول.
لا يُعلن اكتمال تحديث الموقع حتى نجاح workflow وتثبيت المخرجات وتحقق Publication Integrity بعد التثبيت.
