# US500 — إصلاح جلب vintages واختبار السياق الاقتصادي V4

## ماذا وجد الفحص؟

الملف المرفوع يحتوي 390 طلبًا، 319 قراءة ناجحة و71 حالة مرفوضة. جميع receipts الناجحة اجتازت مطابقة SHA-256 لهوية الملف، السلسلة، وحدات القياس، التواتر وvintage المطلوب. بصمة مصدر أسعار الدراسة تطابق نسخة المشروع المحلية. هذه سلامة وتناسق artifact؛ ليست توقيعًا رقميًا مستقلًا من المزود ولا إثباتًا لتاريخ نشر الوكالة بالدقيقة.

| السبب | العدد | النتيجة |
|---|---:|---|
| DFF محدد خطأ بـDaily بدل Daily, 7-Day | 39 | خطأ في النسخة السابقة؛ أصلح الكود والاختبار. القيم لم تُجلب مجددًا محليًا لغياب مفتاح GitHub Secret. |
| HTTP 400 في تواريخ قبل تغطية archive | 29 | تواريخها متوافقة مع تاريخ بدء metadata في ALFRED، وليست 29 عطل اتصال عشوائيًا. الكود الجديد يستعلم أول vintage ديناميكيًا ويصنف UNAVAILABLE_ARCHIVE. |
| GDP رفضه فحص عمر الفترة المرجعية | 3 | لا يوجد payload لهذه الحالات في ZIP لأن الجامع القديم لم يحفظه. لا يمكن إثبات أن آخر إصدار وكالة كان قديمًا؛ بوابة العمر وحدها لا تثبت ذلك. الكود الجديد يحفظ الاستجابة المرفوضة للتشخيص، ولا يستخدمها كميزة. |

تفصيل HTTP 400: GDP=11، فارق العوائد T10Y3M=9، NFCI=4، ANFCI=4، Core PCE=1.

المصادر الرسمية التي توضح السبب:
- DFF: https://fred.stlouisfed.org/series/DFF — Daily, 7-Day.
- GDP metadata تبدأ 2014-09-26: https://alfred.stlouisfed.org/series?seid=A191RL1Q225SBEA
- T10Y3M تبدأ 2014-01-27: https://alfred.stlouisfed.org/series?seid=T10Y3M
- NFCI وANFCI تبدأ 2011-05-25: https://alfred.stlouisfed.org/series?seid=NFCI ، https://alfred.stlouisfed.org/series?seid=ANFCI
- PCEPILFE تبدأ 2000-08-01: https://alfred.stlouisfed.org/series?seid=PCEPILFE
- الاستعلام الديناميكي: https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html
هذه التواريخ شرح للدليل وليست تواريخ ثابتة داخل منطق الجلب.

## الإصلاحات المنفذة

- التصحيح الدقيق لتواتر DFF مع إبقاء unit وseasonal-adjustment validation.
- جلب أول vintage من المصدر قبل طلب فترة قديمة؛ لا تُستبدل الفترة غير المتاحة بأول فترة مستقبلية.
- التمييز بين SOURCE_ERROR وUNAVAILABLE_ARCHIVE وSTALE. هذا الأخير تصنيف البوابة الإضافية لعمر الفترة، وليس إثبات release parity مع الوكالة.
- حفظ receipts قبل فحص العمر حتى لا تضيع الاستجابة اللازمة للتشخيص. رفض الميزة يبقى قائمًا.
- cache صريح يحتوي القراءات الـ319 المرفوعة، مع فحص البصمات والهوية والسلسلة وas-of عند إعادة الاستخدام. لا إعادة طلب لهذه القراءات الناجحة، ولا دمج لتواريخ مختلفة، ولا اختيار صامت بين receipts متعارضة.
- إعادة تشغيل الدراسة الاقتصادية في workflow حتى عند نقص التغطية، على الحالات الصالحة فقط. نتيجة جمع ناقصة تظل exit 1، وترفع artifacts كاملة؛ لم تُعطل بوابة الجلب لتلوين workflow بالأخضر.
- واجهة ATH تعرض الدراسة الاقتصادية كبحث غير معتمد. لم يتغير app.py أو public_data أو Autonomous/Master في هذه الحزمة.

## نتيجة اختبار edge من البيانات الفعلية

اخترت مجموعة واحدة محدودة قبل تشغيل V4: أسعار الماضي + تغير NFP الشهري بالوظائف، البطالة، YoY من مؤشر CPI المعدل موسميًا، YoY من Core PCE المعدل موسميًا، وتغير الإنتاج الصناعي الشهري. جميع القيم من vintage اليوم السابق للقرار. لا مستويات CPI/PCE مختلفة السنوات الأساسية، ولا موقف Fed اصطناعي، ولا قيم DFF مفقودة داخل النموذج.

التدريب باستخدام ridge λ=10 والتاريخ السابق الذي اكتملت تسمياته قبل القرار، على عينة مشتركة للمقارنات. بداية السؤال بعد هبوط إغلاق 3% إلى أقل من 5% من قمة إغلاق في التاريخ المتاح؛ ليس توقع يوم ATH. تثبيت الفرضية مسجل محليًا قبل تشغيل V4، ولكنه ليس تسجيلًا مستقلًا؛ سنوات التقييم نفسها فُحصت في دراسات سابقة، فالنتيجة استكشافية.

Brier أصغر أفضل، وليس نسبة خسارة تداول أو نسبة دقة.

| الأفق | اختبارات التقييم | الانهيارات | خطأ الاقتصادي | خطأ الأسعار | خطأ سياق السوق | خطأ الاحتمالات التاريخية |
|---|---:|---:|---:|---:|---:|---:|
| 1M | 16 | 0 | 0.6985 | 0.5908 | 0.7634 | 0.5276 |
| 3M | 12 | 1 | 0.6825 | 0.5793 | 0.7249 | 0.5124 |
| UNTIL_RECOVERY | 19 | 2 | 0.8009 | 0.6762 | 0.8018 | 0.6181 |

**النتيجة: NO_CONFIRMED_EDGE في جميع الآفاق.** الاقتصادي أفضل من سياق السوق في بعض المقارنات، ولكنه أضعف من الأسعار والاحتمالات التاريخية على نفس الحالات. لا يجوز الإعلان عن احتمال مرتفع. لم أغيّر العوامل أو المعلمات بعد رؤية النتيجة لإجبار التفوق. Macro complete rows: 34 للشهر، 25 لثلاثة أشهر، 38 حتى الاستعادة؛ تشمل صفوفًا لا تصلح بعد للتقييم بسبب نضج label أو حجم التدريب.

المقارنات الاستكشافية محدودة جدًا بحالات أزمات قليلة. لا تضم أسعار ES أو US500 الخاصة بالوسيط؛ ^GSPC مؤشر نقدي. نتائج هذه الدراسة لا تنفي وجود edge في أي منهج آخر، لكنها ترفض الادعاء به لهذا النموذج وهذه العينة.

## الاختبارات

- `python -m pytest tests/test_ath_official_vintage_backfill_v1.py tests/test_ath_macro_edge_research_v4.py -q`: **17 passed**، 0.48 ثانية.
- `python -m pytest -q`: exit 0، **449 علامات اختبار ناجح** في المخرجات؛ لم تطبع هذه العملية ملخصًا نصيًا نهائيًا. السجل الأصلي مرفق دون اختراع زمن أو عدد warnings.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py -q`: **16 passed**، 0.37 ثانية.
- `python scripts/verify_publication_integrity.py`: **106 Match، 0 Mismatch، 0 Missing، 0 Error**. أعيد الملفان اللذان تعيد اختبارات المشروع توليدهما إلى بايتات النسخة المعتمدة. manifest لم يُعدل.
- تشغيل `ath_macro_edge_research_v4.py` على study وreceipts المرفوعة: نجاح فعلي، 319 receipt متحققًا.
- تكرار نفس الدراسة: ملفات audit/events/predictions مطابقة بالبايتات.
- authenticated reacquisition لـDFF وبقية حالات الفشل لم تُنفذ محليًا؛ مفتاح FRED محفوظ عندك في GitHub فقط. Fixtures تثبت منطق الإصلاح ولا تثبت تغطية الشبكة.

## ما عليك فعله

1. هذه **حزمة إضافية فوق V3**؛ فك ملفاتها داخل جذر المستودع مع المحافظة على الملفات الأخرى.
2. شغّل **ATH Official Vintage Context Backfill** من GitHub Actions بالمفتاح الموجود FRED_API_KEY.
3. سيعيد استخدام receipts السليمة ويطلب DFF وحالات أخرى غير متاحة في cache، ويصنف نقص archive بوضوح.
4. نزّل artifact وأرسله. نحتاج خصوصًا DFF الفعلي واستجابات GDP المرفوضة لفحصها. قد يبقى التشغيل أحمر عندما تكون coverage ناقصة؛ ليس ذلك إذنًا لنشر توقع حي.

لا مفتاح جديد، ولا اشتراك، ولا إرسال قيمة secret. لا يلزم Autonomous لهذه الخطوة. لم أجر commit أو push أو merge أو PR أو تداول.

## الملفات

- `ath_official_vintage_backfill_v1.py`: إصلاح المصدر وحفظ الاستجابات وcache والتحقق من الحدود.
- `ath_macro_edge_research_v4.py`: دراسة مقارنة اقتصادية فعلية، دون توقع حي.
- `ath_pullback_context_ui_v1.py`: عرض النتائج الأرشيفية وحالة عدم الاعتماد.
- الاختباران وworkflow: regression ومسار إعادة الجلب والبحث.
- `research_history/ath_official_vintages_v1`: الـ319 receipt الأصلية والـaudit الأصلي دون محو التاريخ.
- `research_history/ath_macro_edge_v4`: التشخيص والبروتوكول ونتائج الدراسة والمدخلات المستخدمة وأدلة الاختبارات.

قائمة محتويات ZIP الكاملة:

- `.github/workflows/ath-official-vintage-backfill.yml`
- `ath_macro_edge_research_v4.py`
- `ath_official_vintage_backfill_v1.py`
- `ath_pullback_context_ui_v1.py`
- `research_history/ath_macro_edge_v4/acquisition_diagnosis.json`
- `research_history/ath_macro_edge_v4/evidence/full-tests.log`
- `research_history/ath_macro_edge_v4/evidence/integrity.log`
- `research_history/ath_macro_edge_v4/evidence/pit.log`
- `research_history/ath_macro_edge_v4/evidence/verification.json`
- `research_history/ath_macro_edge_v4/input_study/edge_v3_audit.json`
- `research_history/ath_macro_edge_v4/input_study/edge_v3_events.csv`
- `research_history/ath_macro_edge_v4/input_study/edge_v3_predictions.json`
- `research_history/ath_macro_edge_v4/macro_edge_v4_audit.json`
- `research_history/ath_macro_edge_v4/macro_edge_v4_events.csv`
- `research_history/ath_macro_edge_v4/macro_edge_v4_predictions.json`
- `research_history/ath_macro_edge_v4/protocol_record.json`
- `research_history/ath_official_vintages_v1/original_acquisition_audit.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2014-10-01-e92caeecd4f40228b6e8977a30ad11fe49892a276eb3cca0f6ba2aa670a72521.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2014-12-12-f78fca4a12a5fc62be1e07c141cbfbbef9d8c28997363a0f995fca96444dfc15.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2015-01-05-b8febeddcd323837030f4dca7ce6de4b23eb05ebf61a86e198bc00bd31eb1d97.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2015-03-10-dd67a9aca7a00b65b90ef4f831646eda5cc4ea94945221b4df29f53ad047f3b7.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2015-06-29-318f2fddb4964afbb8e8cf9b87a4a27cf44f3543741c504ba03aa9398f949ac8.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2016-11-01-9971aa94efc073c617af7719aeba1fe9c71fdf5fa34cedd3042d35294a387a9f.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2018-02-02-dc6d0b5b2f2fa3d5630818f164cb52c1efaada6db705857d327cebb12c87c905.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2018-10-10-ab6f810c55177f6d02d0948e14f1cb0f17fa0c7c7ba7f7c6635ee65ac7e65122.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2019-05-13-e9febc46448c595b29cd8abccab3e282cac61ac45c8e89cae1c933ab86bbf659.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2019-08-02-8fe60ddffb3d23685d3256e2c40891a30c37d2a841592b97cc1d3e5c2ac874fb.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2020-01-31-43661c4ed90afe3cfdb37aebcc91251baa368a190cb3880b4dd6029b605a0236.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2020-02-24-112383c2fc0f628f3f900c29a27fc5e165944159948153d6f114d6b0e57fc5f9.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2020-09-03-b31e745e912c1d41b45ee1a78602dd0169fa050878a38a02c64f201d53765325.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2021-01-29-22d0fb68b3749e4677b0f0ffc8fa3eaf9d148247e777df5bc57a7f3fc8f23b78.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2021-02-26-3d510ac7584108d0ffec0e2d99b8dd68bb3193f2de4092ce568785616e169b1b.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2021-05-12-d76b8c301421d4a73d3a86bda92946b13011d545617607568be433d886bae6db.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2021-09-20-f7dbd81488ed241d6460ccbd8fdece19b7498d14fa667d512c460dd5e5677d24.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2021-12-01-a9e3cb240804e855cd9e43e1984d1098d65486e08806df63908dddcc3e675413.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2021-12-20-ce59b3a755db367306ddf7b9e3a0d8f0201b4b502381ee8331786026416f152f.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2024-04-15-e69b36d305aa81ae3ef0c7c4470b6b3f210df9170c147c12bc481d5c2f5423de.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2024-12-18-6d73300b883fd2ddf81e42f7f82b1ddb0e03cda2f903bdc903e4e2e630931ef2.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2025-02-25-27a227039cc3e0ee6a51beda2a7169b2fb455d54ffa0947cdf98f86021941c36.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2026-03-06-8d302cd85bd895b7afb82dcc07cf7139e13721481c6a1c02ce5b541f777abbd1.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2026-06-10-9241d7b1e66853324772590ab18915e3e7503f4adb2d3ed3d332f9fbda4d0034.json`
- `research_history/ath_official_vintages_v1/receipts/A191RL1Q225SBEA-2026-09-16-9e08d70a4afdd10c3e8feecd3eee52262f8e0035744fdff0d5e2e46fc915f512.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2013-04-18-7ae9ace0b14596e4f548064e39819763e5a0740d008ae3695f7bbf6f618da695.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2013-06-05-1b9d2efdc51d7715fa9d025527e47b88d0d8d0abdfefc2836de7de349bb468ce.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2013-08-16-dbf085775991008862e88e4b0cb40874940940ced1dd90cc162946c2ec988681.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2013-10-08-801f61db679bc7f0374c3ad1d16064fbd3ecab2621034e589e672d0eed415c45.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2014-01-24-2bcbcd6305a578de1e2b83c9e5aa320355ccbda81ec1a0b73403edcf0b696735.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2014-04-10-6dc7735464cbbf67c4b76264ef225d886bfbd11aa720090960c40bf7acf98c43.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2014-08-01-3459ed2c78e6ff4ff8b89fa0b8af0b53c80afef75f58663dd1279dc1c30ca051.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2014-10-01-2a89072681668f33bca8ad7068208bcbd54c716efc691c39cfa33b7888dc3102.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2014-12-12-0b0fabfee7b55f29c3444a362f12488886227c599ab1c1efd32d2d76064e1993.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2015-01-05-21d46f4f10065657d50e0006a2414cc74a75cace857775657dbb496946c9e9c6.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2015-03-10-ee2560996ed3ff6852cf584d369891229dcc27ad40e1809204153d3c29fd557a.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2015-06-29-bc3e889ba64f041f2ab764bc8386dd22979979b8667c8a3c48902c574a70a9e2.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2016-11-01-8039f5bc2fea5d0eda7c6236ed71c099d1d230d85876a5f6f811824778b991ad.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2018-02-02-68c94dfcf2f017952e85e1fcd567780ce5fde34ba73edc458123a5364fc50abd.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2018-10-10-dcc74c2de82820cf8a986ed2a33fc60bea3c95686a285e85005034e9052da844.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2019-05-13-e5c2465a3aba05b13eea77eecd0bb54dfce0496f3089e03b314430abc8d31728.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2019-08-02-c5efb14fbce2ae2bdb9910ba9073a44fb0d69bd65f0b6680c85dd4a248807e30.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2020-01-31-3f00669c52148af5781ba0952bcb7928a841049c7e90eaa35009c7de972930be.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2020-02-24-201adc6db7cf18f4c18169d14cc28313f2c7e7eb98c3f9ca0bd7b5a4502a1137.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2020-09-03-5db00f2fcd00618de2fe277bf439ac503e309b91bb3591773f9ab88ed540721c.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2021-01-29-40555f36b4a5995b06b9866d69f66ace331861d170e585008a39b593c60b0d02.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2021-02-26-16d8c1c4988ef132ea16f75266e160309dddbfc79da70377ae2dd938ea7a2781.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2021-05-12-15013ce10950dc8a6e9e70e92f9cd168a603a4f2e80e59e71cecd2c45a2f054a.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2021-09-20-fa6e88e501de6e2118f47fa30addb702d38f778668d335c48be3d140b6bc028d.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2021-12-01-58d28bbc4ae2463ffd045128831e083037556c574e603aa227c2f4ca34a3daef.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2021-12-20-636012c43d9e6aa39ace9ba654e599e3594e4bd4cc9607972148d5511a49788e.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2022-01-18-01f08a9613c80126217a22d7e54aad01a1652e0dff3e22b710710e8138bc65c6.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2024-04-15-cf161134c3cacd20ddc678145c30d3b90261dcf76c397feaa53e40b1a5e75b6f.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2024-07-24-4c9da7589f7e493ab4dd639e00b2bc1543e4d02d7922f81e65df7c317a8efdb8.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2024-12-18-657eefb925f18cf3ced2e67e0f6c4e1b2180c4ae502cdaae4d8b24602aa597ec.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2025-02-25-14d62b6ab11ff1034e8e11f21e44c3c6e70230478d13c0305ec5de740500f140.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2025-11-17-1ecf11d0841017db8d963b9db98691fd01b0042e16f9299c0ebda16b24aae339.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2026-03-06-62061557c7c005a8ec5ba88aa971d6e1249b3ab1046d42f179d4ff009af87960.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2026-06-10-c37c38e76be3706468f1c43dcd82ff0f7c2b864c11c8e4289432972273ef0879.json`
- `research_history/ath_official_vintages_v1/receipts/ANFCI-2026-09-16-24271d27add8b5659350b1f01eca1c56caa10a285bf78e8d45fbfebaedb4ef4d.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2000-04-12-d228e1d947ae3429c150ec24f0bb4c2bb577169324943152c16b5bed7bf8f824.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2007-06-07-13caa740146937e57bd1e94c194d64952369cd977d51a23e74b87ca51e046415.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2007-07-26-18c3c7b31c8f5209a29f33599fe6be35349c5ea5c6f98e2f75957db5d964edb4.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2007-10-19-c4bedbd2cd21520b800a078497a3e43b6a001e604f7e0cb50dcb1e587f0fce06.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2013-04-18-5c0b92516123f569f24cd7de5e39ff6ce8117c50e49faa9be41efd6c7288a834.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2013-06-05-72f2058d7962c859b353b460245ade47d617392784423f6125177edfe695aa70.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2013-08-16-cc9e158568685bad1e10807c9b92169bbf102bdf80ee394e754866b0ec543a1e.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2013-10-08-8ffb3f50a9b715dfc217481b963789b1e046e285114c9663082560d3b1b67d20.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2014-01-24-15c7b2fe52940b748e777d1e7e34e8ed9c9bd36bb6c9b04ce358dc87efd58840.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2014-04-10-3cb0be8fa162ce40f26d37a5aea8ec1a23d09e0bf32c9aae0535efcab7fe8993.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2014-08-01-5c0836a6e6461c9168fbccc452cf0c13fb152af19a554ff8d8cb504fc5fd4104.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2014-10-01-cb22a0f6a30dc876718e1c38ba354c0019ac5cc758b628e21b0a29567a36d1b6.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2014-12-12-98b5b7208a76b83987c31f6e75ada1103a88e05e553892cfd6ebb683d92962c7.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2015-01-05-35dbb601ea302ee89a16c0ba427e432991722db3a70a903328b19e33e8569cec.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2015-03-10-24dc8d900a5d5664c5276aa8251cc1d818385e97c14c6bac5bfb2aba5a6bc650.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2015-06-29-b85dd011d4f4d4a28983ca080c690cb6d41b5124e1b5fa42c852ddc478047ed0.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2016-11-01-5e91c90fa2754b82c2f92a502ca5671cecf2d272319c4ba64b28c0b1f67913f7.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2018-02-02-3c1e7d7ce84b19981c80b0f7e90ab5fd2befe5c5fa132823543c16bebf79d2ad.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2018-10-10-891b728ae8ddb8b61cbff514972b86ebb098dd0171bcac4a7505c7f1e97345f1.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2019-05-13-88f9a509c743dee3bec439ba7d952699f3b4640e7aaac70b4aa08cd080aec2f3.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2019-08-02-50aedfc5b48eaf0a8dde3687c8aca9a728560dad31ec8d8dbffd01dd2b972f30.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2020-01-31-d9a1f334a905b6c212f64eb362a4ce0375a76c8067731f3b3204f600a5bd2b18.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2020-02-24-dc190287de937a22a5c0472069ae3619ae5130103e5f55f5ffacdb26811104da.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2020-09-03-3e8a67109388a85f0b0607fea5c4f5006fa9722461686298d9800c9950bf14d1.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2021-01-29-24b686147fc446cb0e01040f017e96f6c81c7b24f35b6f760ea05b371ae2d266.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2021-02-26-177cbb44c09a823c2f9598bc40dd22764b8bb10ba9aec4b049e5848c0516926b.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2021-05-12-e05a95a8fb3450b324a0a5cb0ca6b4add4ca447bf8ff1f7edfae0f11e23daefd.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2021-09-20-4fd71b94920e5a196bd10cd59d6257d5db35b4c267a2490668aaa04d9800a875.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2021-12-01-50c62338df42c004c6ec77aef4b1be3c8345aca699241eab18f6ca0d5405477e.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2021-12-20-536a4355441661a96caabc22e47a4466f1adab88cf3f943bc014d041b64c9c39.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2022-01-18-28495c8048d251bead64ba91eccdade5a008b84761f1b51b33a0e0c7b4d80cb7.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2024-04-15-3eb57ed0fe5bafa9532d0b915ebad7e96dd7dce47708b6858171d0b88e45f665.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2024-07-24-8b1262f18a2145b433b2b9df8d734ce7589a20217604c9f0354a36a50c77931c.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2024-12-18-df9688ef1b2ead431fc0eeb00446b34339ca724f875042e5c6e59304382ca3a4.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2025-02-25-6ca956edb95e16f41ac2625f80b16e87e08e355855fbd0fb21561ebc8664d14a.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2025-11-17-ca7182435cd3a5d52dd15a80d33c9bb7417e91321dd3903ae7ba52e465d9527b.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2026-03-06-712b78c9e283fef8c18c4882b706443e317cc2282f9166bb7ceab88cc41bbf11.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2026-06-10-bebc437a5ea2bb681ef8c7fd1fbaebb050dfab1d75bc3427241e40d93c246992.json`
- `research_history/ath_official_vintages_v1/receipts/CPIAUCSL-2026-09-16-fceb9daa498ea94c3a0d62c4fcba81f9c34708a154ec890db35a7e94946a835f.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2000-04-12-23b1d0ad22f63d56161a508a317cec1f10a1075fd4317e19dce38ec92da18782.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2007-06-07-dfaf260c2e478a78162f0483a12d2b3b900f38e4e7737f7ea752c15575b36854.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2007-07-26-f86897cf28673b38a4c5cb86db415b797a16079e5fca07e859706143f76b6a52.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2007-10-19-8a26f5239674205c983a30242d0965ce03ca99b549c59cd90d40be02c85c7b0c.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2013-04-18-9ec0f8059e0b7464ef4208ce538280e5822e4631c85b4799ecf64319dad468a7.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2013-06-05-98e2ad1988cffa95288d6a63190468e1a4e8621efeed6807c118fe600a4b1c72.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2013-08-16-bba10b756a57d81b403072bcb4319f1df43273490863bb18dd9106213179c55e.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2013-10-08-02a9a96df971d71538ea3467a375cf114d7b475be5c7885595967617403ade02.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2014-01-24-9194d5cf0bd146accaf77237a332e3c243d2acf0b41065c9db5604be7521e0a4.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2014-04-10-258ac85a575474201a8ce5684f8f774079178ea7da3670eb032800e0c574bbb2.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2014-08-01-345e3500f4bfa9d8cae414471fb931fd4fe0f97b6dc79bd1ae26acbd760de2f8.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2014-10-01-7d062e501280ea75f74b4726fa75f46302286b3455c055fe14dbec9a719ccf20.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2014-12-12-b6b46dc157bb7d8182f053b7160c43459984179705dd74b007c50a7018581fbe.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2015-01-05-e932bb0ce3c2d0e299fa83cd9f635236353a67d4d6024708b4fc9d0401ad3ec1.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2015-03-10-e6e2da6d61a5fd5628dee6ad5dec7265d6d496cf911fd7843a5b83ca6c013c3b.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2015-06-29-7dd9445427619338332d9f4107a58bde7490f2d63c166793250c0366ba55bc4c.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2016-11-01-b33fcd84f6c78c78c0e4245bde5542a5d4e1dbafdf71eb8692c02306fe1a328b.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2018-02-02-1b0d95a9e7123b9bf4dc29fc453855327a42989ddd07daeedac345858d0edb4d.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2018-10-10-8791f7fbd57a0c2888a1931417b49c3a4314883668d60c29820451b83a7abae5.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2019-05-13-0b13cd3d7f65e112b6a28a9fc353bd202b97ea2000ebeda299469ba14af11fc8.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2019-08-02-143ba3635e4dab23a6ea8d1195d08dedc3cb0418059101a60291e598303cbe07.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2020-01-31-80538753621e5f7b17f60cfa673ea3f1ddad053c4425ef2d0ecb568d9b1a7932.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2020-02-24-d849193a59fedfed125885aefae9cc675cc6a3f5fdcb8cafbedf874a121750c7.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2020-09-03-7edb8d6b60d3bcf998a56857457eae97b9339285a8386ca37f672b4ac5b6e7f4.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2021-01-29-bdbb5c8da2279c7e88295123120f0c159e8971187dacf479a0c96b0828d71adc.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2021-02-26-1504573f519ce91228128c7afa2880843bf8960dca8b03ea9af8f413ace70c52.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2021-05-12-5f91f71e523cd9ced04f8d8b01c107eb041487ee92c73bae1fe382a40c557582.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2021-09-20-1f22843ee014f715405f3a52dbca1fc6789c38a97e0f9fb3218b17f22e6f2959.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2021-12-01-d1e9877d2d75744ad63cfe34bdea3cc70a0ac1f116278e3e3d537f7ae72f867b.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2021-12-20-18ebcee0f794e3038df9bda75ae20771767444e2fba2dcd31c4f715fd7733bfd.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2022-01-18-e6045b060f9d3479929918d7a28e11a7b51159fe894441a1e05292fadc552fe8.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2024-04-15-a8f0460c37e35e8ac9f19dfe659c96b76caa4cc6639b5fce4d021c613d611921.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2024-07-24-905adbee4150d38a98204ae9478092f6e7ce1a91fd264f2bf7b12bdf2e29a3c2.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2024-12-18-d8c74c3b482cb02ce655b7c24814efaad3488fe73ff31edcb94865421052e14b.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2025-02-25-2a4f8aa87b90305e4cf06809cb1ac89ad895191b1b13ddc882815968513a566e.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2025-11-17-8c75a65d8424b9f789ec535e54bb70c2eec8ed1aaaf18c73445b06053724b087.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2026-03-06-b6e10a70edf1aeec8d8fdf046221c7ab64df2201b01b49f229ecc414642b2e32.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2026-06-10-a3483279b970b8de476482dd9b99a011430e02b0e6fa3a625139829fbd99096e.json`
- `research_history/ath_official_vintages_v1/receipts/INDPRO-2026-09-16-5a3a6f443d4a3a51bb4e282fb3747f307324e358982c7e1d3ebd794adedbaffe.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2013-04-18-16d811cfb16d043c9f8a3f203c6eb0d9a7b2e915ca5f04c6df439197ac5c23dd.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2013-06-05-73a1d0df52d69b3851d12955615ccbd4f617a0a5414091f15792004ac46c56c7.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2013-08-16-11863120b2c55c776fd6c2adb75677421b85e1984e3c756dd4dbc661a58a2e2a.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2013-10-08-3847a0b4b1e33bc234277bd8550492083e7fc84e6ed257d474e1d925df94ad37.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2014-01-24-f8677036e51b152010df1eaa4f75fa15625ffceb8c068694206a3cf068af7144.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2014-04-10-8f78a65ccb2e8fc4013db52f3ed556bd31cbe6ed58e15eeb80977ec45a031ef9.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2014-08-01-c53dee48f4187091287830ab94f72aaa1ecf556a112c69988aff7355c6ffa5f0.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2014-10-01-33d83beeeddddbc3a4da455176f3154812271f395b566138a8c979db43ca406a.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2014-12-12-a38476155ab9f5cab79d3148480369eba5b991f79238338b7e6cea90b9589506.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2015-01-05-7daad2e4d1f944b2058ed881d7be36417efbd75e5d4323a702989df0b2338797.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2015-03-10-2233978a6847addb20b63d4218c4c57370262ca3e01b35e871335799e5d93f4e.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2015-06-29-e66d4d5334006bfc8f88b66293bbfcfeb672ec2d875ccb95e06700fc0b737d78.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2016-11-01-9b3263de3f1f96b603361ee8538513a5a2929d4a54800a3fab01a53641c14214.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2018-02-02-2c0bcc8ce85c5fd69866e04f1b81f89a8b8ac4de009f943e0fb093afe36a54cd.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2018-10-10-e3431d8b46e7dc0587161d08bde67e27c4fcb29cce4c0aa46d78769431c218cb.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2019-05-13-df0139f4bf4d46cb4cc2c899f1da0bd93b8f2767a765927bbf14997635153f52.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2019-08-02-338efa008c8d731ced97daea72f04e0dd1f84ebd16d84504f80a5fa9df46a4af.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2020-01-31-16566f539fd0b5d160e6992947c9fa73a3c9facd6cd45a2bd14fcc1bc49f4b54.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2020-02-24-228225fa812820eea0346e4c396f7185837425548896a40cf42cb5009f9b2346.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2020-09-03-affa6c8175e79a7c42e72b2ffe063ddcc9282e0bddca44a7d688a32da737e346.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2021-01-29-65d21eb6b8a0c67fc4b440f687bc60ff3ddedb514e528b5764976006f515b32c.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2021-02-26-d6c29b834247f9addc6b4b4335893ea719c540cbeac0d3d0b15c7e09de0a10ea.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2021-05-12-7e637bf0275342929bc4b8a18a61939ef3c4b3a5aa406065c5422e9901dd8b42.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2021-09-20-26c998ddd57e495f66ef0c9d9ea6d562861b143198d524498ef12637fdd202bf.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2021-12-01-c5a04539e28c36edc735e652002cf69079793f59d15ddd25f0f6cb4821ecfc5c.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2021-12-20-3fa9a6cc504c4a2f1c66f65d5662e7008c8f1324bd09e9fd2a4e691dd3f9f154.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2022-01-18-cc6c39474b9a737c0695a25b128229824076957683942ac4b006e4bc96732cb7.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2024-04-15-20ef240239d68608dc17b38a336ba14994d1a84503da65915bc438fe783e5d44.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2024-07-24-39d89caf1f56e041f8ebafc5172cd37eb5f92692294c5d83112b21c150ff33f8.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2024-12-18-b16e254a9f5636d883342148ca36296abd1e1b297ccd5b65f9840315764efbab.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2025-02-25-86bd2240cb92e173c7e4528cc885eff8c48732fe3a5101519fb6b719e6d10368.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2025-11-17-4522abb7ca9d68f40e29f13049721895bc5c0d9ae53aa36f451279d215706937.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2026-03-06-1ad148ea3364e113337b2fafbf5b3ab7b208fca602006511a4642f7fed46da44.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2026-06-10-2c493e24c88cd9aa467bafcbf5a731a1aff9945574b0417ce0b90394baf726ba.json`
- `research_history/ath_official_vintages_v1/receipts/NFCI-2026-09-16-e76967d712de206ca110f56051e7c55de061f56bff291c88574c9078890d4b19.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2000-04-12-bc38aeed0e75257fc9704f25a5085c397cba1b11553f9abdd8dc25a6bf6ffd8f.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2007-06-07-d4234a9deabb7b7e04a1fb54cd0bb9cbc7b74fb8c4cb29f812bb512530c8bc91.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2007-07-26-612e88ee39c40a2e80d7bfb29df3011f030ea37b203675fb9faecd8bca4235f7.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2007-10-19-d22db44e2c42264ee8b5ec724b5d392654361ca5f5371c6baae0ef678786dbd0.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2013-04-18-f1fc26599eac81d4747355c9a5992a559d828686d728f63bdaa46f021466db3c.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2013-06-05-16738bef08e4a36f85aa6de09c31928ca6a4c02fce9775c10e89bb0c22477be8.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2013-08-16-a07ad7ea569083421c7a34b96497fc36b0f0798fc2b4ee91022d06f13f0b733e.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2013-10-08-80d196f4b7afc8814f945db9453e869284be9d739679247160bfa44ba25aa087.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2014-01-24-6453d9f8f86963d8917b93b60f6021e1bbb0a38606c685cf3bb0f3172757d920.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2014-04-10-a2a199aba01237282a442afd2493106432d3f48bf43d351ff16db6c92f929ef8.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2014-08-01-93fcb6353500f3d10c0156bb9c19aa1f08301fac3172b8d11c220129791cce15.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2014-10-01-69b699401a76081feb2c81d404633e1d8748d332daec7238e75257b063907f02.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2014-12-12-9bc13a519a8b5bc6792a00e25945895b7b91ca213d218226fe1f695a76c4c7ef.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2015-01-05-5ae127925519cf128ef3bc9a17686e112238d36c3a1fef8530fece422426e64f.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2015-03-10-45037c43c6974eda4358ba37466647cbe5700b162ae22826316ae10ad264b93e.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2015-06-29-243022ec5dd8f69ee4cd13c86bdff2d735f1c8fcf2724a446e9462e3d5e9bd24.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2016-11-01-23b75ddb14c19f89dfe965efc391823e7fc4fd92eaae4a7f862619e772eaee78.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2018-02-02-c3a9211cdb503abc3568c1f6e774e5c2c7fe6a274ce4fd2e9de7e6a80cce0755.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2018-10-10-e45c6df92662774eeb4c2abbd9cccd2e1c0f09b6a068bc28fb65fe6cb967c6a6.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2019-05-13-aa41117fb635b0bf98d5a67c8e7899666f843a12f23e45dc83e1eadb172be692.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2019-08-02-5420d843767ec4ad7fd0602313f6645e887e1d555828ba9bf5fe6eb0f4385ee7.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2020-01-31-b890ffb06eec49dd3cb1230c2100d0098851101858606e1fe4092b10e6161ff1.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2020-02-24-81bcf549e423f5a387c4d85e5dfb492b8e578d4b71662ef01d02a4d22a1ed32e.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2020-09-03-bf3ea5f339df7a72509e3bf992b8ab214cb28f34b9bac76c74935c8f57be508e.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2021-01-29-9ffec5b933ed024ea443e1a8c74567d4ee50cfe6c391df4fe5b69e5e2ede0348.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2021-02-26-2c0bc24301cf91c8940a205e4abe8b1d6403c169e04439bc32e5576665b0cc2a.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2021-05-12-ad92cc38331371cd76e4f1f8fc449d94ba9a636d3db7105260e9c389c0b60457.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2021-09-20-910cc0c679aa1827a2d3d47cb673b25e1c088a9ec0cfa93c62ffcd05a84e8eb5.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2021-12-01-6840ef668fbed5a66b81c0aa19a92ff0e61e65bd6062e00e34036c4fbd8ad167.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2021-12-20-a82d732c47a0b26c267112f98de1efbc8fa0c40d1834ab259f858e6246ab3502.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2022-01-18-03b8deb8191832eb0dff0d00efb3962877d777805a0f30b94b75ccb484cfd6c6.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2024-04-15-b9bd50a93b4af042c2f2c152a50d958e328da887fe32b45adf607e7959bf2864.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2024-07-24-86218afdfa49dbe26f4c30f534caa695bd4a59a34cf1c52ced40e58fe1871f78.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2024-12-18-3d7ddf9eda0cb5fbf6431ae6d2a63c4e25462cd24f9810d9b97c0651bf352c97.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2025-02-25-c73f2997bb41d840d5cb4faff74f5d23bb419d636f7fbd6e2509bc54785e0c07.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2025-11-17-70fd9dd2d68b973182208a2f60fe9c5a93ae3554801ef511e06d815b51bc8015.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2026-03-06-4d918951ccfb17ebf6c6772d93f015fa36e5edad1ac5213310a1ec108a30b7a5.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2026-06-10-9f028ad62a2425584fe1303f0edf936a2a1ed2150ba441f93694767259104b9f.json`
- `research_history/ath_official_vintages_v1/receipts/PAYEMS-2026-09-16-e4c11ff707ed4cf7a7dba544ff343d1cf811e12a026f121520b9ed89ffbae4d3.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2007-06-07-2962aa7268f19f69ab870ef134fc46b0ddae73ba93f4bfdcdc634a309c5aa08f.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2007-07-26-a6790e14365e5b198122cbb6ecde4fe6c7bdd3e3347585c0765e8cecea1a68da.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2007-10-19-20f738b447be37fa7088f019ac584c76a1d63034b54acbc842d76412eebfc445.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2013-04-18-5b05057b449ffdea7df295378d1b0019e88f593f02bc90c13fa0c04c1525b2eb.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2013-06-05-2c918b1fef5f642537306c7554cf99f5e9bbbec6ab84f585010a70b8634409f9.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2013-08-16-b02a212335576489dbda9c23891ef1e6734c56dfb4790a67f7a89320f180f62c.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2013-10-08-9c0865f65e3dc7c19af283512e93f30183419b344ae265317358be13362a3bd8.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2014-01-24-cc4a690030ae79742c0e8bcb352ff51fe377a1557a451bbc8fe3c8d80ed35d91.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2014-04-10-1f0f70795875b641967cb3feba16c167e159526b7a5d918e30ff49f07200960d.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2014-08-01-fe4cede3c86953ceb165fcf48dbf17b62285c45919a88d2d8947887f9b0b2861.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2014-10-01-ca689beabcb2e9beb72c6346476cab2bdfc8b329a14b6da85d8e8dd7fa13eeab.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2014-12-12-38a9cd2267ae4fa52694bd4401007cb4909f644ff84893b04ebd0adeb1d2bcd8.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2015-01-05-d68c05078411b7700ecc8a37a5c85c5c631c5bdb4f731953b083dce388ed79b6.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2015-03-10-5605d33bf2e596724ff288e9916837ecc8e4ac7de187380479d8b045911d1d5c.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2015-06-29-ca095dbb92db8e3ad2c0b6dcda7ce8bbfafa5dfddb95b7bcbf46e10ffd738124.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2016-11-01-e5c6bd72bccb92bba601a6f126304945e0e7f5362c696c5a670911490b1aff10.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2018-02-02-4144bb39d130d200e4efb8a9013dea0b9c1787735be82626cfcabf7b4a08ee69.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2018-10-10-77403acee9510c8bd8d3ad2941949cb8a13de78e3382cf36e900429b73b81936.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2019-05-13-eca0ee9a99f1075ccb548fb54dd5cb900f5ac2d05c24460fa06a2ced23bcd4a4.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2019-08-02-38d71072448db444814049fb97005a371ea81f62375399e34592925ba514a904.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2020-01-31-fd89e91802f3aeb0bf388f4338a8982899840c270d008f7885c49e2cbca70a3c.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2020-02-24-a211d00b7c56fffdc52e762d29300c9daa49bfbabcdfbe88966b78b309c3e150.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2020-09-03-50455084fc9d4c9a78de3b37658a67b53b37a3a63ffa76b591b3e1f183981ffa.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2021-01-29-8ba072f5d0a4314e49c7a1d189dd9149e56b2c96b4910fa2c58f74add1a322f9.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2021-02-26-bfc732087b0677751e71955f56fb63953e81b9ef6d2369ce29cebe24294971e1.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2021-05-12-fca0aab563b2d744cadb8250334070905c63d2bef6e6c286f400552b960c9de2.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2021-09-20-ebcb0c2e7e6d4fb863100e815759b2a36c16f00b3606d091cb762471d53f3996.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2021-12-01-611533ad6bac0e72a9e4889f0b607157f2daa8b44ccf8071e4c1361a9b9d13e7.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2021-12-20-4d1ce1afc5989dabc5ec6fcd40245bd672b881dadb3db3b3632496bcf9369874.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2022-01-18-27ef615235de8308d3b36c5f10c864d2c0cd94ebc8a00ab204bab90a9bbbf9d8.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2024-04-15-5f2f1c3157edfac6365556965101b2ef163351bbed6ee8d79abbbf9d2e145776.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2024-07-24-966200f277e8e7792640c86992c624cf4a9b5aa713e1b9a3692543b0bfebf2e0.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2024-12-18-94fdbe9df0fdb388a07fabd0c9c78683f260ad637c62dea453b00603ca0daec0.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2025-02-25-d7178d1a2cd990eddde7238fe4f2cced2cb732868ef213b91edfc9f5029f2b90.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2025-11-17-21576a0ad2f17047a931cb5f9478d54c939e156975dd29280576366fafb370bc.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2026-03-06-84731513433543cbf6f95dbed25d8b6eaf32acff19a1e30f7b76b96e9f57bf18.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2026-06-10-50094142a9cd7e229bad7d1e423e94e23746e71cb0c4cb2d9f3ef192146eab79.json`
- `research_history/ath_official_vintages_v1/receipts/PCEPILFE-2026-09-16-3636d53fa57614519ec215ad36ed8feb8b4726bf60a478cdb57cd9c454e2a25c.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2014-04-10-264caef55cc10fc0c872542894ff8831e4c4c6012879d7525fc4a53d8c7e7e6e.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2014-08-01-177ae59d22dd3bf5b2e7cd628382b15c73b2b2e24fd4532935f69152d5bcca89.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2014-10-01-07c2f326b81f9fd44eb75a6782c0ba63e87f424f55c3fba76ec74ff214aa6b02.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2014-12-12-2844113710732a27c30809dc41c7371bcfee2b05f4395745aee854c009f89a45.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2015-01-05-3a92d950f6199490253373c8c2d832745f1dac2c38959d1522abccbdaa7c5b77.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2015-03-10-6e796722aebc42cbab659bcec79d2599b7cc1961ac6e6a0ecbb7894ec856afe0.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2015-06-29-4aaf6ddf5d7fe568814f3a667c538970c64c736162f14120baf2ce71e2645b40.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2016-11-01-b16082baf932c0bd72d99cb21e466d6bad12dd9954d91565a2e7d747942cc68c.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2018-02-02-5976cc7362e145e4657ca13f8db4fc03856a3095771e5138bda983589f7adc76.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2018-10-10-0449b8bfcd078b2b99a1f4af8a87e7310693d298d773ea9401ae193074d61d77.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2019-05-13-bd509f275e93672e5b53361342a8559b649a9f3740ad9e0d9e9c14999dfe3fb2.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2019-08-02-2944511b6a1f55f3352ae9fc7a1d94a5831947ccae00285a0750f1d5e7d9e4b5.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2020-01-31-00db09899812a3bdf722d903527fc95ad357f2396b2de41a5a55f0aff2ae6f0b.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2020-02-24-4501fcbb91a0b3895f3f3a65e24c65c6d427401e488c0da81969f2c50b32c593.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2020-09-03-2171d52ad9fd4345db02555c949049271178059eab29a7eb863050fe56a82ade.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2021-01-29-c82d8b2f0cfeda302cf2528bd35c25fd352d9ac07e7869bc42418d335cb00158.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2021-02-26-7d0dc5563b875b13626479c05e04d69a00a07d0886eb3703538883876690eca0.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2021-05-12-304d1b3d5ed7eeb38b1a9e057c7432e29d048224ed684dbc87eef0388f77db4d.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2021-09-20-90fea4250cc2cb80ba43d56803e254da808332b14b630ace167d3822b1897366.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2021-12-01-950a20596622960da4855fb1146306a82db7aa4a0263c48e0bfc543abb993ded.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2021-12-20-4b5b8e95507354dc76cd246b5442b2758f9ef853d8e421f1ad89432e66abfcf9.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2022-01-18-3fcdfec6c426c1c982cf5ab4e440e4742bb8f669bd5c0a03995340d03e618779.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2024-04-15-54a9f801d3055dd67c479e947611a9ec0e68c98928df26508fed196dde9cb381.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2024-07-24-f9df049315c8a6fb46b41afd7277f5843cc2b5a589f5ac550e5cfc77830a521c.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2024-12-18-0216b8aa20c17f3efa16757da868a535d53d842b61d21bea0322c5bbc88450b6.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2025-02-25-c02c88925b420e275e158ccfa739f0ad939cccc1b9cdf2dd2537e525ee601246.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2025-11-17-f1315dd2403b117fc2a1a1a3244c6b95d1e1a101474abf793958bda0ada15f6a.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2026-03-06-cf9c1a000c4ed0526d1a94869d3a3a8e3af6d160fa35d3af5814d37339910330.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2026-06-10-4aca6ad12c7f1ef6979d231a0e076eebfd650cb6c637d434f672b3e7019032e0.json`
- `research_history/ath_official_vintages_v1/receipts/T10Y3M-2026-09-16-6da9c7c5c464fbeb1c2b1cea5c17468f590753de5754e7c6e57b28df4dd656ef.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2000-04-12-2be16566aed74a1b60ba1ca508ec798fda43a19e69f026c8b870fd6a2db51ef6.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2007-06-07-88725d6766db71b6fd63b927687be716582ce6e5a60ed34519533e108f8303e8.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2007-07-26-53a6faf0b8be444fe171c57202f0b1fd1bfabb38f0649819f866641ebbea8976.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2007-10-19-9d2a3e29153de02765ecb32ea8c52378f8c9fdb1858480865271175d94b15f0e.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2013-04-18-6e686dbfbf52a424c3451563fb4c6458a6813424c8a575f4cd04cf0c648f22b8.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2013-06-05-9f30a97675cd912ca8bece66a703072592704ba7149283d01f3ad98a46a0d04c.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2013-08-16-4faa024a28bb1bb9ce2039b2fb1c1e35f81a691904d679979a07f3dde4c8876a.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2013-10-08-c4c4337e7b18c1c7aa14d36e1c16d72d6e7c6ef7117d17797a528eb9b9079a89.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2014-01-24-3da8d97f17a5b3e4dda516b1e9d748f0a21f1b0ea8c781a3952f1737c2497a61.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2014-04-10-ccd5e288f9d38876d6d1afd787f312a665117c9017df40a4a5470ca29cabaf77.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2014-08-01-219d0079460dcf7b4ceca401c5b71a476b3c7a16745db55e6fd8cbd67f83f4e9.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2014-10-01-46e88bf6c8d51043759e851c0e73d7ca882acad491c1d9623d83c8c5e0218e88.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2014-12-12-6236a72d615e58f14136527a539d44f28c95e353508a48c78a37619a4c4655df.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2015-01-05-ce7b26622f626406d44486f4f2225b336d4456fbd33db60bf18c1aa97846afdb.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2015-03-10-8bd1f2cbd9d05aa8436cffeae589f0928cbc9886ad7ca656b338b9a3a38b14d7.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2015-06-29-2ca271840c62c990a59232184056096807341efcf48d9921db83ee4e4ee466f8.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2016-11-01-26abe0ff2ebfe5d01b9dc39bfeac44cad21c01c84dc70155774cc772f83c9b54.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2018-02-02-11887338898885d82d737eaf3e934392feff6d9414c6051dcde14ad2b5744744.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2018-10-10-28c838ff1fbe986f3cfc3be5f0cd7565ede8fc6d3103c5333df8b71206d80c0f.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2019-05-13-e4e728ec98be3bd715df258e0c1c0e1dfb386e18c82833f26e83e59f729f34fd.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2019-08-02-0db5053ebd9f94ceb2b34b88b84a6eb25835cf5316cdd782c75be5c7025d4327.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2020-01-31-bdfe810d09d42d57e38792902f5bd7579e2de9d56df7df2c0280d6d42cc475f7.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2020-02-24-3a11aadc0619004bb19593d55050520cdbb9e8d065070e39018362186d9f58f9.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2020-09-03-c82373c48594191c28ad61d7f3b69da3fbb2b1d240fd03fe9025359011a0be93.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2021-01-29-52e6ff3be667ca3fb050da203cd7297ffa6336efabbaeb168ba63c47370cbdcb.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2021-02-26-32ae799de60e3f08063b251e7046de99bfef78550e9c208ead6a3801483a6096.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2021-05-12-b9a112b2f11435b5c13b6daf0fcbb250a50956d1f965ec5f6e00bc87730c921b.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2021-09-20-ac7de62aa0c4223a0087f1c0c49e1962b076605111fb63f5fd354cb87705f89d.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2021-12-01-ce8f7e52963a0f6c5258de1777c3c49dfdd994d3e8fb9c98bccae382cf34fd60.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2021-12-20-2899a6d1c0abfb804df6b6ea9173b8e543c132daa542021139872e31a70562be.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2022-01-18-67e785adbdd298e4eaf4cdd041a124784d11317fb10c16e6cc2024a9ee5f47b8.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2024-04-15-ab4cdbe4ccf4005dadb640d80ad52811787de24a8f3386931f190305c45ea8be.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2024-07-24-5ab7cda1749dd88b134f133bc2a73ad3fe31f75e3147aad590f02344c690758a.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2024-12-18-0de19c2e6dbb7877e1143b65d3b16ca784f88fc9b918fcfe64b6647bf8d9aa23.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2025-02-25-1400cde41d8717a75077f7cc045a1b381f9333a3febbb0a1a7f50c1eb60e27ea.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2025-11-17-315315f0b9c821f16d569d1a6bf20507a76833e8264f4e31a8c73a828c1127a9.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2026-03-06-33b1f92e5bc5676963e3ea6c2f2022601aaffadc66a7e45fb886deece2efa753.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2026-06-10-8bf6b3056011a8b6be6336977df913e00f3079bd61a6f5ca32c315993dea57fe.json`
- `research_history/ath_official_vintages_v1/receipts/UNRATE-2026-09-16-cb404c20ff17baa707b733b08879c0636a07c5caa6cecf47b2a8c0a8bb3b7b31.json`
- `tests/test_ath_macro_edge_research_v4.py`
- `tests/test_ath_official_vintage_backfill_v1.py`
- `US500-ATH-Vintage-Fix-V4-Report.md`
