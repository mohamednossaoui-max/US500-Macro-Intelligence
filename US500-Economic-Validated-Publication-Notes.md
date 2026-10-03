# US500 — الحزمة الاقتصادية المتحققة

هذه الحزمة مبنية على التشغيل الفعلي المرفوع economic-official-validated.zip بتاريخ 2026-10-03T18:40:23.877968+00:00. لا تدعي أن واجهة البرنامج المنشورة قد تم تحديثها بعد.

## التثبيت

1. فك ZIP. ارفع محتويات مجلد public_data داخل مجلد public_data الموجود في المستودع؛ استبدل الملفات المتطابقة، بما فيها manifest.json، مع إبقاء باقي الملفات.
2. استبدل economic_official_ingestion_v1.py في جذر المشروع، وأضف tests/test_economic_post_merge_status.py داخل tests. هذان الملفان يصححان وصف حالة الدمج فقط؛ لا يغيران القيم الاقتصادية أو منطق النماذج.
3. تأكد من نجاح Publication Integrity. بعد نشر تغييرات البيانات في مستودعك، أعد تحميل صفحة البرنامج. لم أنفذ commit أو push أو تداول.

manifest.json أُنشئ بواسطة scripts/rebuild_publication_manifest.py بعد تركيب البيانات على نسخة النشر الحالية من GitHub (100 ملف متحقق). بعد إضافة economic_ingestion_status_v1.json أصبح العدد 101. هذه الحزمة مناسبة لنسخة النشر التي تم فحصها؛ إذا حدث تحديث آخر لأي ملف public_data قبل تركيبها، أعد إنشاء manifest بالأداة المعتمدة على النسخة الكاملة ثم تحقق منه، ولا تنسخ manifest قديمًا.

## النتائج

- ملفات المرفق: 31؛ canonical وSurprise: 605 صفوف لكل منهما.
- المؤشرات: 14/14 VERIFIED ومطابقة فعلية بين official وcanonical وSurprise.
- Regime وMacro وResearch: سياق 2026-10-03 وقيم درجات مطابقة.
- PIT: NFP August القديم 162000 محفوظ ومتاح قبل المراجعة؛ 133000 معلوم من 2026-10-03، وإصدار September الجديد 29000 بتاريخ 2026-10-02. لم يُمسح التاريخ.
- إعادة دمج الصفوف الرسمية نفسها: added=0؛ لا event IDs مكررة.
- إصلاح وصف الحالة: الحقول canonical_* تعرض ما بعد الدمج؛ before_merge_* تحفظ المقارنة السابقة، وingestion_status/ingestion_reason تحفظ نتيجة الجلب الأولى. ملف المرفق الأصلي بقي كما هو.

### الأوامر الفعلية

`python -m pytest -q tests` في نسخة المشروع المصححة: **326 passed, 19 warnings in 22.20s**. التحذيرات الحالية من pandas FutureWarning، وليست فشل اختبار.

`python validate_received_bundle.py`: تنزيل نسخة النشر الحالية والتحقق من hashes، مطابقة المؤشرات، حفظ التاريخ، idempotency، واتساق Regime/Macro/Research: **PASS**.

`python scripts/rebuild_publication_manifest.py --public-data /workspace/scratch/0c2ce463fb87/received-publication-validated --source official-economic-validated-refresh`

`python scripts/verify_publication_integrity.py --public-data /workspace/scratch/0c2ce463fb87/received-publication-validated`: **Match=101, Mismatch=0, Missing=0, Error=0**.

### الحدود

التحقق هنا من دليل التشغيل الرسمي المرفوع والبيانات الناتجة؛ لم أستخدم مفاتيحك لتشغيل جلب جديد محليًا. بيانات BLS مباشرة من BLS، مع إثبات release/vintage عبر FRED/ALFRED عند تعذر metadata المباشرة. release_time لبعض صفوف BLS بقي METADATA_UNVERIFIED؛ لم يُخترع وقت. هذه الحزمة لا تعالج أي نقص مستقل في Breadth/Cross Asset أو consensus. Research-only يبقى كما هو. لا تغيير في app.py أو workflows في هذه الحزمة. لا اشتراك جديد أو secret جديد.

## المؤشرات

| Indicator | Agency | Reference period | Official release | Before value | After value | State |
|---|---|---|---|---:|---:|---|
| NFP | BLS | September 2026 | 2026-10-02 | 162000.0 | 29000.0 | CURRENT |
| UNEMPLOYMENT_RATE | BLS | September 2026 | 2026-10-02 | 4.1 | 4.2 | CURRENT |
| AVERAGE_HOURLY_EARNINGS | BLS | September 2026 | 2026-10-02 | 0.3 | 0.1 | CURRENT |
| CPI | BLS | August 2026 | 2026-09-11 | 0.4 | 0.4 | CURRENT |
| CORE_CPI | BLS | August 2026 | 2026-09-11 | 0.3 | 0.3 | CURRENT |
| PPI_FINAL_DEMAND | BLS | August 2026 | 2026-09-10 | 0.4 | 0.4 | CURRENT |
| CORE_PPI | BLS | August 2026 | 2026-09-10 | 0.3 | 0.2 | CURRENT |
| GDP | BEA | Q2 2026 | 2026-09-30 | 1.5 | 2.2 | CURRENT |
| PCE_PRICE_INDEX | BEA | August 2026 | 2026-09-30 | 0.2 | 0.3 | CURRENT |
| CORE_PCE | BEA | August 2026 | 2026-09-30 | 0.2 | 0.2 | CURRENT |
| RETAIL_SALES | Census | August 2026 | 2026-09-28 | 1.2 | 1.1 | CURRENT |
| INITIAL_JOBLESS_CLAIMS | DOL | Week ending September 26, 2026 | 2026-10-01 | 196000.0 | 197000.0 | CURRENT |
| ISM_MANUFACTURING_PMI | ISM | September 2026 | 2026-10-01 | 54.6 | 54.5 | CURRENT |
| ISM_SERVICES_PMI | ISM | August 2026 | 2026-09-03 | 55.4 | 55.4 | CURRENT |

## محتويات ZIP

- public_data/decision_engine_research_summary_v1.csv
- public_data/decision_engine_research_v1.csv
- public_data/decision_engine_research_v1.json
- public_data/decision_intelligence_summary_v2.csv
- public_data/decision_intelligence_v2.json
- public_data/earnings_quality_summary_v3.json
- public_data/economic_historical_events_v1.csv
- public_data/economic_historical_quality_v1.csv
- public_data/economic_ingestion_status_v1.json
- public_data/economic_regime_events_v1.csv
- public_data/economic_regime_summary_v1.csv
- public_data/economic_surprise_engine_v1.csv
- public_data/economic_surprise_summary_v1.csv
- public_data/event_news_research_v2.csv
- public_data/final_remaining_layers_hardening_v1.json
- public_data/historical_analog_candidates_v1.csv
- public_data/historical_analog_summary_v1.json
- public_data/historical_analog_top_v1.csv
- public_data/historical_market_reaction_summary_v1.json
- public_data/historical_market_reaction_v1.csv
- public_data/macro_context_v1.csv
- public_data/macro_context_v1.json
- public_data/research_context_summary_v1.csv
- public_data/research_context_v1.csv
- public_data/research_evidence_contract_v1.csv
- public_data/research_evidence_quality_summary_v1.json
- public_data/research_evidence_quality_v1.csv
- public_data/system_health_layers_v1.json
- public_data/system_health_summary_v1.json
- public_data/unified_state_vector_summary_v1.json
- public_data/unified_state_vector_v1.csv
- public_data/manifest.json
- economic_official_ingestion_v1.py
- tests/test_economic_post_merge_status.py
- US500-Economic-Validated-Publication-Notes.md
