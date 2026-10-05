"""Depth context page. No orders, strategy rules, or uncalibrated predictions."""
import json
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from ath_pullback_context_v1 import audit, bars, classify, loss, study, describe


def render_ath_pullback_context(public_data=None):
    st.header('ATH Pullback Context — عمق التراجع')
    st.write('الهدف: دراسة السياق لتقدير هل البولباك محدود، متوسط، أم انهيار، مع قراءة لشهر وثلاثة أشهر وحتى استعادة القمة.')
    st.caption('الحدود البحثية: أقل من 3% حركة بسيطة · 3 إلى أقل من 5% محدود · 5 إلى أقل من 20% متوسط · 20% فأكثر انهيار. هذه حدود تصنيف تختارها الدراسة.')
    root = Path(public_data) if public_data else Path(__file__).resolve().parent / 'public_data'
    try:
        result, labels = audit(root)
    except (ValueError, OSError, pd.errors.ParserError) as error:
        st.error('تعذر التحقق من مدخلات الدراسة: ' + str(error))
        return
    st.info('التوقع غير معاير بعد. بيانات Macro / Fed / Decision الحالية لا تكفي لتدريب واختبار تقدير تاريخي شامل. الأعداد أدناه وصف للتاريخ المتاح وليست احتمالات للتراجع القادم.')
    a, b, c = st.columns(3)
    a.metric('أعلى قمة في التاريخ المتاح', f"{result['reference_peak']:,.2f}")
    b.metric('التراجع عند آخر إغلاق', f"−{result['drawdown_at_last_close_pct']:.2f}%")
    c.metric('التصنيف المرصود حاليًا', result['current_observed_class'])
    st.caption(f"المصدر المنشور: {', '.join(result['instrument'])} · {result['history_start']} إلى {result['last_session']}. المؤشر النقدي ليس أسعار ES أو US500 لدى الوسيط. التاريخ المحدود لا يثبت ATH مطلقًا.")
    for col, name in zip(st.columns(3), ['حتى استعادة القمة', 'خلال شهر', 'خلال ثلاثة أشهر']):
        col.metric(name, 'التقدير غير متاح')
    st.write('حتى الاستعادة: يُقاس الهبوط من القمة المرجعية حتى العودة إليها. الشهر والثلاثة أشهر: يُقاس أكبر هبوط داخل المدة، بما يشمل الهبوط من قمة جديدة تتحقق خلالها.')
    render_record_research(root)
    render_model_research(root)
    render_edge_research(root)
    render_macro_edge_research(root)
    with st.expander('السياق المتاح قبل تاريخ لقطة الأسعار', expanded=True):
        for item in result['context_inventory']:
            st.write(item['file'] + ' — ' + item['status'])
            if 'historical_anchor_count' in item:
                st.caption(f"سياق مؤهل بالتاريخ عند {item['historical_anchors_with_context']} من {item['historical_anchor_count']} قمة في العينة. تاريخ البحث المنشور لا يثبت وحده صحة كل vintage تاريخي.")
            if item.get('current_context'):
                st.json(item['current_context'])
        st.caption('لا يعاد إسقاط السياق الحالي على القمم القديمة. غياب سياق مؤهل لا يعوّض بقراءة مستقبلية.')
    st.subheader('الدراسة التاريخية — ليست توقعًا')
    rows = []
    for item in result['horizons']:
        rows.append({'المدة': item['horizon'], 'العينات': item['sample_count'],
                     'المكتملة الواضحة': item['complete_unambiguous_count'],
                     'غير المكتملة': item['censored_count'], **item['historical_class_counts']})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption('حتى الاستعادة: تعداد رجعي لبولباكس وصلت أو ربما وصلت 3%، دون تكرار نفس الحلقة. الشهر/الثلاثة أشهر: قمم اختيرت بالتاريخ ومتباعدة أكثر من ثلاثة أشهر. العينتان مختلفتان؛ لا تقارن أعدادهما كاحتمالات. ترتيب High وLow داخل اليوم غير معروف؛ تُحفظ حدود العمق والحالات الملتبسة.')
    st.download_button('تنزيل تدقيق العمق والسياق', json.dumps(result, indent=2, ensure_ascii=False),
                       'ath-depth-context-audit.json', 'application/json', key='ath_audit_download')
    st.download_button('تنزيل قياسات القمم التاريخية', labels.to_csv(index=False),
                       'ath-depth-labels.csv', 'text/csv', key='ath_labels_download')
    with st.expander('دراسة ملف أسعار ES أو US500 مستقل'):
        st.caption('كل أداة تُقاس من قمم ملفها الخاص. استخدم جلسات مكتملة وتاريخ عقود موثقًا؛ الملف المرفوع لا يصبح توقعًا اقتصاديًا تلقائيًا.')
        for instrument in ['ES', 'US500']:
            file = st.file_uploader(instrument + ': Date, Open, High, Low, Close', type=['csv'], key='ath_file_' + instrument)
            if file is None:
                continue
            try:
                frame = pd.read_csv(file)
                data = bars(frame)
                peak = float(data.high.max())
                depth = loss(peak, data.close.iloc[-1])
                st.write(f'{instrument} · قمة الملف {peak:,.2f} · هبوط الإغلاق {depth:.2f}% · {classify(depth)}')
                st.json(describe(study(frame)))
            except (ValueError, TypeError, pd.errors.ParserError) as error:
                st.error(str(error))


def render_model_research(public_data):
    history=Path(public_data).parent/'research_history'
    path=history/'ath_depth_model_audit_v1.json'
    with st.expander('اختبار هل يضيف السياق معلومات عن عمق التراجع؟',expanded=True):
        if not path.exists():
            st.info('نتائج اختبار النموذج غير منشورة في هذه النسخة. لا يوجد توقع موثّق بعد.')
            return
        try:
            report=json.loads(path.read_text())
            st.warning('ميزة التوقع غير مثبتة — الاحتمالات المباشرة محجوبة.')
            st.caption(f"أرشيف السياق: {report['source_snapshot_count']} لقطة · الاختبار على المؤشر النقدي، وليس ES أو US500 لدى الوسيط.")
            if report.get('source_hashes'):
                changed=[name for name,sha in report['source_hashes'].items()
                         if not (Path(public_data)/name).exists() or hashlib.sha256((Path(public_data)/name).read_bytes()).hexdigest()!=sha]
                if changed:
                    st.info('تغيرت مدخلات منذ هذا الاختبار؛ النتائج أدناه أرشيفية وتحتاج إعادة الحساب.')
            rows=[]
            for item in report['analyses']:
                scores=item['partial_context_common_sample']
                rows.append({'المدة':item['horizon'],'اختبارات زمنية':scores['evaluations'],
                             'خطأ الأسعار فقط':scores['price_brier'],
                             'خطأ إضافة السياق الجزئي':scores['context_brier'],
                             'خطأ الاحتمالات التاريخية':scores['climatology_brier'],
                             'اختبارات السياق الكامل':item['full_context_common_sample']['evaluations']})
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.caption('الخطأ الأصغر أفضل. المقارنة على الحالات نفسها وبالتدريب على نتائج اكتملت قبل كل قمة. السياق الجزئي: الضغط المالي، المعنويات والسيولة. العينة الصغيرة لا تثبت دقة عالية أو قدرة على توقع الانهيارات.')
            st.download_button('تنزيل نتيجة اختبار النموذج',path.read_bytes(),'ath-depth-model-audit.json','application/json',key='ath_model_download')
        except (OSError,ValueError,KeyError,TypeError) as error:
            st.error('تعذر قراءة تدقيق النموذج: '+str(error))


def render_edge_research(public_data):
    path=Path(public_data).parent/'research_history'/'ath_edge_v3'/'edge_v3_audit.json'
    if not path.exists():return
    with st.expander('دراسة موسعة: عمق الهبوط بعد وصوله إلى 3%'):
        try:
            report=json.loads(path.read_text())
            st.warning('لا توجد ميزة تنبؤ مؤكدة. هذه نتائج بحثية وليست احتمالات للسوق الحالي.')
            st.caption('الدراسة تبدأ بعد هبوط إغلاق 3% إلى أقل من 5% من قمة إغلاق في التاريخ المتاح. لا تمثل توقعًا يوم ATH أو أسعار ES/US500.')
            source=Path(public_data)/report['source_file']
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:
                st.info('المدخلات تغيرت؛ الدراسة المعروضة أرشيفية وتحتاج إعادة حساب.')
            st.dataframe(pd.DataFrame([{'المدة':x['horizon'],'حالات الاختبار':x['evaluation_predictions'],
                'حالات الانهيار':x['test_class_counts']['CRASH'],
                'خطأ السياق':x['mean_scores']['market_brier'],
                'خطأ الأسعار':x['mean_scores']['price_brier'],
                'خطأ الاحتمالات التاريخية':x['mean_scores']['climatology_brier']} for x in report['analyses']]),
                hide_index=True,use_container_width=True)
            st.caption('الخطأ الأصغر أفضل. فترة الاختبار سبق الاطلاع عليها في دراسات أخرى؛ يلزم اختبار مستقبلي مستقل قبل إثبات edge.')
            st.download_button('تنزيل تدقيق الدراسة الموسعة',path.read_bytes(),'ath-edge-v3-audit.json','application/json',key='ath_edge_download')
        except (OSError,ValueError,KeyError,TypeError) as error:
            st.error('تعذر قراءة الدراسة الموسعة: '+str(error))


def render_macro_edge_research(public_data):
    path=Path(public_data).parent/'research_history'/'ath_macro_edge_v4'/'macro_edge_v4_audit.json'
    if not path.exists():return
    with st.expander('اختبار السياق الاقتصادي التاريخي الموثق'):
        try:
            report=json.loads(path.read_text())
            st.warning('النموذج الاقتصادي لم يثبت edge؛ لا توقع مباشر منشور.')
            source=Path(public_data)/'cross_asset_research_v1.csv'
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['price_source_sha256']:
                st.info('هذه نتائج أرشيفية؛ تغيرت مدخلات الأسعار وتحتاج إعادة حساب.')
            st.caption('ميزات التوظيف والبطالة والتضخم والإنتاج الصناعي مستخرجة من receipts تعكس vintage سابقًا لكل قرار. لا تستخدم القيم الحالية للقمم القديمة.')
            st.dataframe(pd.DataFrame([{'المدة':a['horizon'],'حالات الاختبار':a['evaluation_predictions'],
                'خطأ السياق الاقتصادي':a['scores']['macro'],'خطأ الأسعار':a['scores']['price'],
                'خطأ الاحتمالات التاريخية':a['scores']['climatology']} for a in report['analyses']]),
                hide_index=True,use_container_width=True)
            st.caption('الخطأ الأصغر أفضل. نتائج بحثية بعد هبوط 3%؛ ليست توقعًا يوم ATH أو معايرة مؤكدة.')
        except (OSError,ValueError,KeyError,TypeError) as error:st.error('تعذر قراءة دراسة السياق: '+str(error))


def render_record_research(public_data):
    path=Path(public_data).parent/'research_history'/'ath_record_high_v6'/'record_high_v6_audit.json'
    if not path.exists():return
    with st.expander('الاختبار من يوم القمة — قبل حدوث التراجع',expanded=True):
        try:
            report=json.loads(path.read_text())
            st.caption('هذا الاختبار يختار قمم إغلاق بالتاريخ، ويحتفظ أيضًا بحالات استمرار الصعود. المؤشر النقدي وتاريخ القمم المتاح لا يثبتان ATH داخل الجلسة أو أسعار ES/US500.')
            st.warning('لا توجد احتمالات حية معتمدة. السياق الاقتصادي يجب أن يعود إلى تاريخ القمة نفسه.')
            source=Path(public_data)/'cross_asset_research_v1.csv'
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:
                st.info('نتائج أرشيفية؛ تغيرت المدخلات وتحتاج إعادة حساب.')
            for column,item in zip(st.columns(3),report['analyses']):
                score=item['price_and_market_common_sample']
                column.metric(item['horizon'],str(score['evaluations'])+' اختبارات')
                column.caption('السياق الكامل: '+str(item['full_context_common_sample']['evaluations'])+' اختبارات')
            comparisons=[]
            for item in report['analyses']:
                sample=item['full_context_common_sample'];scores=sample['scores']
                if sample['evaluations']:
                    comparisons.append({'المدة':item['horizon'],'الحالات':sample['evaluations'],
                        'السياق الكامل':scores.get('full_context'),'المرجع التاريخي':scores.get('climatology')})
            if comparisons:
                st.caption('Brier: الأقل أفضل؛ مقارنة على نفس الحالات. النتائج استكشافية ولا تثبت edge.')
                st.dataframe(comparisons,hide_index=True,use_container_width=True)
            if all(x['full_context_feature_rows']==0 for x in report['analyses']):
                st.info('الأرشيف الحالي جمع vintages عند بدء هبوط 3%؛ لا يغطي تواريخ هذه القمم. شغّل ATH Record High Context Audit لجلبها.')
            st.caption('حتى الاستعادة يعني العودة إلى القمة المرجعية المختارة، وقد يحدث ذلك في الجلسة التالية. لا تستبعد هذه الحالات لتضخيم عدد البولباكس. نتائج الشهر والثلاثة أشهر تقيس الهبوط من قمم متحركة داخل المدة.')
            st.download_button('تنزيل تدقيق الاختبار من القمة',path.read_bytes(),'ath-record-high-v6-audit.json','application/json',key='ath_record_v6_download')
        except (OSError,ValueError,KeyError,TypeError) as error:st.error('تعذر قراءة اختبار القمم: '+str(error))
