# US500 — إصلاح اكتشاف artifacts لمصادر Sentiment

## السبب المثبت وحدود التشخيص

السجل يرفض COT Positioning وAAII Sentiment؛ VIX موجود. الـWorkflow السابق يجلب صفحة واحدة فقط من `/actions/artifacts?per_page=100`، ثم يبحث فيها. تراكم artifacts بعد التشغيلات المتكررة يجعل ملفًا أقدم خارج نافذة البحث رغم احتمال أنه لم ينتهِ. لم يتم الوصول إلى API المصادق عليه لحساب المستخدم، لذلك لا ندعي أننا أثبتنا وجود COT/AAII في الصفحة الثانية فعليًا؛ قد يكونان أيضًا منتهيين أو لم يُنتجا.

وجدنا نفس حد الصفحة في اكتشاف historical لدى محللات COT وAAII وVIX. ترتيب Master صحيح: historical ثم analyzer ثم Sentiment Engine، ويُشغّلها طبقًا لخطة الاعتماد الحالية. لا حاجة إلى تغيير الترتيب بسبب هذا الخلل.

## التغييرات

- `.github/workflows/sentiment-engine-v1.yml`: اكتشاف جميع صفحات API بواسطة `gh api --paginate --slurp` ثم تحويلها إلى inventory موحد قبل الاختيار الموجود أصلًا. لا تغيير أسماء ملفات outputs أو الحساب.
- `.github/workflows/cot-positioning-analyzer-v1.yml`: البحث عن cot-historical-v1 عبر الصفحات كلها.
- `.github/workflows/aaii-sentiment-analyzer-v1.yml`: البحث عن aaii-historical-v1 عبر الصفحات كلها.
- `.github/workflows/vix-sentiment-analyzer-v1.yml`: البحث عن vix-historical-v1 عبر الصفحات كلها.
- `scripts/actions_artifact_inventory_v1.py`: تجميع الصفحات، إزالة duplicate مطابق، رفض duplicate متعارض أو metadata ناقصة، اختيار أحدث artifact بالاسم الصحيح وغير منتهٍ، مع ترتيب deterministic. رسالة غياب واضحة بعد عدد الصفحات المفحوصة.
- `tests/test_actions_artifact_inventory_v1.py`: regression لما بعد أول 100، expired، اختلاف النوع، duplicates، metadata تالفة، CLI وفشل الملف المفقود.

وجود artifact لا يثبت حداثة بياناته الاقتصادية. لم نعدّل freshness أو PIT أو بوابات جودة البيانات، ولم نضع fallback إلى أرقام وهمية أو نعلن CURRENT بسبب وجود الملف فقط. إذا غاب المصدر بعد كل الصفحات، يظل التشغيل fail-closed.

لم يتغير Master أو Autonomous أو app.py أو public_data/manifest. سيستخدم Master/Autonomous الـworkflows المصححة في التشغيلات الجديدة. لا commit/push/merge أو تشغيل حساب GitHub من جانبنا.

## الاختبارات الفعلية

- `python -m pytest -q`: 496 passed، 6 تحذيرات pandas FutureWarning، 25.04 ثانية.
- `python -m pytest tests/test_actions_artifact_inventory_v1.py -q`: 8 passed.
- `python -m pytest tests/test_publication_integrity.py tests/test_point_in_time_integrity.py tests/test_actions_artifact_inventory_v1.py -q`: 24 passed.
- `python scripts/verify_publication_integrity.py`: 106 Match، 0 Mismatch، 0 Missing، 0 Error.
- parse YAML و`bash -n` لكل shell block داخل workflows الأربعة: PASS.
- تشغيل نصوص discovery/selection الفعلية في workflows باستخدام gh mock: 100 artifact غير متعلق في الصفحة الأولى، وجميع مدخلات Sentiment والـhistorical الستة في الصفحة الثانية. نجحت خطوات Sentiment/COT/AAII/VIX، واختار Sentiment IDs 101/102/103.

المحاكاة تثبت الكود، وليس توفر artifacts في حساب GitHub. أُعيد ملفان يولدهما pytest إلى البايتات الأصلية المطابقة للـmanifest بعد الاختبار؛ لم يُعدّل manifest لإخفاء mismatch.

## ما يفعله المستخدم

1. فك ZIP في جذر نسخة المشروع وارفع الملفات الستة إلى GitHub مع الحفاظ على مسارات `.github/workflows/` و`scripts/` و`tests/`. الحزمة تكمّل النسخة الحالية وليست المستودع كله.
2. ابدأ **تشغيلًا جديدًا** لـSentiment Engine v1 من Actions → Run workflow، ليستخدم الملفات المصححة.
3. إذا نجح، ابدأ تشغيل Autonomous Intelligence جديدًا.
4. إذا استمر الغياب بعد فحص الصفحات كلها، تكون هناك حاجة إلى إنتاج/استعادة المصدر: COT Historical v1 ثم COT Positioning Analyzer v1؛ وAAII Historical v1 ثم AAII Sentiment Analyzer v1. وجود الملفات خارج أول صفحة لن يتطلب إعادة إنتاجها بعد الإصلاح، لكن الملف المنتهي أو غير الموجود لا يمكن اختلاقه.

التوكن المستخدم هو `${{ github.token }}` الموجود في workflows الحالية بصلاحية actions: read؛ لا secret جديد أو اشتراك. لم نرفع صلاحيات الكتابة.

## المرجع التقني

https://cli.github.com/manual/gh_api

توثيق GitHub CLI يوضح `--paginate` لمتابعة الصفحات و`--slurp` لتجميعها في مصفوفة JSON. هذه الحزمة تفصل تجميع الصفحات عن اختيار أحدث ملف لتجنب تطبيق اختيار مستقل على كل صفحة.

## محتويات ZIP

الملفات الستة المذكورة أعلاه، evidence/full-tests.log، evidence/publication.log، evidence/integrity-tests.log، evidence/workflow-validation.json، هذا التقرير وPATCH_CONTENTS.json الذي يسرد المسارات وبصمات SHA-256.
