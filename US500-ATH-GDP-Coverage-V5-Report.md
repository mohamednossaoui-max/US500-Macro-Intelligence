# US500 — GDP period semantics and research coverage V5

## النتيجة

بعد فحص الملف الثاني وإعادة التحقق من الاستجابات الرسمية المحفوظة: **360 قراءة موثقة، صفر SOURCE_ERROR، صفر STALE، و30 UNAVAILABLE_ARCHIVE**. هذه مراجعة offline لمحتوى API الذي جلبه workflow عند المستخدم، وليست اتصالًا جديدًا أو دليلًا على حداثة كل إصدار وكالة بالدقيقة.

لا حاجة لإعادة الجلب الآن لحل المشكلة الثلاثية؛ الملف الثاني احتوى جميع الاستجابات اللازمة. الحزمة إضافية فوق V4 وتضم 41 receipt جديدة فقط، مع الحفاظ على الـ319 الموجودة والتاريخ السابق.

## السبب الجذري المثبت

بوابة GDP كانت تقيس عمر القراءة من اليوم الأول للربع، رغم أن الفترة تغطي الربع كله وأن نشر GDP يأتي بعد نهايته. هذا سبب رفضًا خاطئًا دون إخفاق endpoint. الإصلاح يحسب عمر **الفترة المرجعية** من نهايتها؛ لا يستخدمها release_date. حد العمر 200 يوم لم يتغير، وفحص realtime/as-of لم يتغير. الربع المستقبلي/غير المكتمل والتاريخ الربعي غير الصحيح أو القيمة القديمة حقًا ما زال يرفض.

| as-of | reference period | actual | نهاية الربع | عمر الفترة الصحيح |
|---|---|---:|---|---:|
| 2022-01-18 | Q3 2021 | 2.3% | 2021-09-30 | 110 يوم |
| 2024-07-24 | Q1 2024 | 1.4% | 2024-03-31 | 115 يوم |
| 2025-11-17 | Q2 2025 | 3.8% | 2025-06-30 | 140 يوم |

BEA يؤكد أن Q4 2021 advance صدر 2022-01-27، وQ2 2024 advance صدر 2024-07-25. وQ3 2025 initial صدر 2025-12-23 بعد تأجيل بسبب الإغلاق الحكومي؛ فلا يجوز استخدام هذه الإصدارات المستقبلية عند تواريخ القرار أعلاه.

مصادر رسمية:
- https://www.bea.gov/news/2022/gross-domestic-product-fourth-quarter-and-year-2021-advance-estimate
- https://www.bea.gov/news/2024/gross-domestic-product-second-quarter-2024-advance-estimate
- https://www.bea.gov/news/2025/gross-domestic-product-3rd-quarter-2025-initial-estimate-and-corporate-profits

حقول reference_period_end وage_since_reference_period_end_days تضاف صراحة. release_date وrelease_time يبقيان فارغين عند غياب إثباتهما. حالة ASOF_VERIFIED تعني تحقق vintage المزود، ولا تعني Economic CURRENT أو release parity مع الوكالة.

## لماذا عاد workflow exit 1؟ وكيف أصلح تفسيره؟

الوضع السابق يشترط نجاح كل تاريخ مطلوب، حتى تلك التي تسبق بدء الأرشيف. لذلك 30 تاريخًا غير متاح بطبيعة المصدر يكفي لإظهار FAILURE إلى الأبد.

أضفت سياسة **available-archive** للـworkflow البحثي فقط:
- تقبل القراءات الموثقة، والفجوات التي ثبت أن as_of_date يسبق first_provider_vintage المحدد ديناميكيًا.
- تفشل عند SOURCE_ERROR أو STALE أو metadata غير موثقة أو فجوة غير مثبتة أو تكرارات أو غياب كل القراءات الموثقة.
- تصف النتيجة VERIFIED_AVAILABLE_ARCHIVE_PARTIAL_TOTAL، لا CURRENT ولا COMPLETE.
- الوضع الافتراضي **complete** ما زال يرجع exit 1 عند نقص أي قراءة.

هذا لا يخفف gates الخاصة بالإصدارات الرسمية الحية أو canonical/publication. حدود Archive ليست أخطاء اتصال؛ تمييزها ضروري للاختبار التاريخي الصحيح. لا تُملأ القيم غير الموجودة من vintages مستقبلية أو بقيمة حيادية.

الأمر الجديد في الـworkflow:

```bash
python ath_official_vintage_backfill_v1.py --events ath_edge_run/study/edge_v3_events.csv --output ath_edge_run/vintages --cache research_history/ath_official_vintages_v1 --coverage-policy available-archive
```

النتيجة المتحققة من replay الحالي: rows=390، verified=360، source_errors=0، unavailable_archive=30، stale=0، research_coverage_status=VERIFIED_AVAILABLE_ARCHIVE_PARTIAL_TOTAL.

## هل ثبت edge؟

لا. أعدت تشغيل V4 بالاستجابات المتحققة؛ النتيجة NO_CONFIRMED_EDGE في الآفاق الثلاثة. قيم DFF وGDP أصبحت موثقة في الأرشيف، لكنهما ليسا predictors ضمن مواصفة V4 المجمدة، فلا تدّعي هذه النتائج أنها اختبرتهما. لم أضفهما بعد رؤية النتائج لإجبار تحسن النموذج. التوظيف والبطالة والتضخم والإنتاج الصناعي لم تتفوق بهذه المواصفة على خط الأساس.

| الأفق | خطأ الاقتصادي | خطأ الأسعار | خطأ الاحتمالات التاريخية |
|---|---:|---:|---:|
| شهر | 0.6985 | 0.5908 | 0.5276 |
| ثلاثة أشهر | 0.6825 | 0.5793 | 0.5124 |
| حتى الاستعادة | 0.8009 | 0.6762 | 0.6181 |

Brier أصغر أفضل؛ هذه ليست نسب دقة أو نتائج تداول. الدراسة تبدأ بعد هبوط إغلاق 3%، وليست توقعًا عند ATH. ^GSPC ليس ES أو أسعار US500 الخاصة بالوسيط. سنوات الدراسة فُحصت سابقًا، فهذه دراسة استكشافية وليست اختبارًا تأكيديًا مستقلًا. لا احتمال حي ولا ادعاء معايرة.

## التحقق

- `python -m pytest tests/test_ath_official_vintage_backfill_v1.py tests/test_ath_macro_edge_research_v4.py -q`: **22 passed**، 1.11 ثانية.
- `python -m pytest -q`: **454 passed، 6 warnings** موجودة من pandas، 37.42 ثانية.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py -q`: نتائج ناجحة مرفقة بالسجل.
- `python scripts/verify_publication_integrity.py`: **106 Match، 0 Mismatch، 0 Missing، 0 Error**.
- أُعيد الملفان اللذان تولدهما اختبارات المشروع إلى بايتات النسخة المعتمدة؛ manifest لم يتغير.
- replay من receipts الحقيقية: 360 موثقة، 30 خارج الأرشيف؛ لا endpoint بديل أو بيانات وهمية. metadata وحدود الأرشيف مأخوذة من artifact المستخدم وتسمية الوضع صريحة.
- بقيت canonical/public_data وapp.py وAutonomous/Master كما هي في هذا الإصلاح. لا commit/push/merge/PR، ولا تداول.

## التركيب

فك ملفات ZIP فوق V4 داخل جذر المشروع. لا تحذف ملفات receipts السابقة. النتائج الحالية تكفي للمراجعة ولا تحتاج إرسال artifact ثالث لحل GDP. تشغيل workflow مستقبلًا يستخدم cache المتحقق ويصنف أي أخطاء جديدة صراحة. لا Secret جديد؛ FRED_API_KEY الموجود يكفي للجلب المستقبلي.

## ملفات الحزمة

- `.github/workflows/ath-official-vintage-backfill.yml`
- `ath_macro_edge_research_v4.py`
- `ath_official_vintage_backfill_v1.py`
- `research_history/ath_macro_edge_v4/evidence/full-tests.log`
- `research_history/ath_macro_edge_v4/evidence/integrity.log`
- `research_history/ath_macro_edge_v4/evidence/pit.log`
- `research_history/ath_macro_edge_v4/evidence/verification.json`
- `research_history/ath_macro_edge_v4/macro_edge_v4_audit.json`
- `research_history/ath_macro_edge_v4/macro_edge_v4_events.csv`
- `research_history/ath_macro_edge_v4/macro_edge_v4_predictions.json`
- `research_history/ath_official_vintages_v1/network_acquisition_audit_2026_10_04.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2022-01-18-1910263fb7ed2ba70eb8170b88edf589d6cd9b8442e1ada7b8d36acd033f1e12.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2024-07-24-c8aed75febbbf821d327ebd9368223e123ff5ae07e73b1a895f4c1a2e462e94e.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2025-11-17-947a27a52302d03a76e3952f13799a4addcb14f6230c23228c42510385767ed1.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2007-06-07-b946b3de26f717548c86592e7b8e91fad762912665c0f50fb314a06eae29c59f.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2007-07-26-8094d23956dcc2699535194c26874d7192e2b987ac39118035e4b063af154cde.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2007-10-19-29256c3794635d67d73641e80a6e76173bef07c077a88089b9003e98ae6cf669.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2013-04-18-927491f6c66aeab86107f6784460c66771faa740c7422e3445e26d6bcf2336a0.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2013-06-05-771ee0460bce972d523e39f652c90697dd136cc567dadca4a2ff7e948a202d94.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2013-08-16-f395c0ac2531fcf8c4c2aee485098266d7f785e5c8ad468d16f7a0e8d1b0242f.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2013-10-08-368eb2efa2d3a386cc91b87dbb08d33c0d7addd7023f3611e12c0f1799e736f6.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2014-01-24-2a7116d7bf83fbbfb6cf2f991c6e0aeeaae31787e2f1d3173da6ccd92cda85ef.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2014-04-10-98c7b2908c6a170df64853358ab0a2a734693917c46a8bf0962703fb71d0c374.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2014-08-01-15c82a9fb61732bdaac940bcf1eda3e701a4a12f598c4d3205614ee8f7746624.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2014-10-01-be124558f8ded0caad65593db96bc9d1c5fc39d65125cf2ac91d9450fc40f6c4.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2014-12-12-47cb1429ec11b08852fe95ec0a00e61a3b721523d33e7b8f4712a0d8b7ed2fcc.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2015-01-05-d056bd1d1a90d85cd117c2376e3bade64cd54de5e2ea80c8daf0a45e2db3b862.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2015-03-10-5db981ba6034e0f707681d74769824b4a347bc1a94bd807ee47d1a887ac9c73f.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2015-06-29-aff0adc096e7fc17c5e57a51730abc8d8961ff78a062026d81784cd3726a7806.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2016-11-01-7ae327f320a5759f30e7a2d4138c30b9eb7afb4d32b1734158e68cd954c162ca.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2018-02-02-dcb25fedc6e50d08b2bf10b5e94fb64a11a5fdee677b485712edd21dd254fc7e.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2018-10-10-8d51ba8aec71f2ef9389f666315deb1ebe39c74532622168e2745de1d33fac45.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2019-05-13-c2ac510e648aab586e10e976e5e7bc4dea8970da02b439bb0f7ad25ea6fbda2f.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2019-08-02-f9334a5b15d73f5593605b0dee573794707486f19ad79b31858abf25d601f763.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2020-01-31-6127a43275e439c5b356a93c6130a840a6a0e98811e874af2c3c9061c9a3a571.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2020-02-24-71ad4529ec3d0fc8c3976a1f35720eb6eab13ea60ea637b684e1254147a41253.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2020-09-03-0a91d56ae1be25eeb255fbf9fb1f1fd82f10673ba1a4f9b76efb48568f0fa004.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2021-01-29-17a86c0a1408df4f4442f8b8a85b6fac536d99b3338b9025925e9b7aea935811.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2021-02-26-6cd743cdd1947e2d9943753531290a9236d4a095a413ac64dd709eb0669f89ff.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2021-05-12-322760ff1f653bcbf67d6ffb8d5ea48dddcf33b9fc00586582e46ccdb116293c.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2021-09-20-43b71d6e487cee368de78fc5ac748fc1641895bb68f65e48af21595df8ea5a4c.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2021-12-01-4ded318321a705503f60085483f9580077e14c6b66341c650c07e90de06c455f.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2021-12-20-ab184610ca4e2a51bd56357428e0bfe2b4dcfddd7b063a6af02b4f4e30a99c8c.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2022-01-18-220ad98184705c7a3abbfc175cfa4a213a58081f415d08472719ea1513893723.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2024-04-15-5a8cc5d61143e046c3a3089993c14ee558f4c7db2e85adbb0549cf3c3000652e.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2024-07-24-4fcd158aae5b5bb1466ebe1288e0cac27a11662061e7b0b8913f55e192273cd9.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2024-12-18-5be81c56f2aa3a60c73b0169446b35e9d3713a7033a8de57a30f996a4c019ef2.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2025-02-25-1afc9fc540c7439607f593815ae12835c2ba7c9b00f78ada2105b29844f52d06.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2025-11-17-b449b296c32d1d8fb329e68ef307f06fb5f7940017d44e084790eb2bf0ca0a7d.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2026-03-06-85f4806bf38ae81e6d9451075eecd4df8c5343c822399b240422a79de8735f91.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2026-06-10-d731cc28bfefa03bca82a6b546d913950e0f71f88b0c87aae1b1c0a04b475a9a.json`
- `research_history/ath_official_vintages_v1/receipts/DFF-2026-09-16-859f4b9accaefda373dfb99ff32c796b821c2decdfa2e70dafde993ea37ae411.json`
- `research_history/ath_official_vintages_v1/revalidated_acquisition_audit_v5.json`
- `tests/test_ath_official_vintage_backfill_v1.py`
