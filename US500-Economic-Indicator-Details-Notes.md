# Economic Indicator Details — تصحيح السابق والقراءة والسنوي

## الأسباب الفعلية

- بطاقات Economic Indicator Pulse في app.py كانت تعرض الحالي دون مقارنة السابق.
- _latest_release كان يرتب بتاريخ الإصدار وحده، ولذلك قد يختار شهرًا تاريخيًا عند تساوي تواريخ تحديث عدة مراجعات. أصبح الاختيار يعتمد الفترة المرجعية ثم وقت إتاحة المعرفة.
- Collector BLS لم يحفظ mom أو yoy؛ Collector BEA أسقط mom الموجود في parser ولم يستخرج السنوي. أضيف استخراج السابق من جدول الإصدار BEA مع التحقق من الشهر الحالي والماضي ومطابقة قيمة الحالي.
- merge كان يتجاوز الإصدار المتطابق في actual حتى لو وصلت تفاصيل إضافية موثقة. أصبح يضيف metadata enrichment كنسخة لاحقة مع حفظ الصف السابق ووقت المعرفة، دون مضاعفة عينات Surprise أو مدخلات Regime.

## التثبيت

فك ZIP وارفع الملفات في المسارات المطابقة إلى جذر مستودعك. ملفات public_data داخل مجلد public_data نفسه، وملف الاختبار داخل tests. استبدل الملفات المتطابقة مع الاحتفاظ بالبقية؛ لا تضع ZIP نفسه داخل public_data.

ثم شغّل Publication Integrity وأعد تحميل البرنامج. هذه الحزمة تحتوي على البيانات المثرية وإعادة بناء الطبقات التابعة؛ لا يلزم تشغيل Autonomous لإظهارها الآن. الجلب المستقبلي يستخدم collectors المصححة عند تشغيل المسار الاقتصادي، مع ضرورة نشر النتائج.

التعديل على app.py ضروري هنا لأن الفحص أثبت مشكلة مستقلة في العرض؛ اقتصر على اختيار أحدث observation وعرض تفاصيل البطاقة واستيراد المساعدين، دون تعديل Fed أو قرارات النماذج.

NFP: قراءة September الحالية 29000؛ قيمة August المعروفة في الإصدار السابق 162000 بقيت في التاريخ، بينما قيمة August المعدلة في الإصدار الحالي 133000 هي السابق من المصدر. هذه قيمتان من vintages مختلفين.

## المصادر والحدود

CPI/Core CPI السنويان مشتقان من CUUR0000SA0 / CUUR0000SA0L1E غير المعدلتين موسميًا؛ PPI/Core PPI من WPUFD4 / WPUFD49104 غير المعدلتين موسميًا، بنفس تعريف core less foods and energy. لا نخلط ذلك مع core less foods, energy and trade services. تم جلب هذه السلاسل الأربع مباشرة من BLS API بنجاح HTTP 200 وحساب نفس الشهر قبل 12 شهرًا؛ عند اختلاف الفترة أو غياب baseline تبقى القراءة غير متحققة.

PCE السنويان مستخرجان مباشرة من نص إصدار BEA المنشور الذي جُلب HTTP 200. السابق مستخرج من جدول monthly release الرسمي. الأجور السنوية من سلسلة hourly earnings الرسمية SA، وRetail Sales سنوي اسمي SA من API Census الذي اجتاز الجلب الرسمي السابق. القيم الشهرية وبياناتها الرسمية والسياق الإصدار من دليل تشغيلك الرسمي المرفوع؛ لم ندّع تشغيل audit جديد لجميع المصادر محليًا.

GDP في هذه البيانات نمو ربع سنوي بمعدل سنوي؛ لا نعرضه كـ YoY. ISM مستوى diffusion index، وNFP تغير عدد الوظائف؛ لا نخترع معدلًا سنويًا لتلك المؤشرات. غياب YoY يظل صريحًا عند تعذر توثيقه. لا API key جديد ولا اشتراك مدفوع. BLS/Census/FRED secrets الحالية باقية حسب المسار المعتمد.

## التحقق

- `python -m pytest -q tests`: **336 passed, 20 warnings in 22.17s**؛ pandas FutureWarnings فقط. أخطاء التعديل الأولية أُصلحت قبل هذه النتيجة.
- `python enrich_indicator_detail_e2e.py`: **PASS**. 605 صفوف أصلية محفوظة؛ أضيفت 8 نسخ إثراء فأصبح canonical وSurprise 613 صفًا. إعادة الدمج added=0؛ PIT محفوظ. وصل السابق وMoM وYoY إلى Surprise وأعيد بناء Regime/Macro/Research/Decision.
- Publication Integrity بعد إعادة البناء باستخدام مولد manifest المعتمد: **101 MATCH, Mismatch=0, Missing=0, Error=0**.
- manifest الخاص بهذه الحزمة مبني على نسخة GitHub التي تحققت أنها مطابقة تمامًا لنسخة الحزمة السابقة 101 ملف. إذا نُشرت تحديثات أخرى إلى public_data قبل تركيب هذه الحزمة، أعد توليد manifest على النسخة الكاملة ثم تحقق منه، بدل استعمال manifest لا يناسب بقية الملفات.
- لا commit/push/merge أو تداول؛ لم أعدّل workflow في هذه الحزمة.

## تفاصيل القراءات

| Indicator | Current | Previous / prior observation | MoM | YoY |
|---|---:|---:|---:|---:|
| NFP | 29000.0 | 133000.0 | — | — |
| UNEMPLOYMENT_RATE | 4.2 | 4.1 | — | — |
| AVERAGE_HOURLY_EARNINGS | 0.1 | 0.3 | 0.1 | 3.0 |
| CPI | 0.4 | 0.1 | 0.4 | 3.4 |
| CORE_CPI | 0.3 | 0.2 | 0.3 | 2.4 |
| PPI_FINAL_DEMAND | 0.4 | 0.1 | 0.4 | 5.4 |
| CORE_PPI | 0.2 | 0.3 | 0.2 | 4.6 |
| PCE_PRICE_INDEX | 0.3 | 0.1 | 0.3 | 3.4 |
| CORE_PCE | 0.2 | 0.1 | 0.2 | 3.0 |
| RETAIL_SALES | 1.1 | -0.5 | 1.1 | 5.4 |

## قائمة محتويات ZIP

- app.py
- economic_indicator_details_v1.py
- economic_official_sources_v1.py
- economic_official_ingestion_v1.py
- economic_pce_historical_backfill_v2.py
- economic_surprise_engine_v1.1.py
- tests/test_economic_indicator_details.py
- public_data/earnings_quality_summary_v3.json
- public_data/economic_historical_events_v1.csv
- public_data/economic_historical_quality_v1.csv
- public_data/economic_regime_summary_v1.csv
- public_data/economic_surprise_engine_v1.csv
- public_data/economic_surprise_summary_v1.csv
- public_data/event_news_research_v2.csv
- public_data/final_remaining_layers_hardening_v1.json
- public_data/manifest.json
- public_data/research_context_summary_v1.csv
- public_data/research_evidence_contract_v1.csv
- public_data/research_evidence_quality_summary_v1.json
- public_data/research_evidence_quality_v1.csv
- public_data/system_health_layers_v1.json
- public_data/system_health_summary_v1.json
- public_data/unified_state_vector_summary_v1.json
- public_data/unified_state_vector_v1.csv
- US500-Economic-Indicator-Details-Notes.md
