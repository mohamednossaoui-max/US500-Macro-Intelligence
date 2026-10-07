"""Read-only cause evidence inside the existing ATH page; no unvalidated forecasts."""
import json
from pathlib import Path
import streamlit as st
from ath_cause_context_v1 import assess


def render_cause_context(root):
    st.subheader('ما الذي قد يضغط على السوق؟')
    try:
        r=assess(root)
    except (OSError,ValueError,KeyError,TypeError) as e:
        st.error('تعذر التحقق من أدلة الحالات: '+str(e));return
    active=[x for x in r['causes'] if x['status']!='UNVERIFIED']
    st.caption('الأخبار ترصد حالات محتملة، والبيانات تؤيدها أو لا تكفي. لا تثبت سبب الهبوط أو مقدار أثره.')
    if not active:st.info('لا توجد حالة مدعومة ضمن الأدلة المؤهلة؛ هذا لا يثبت غياب المخاطر.')
    for c in active:
        st.write('**'+c['label']+'** — '+c['status'])
        for x in c['news_evidence'][:3]:st.markdown('['+x['title'].replace('[','').replace(']','')+']('+x['url']+')')
        if c['context_evidence']:
            st.caption('التأييد العددي: '+' · '.join(f"{x['feature']}={x['value']:.3f}" for x in c['context_evidence']))
        st.caption('قوة الدليل: '+c['impact_evidence']+' · إسناد سبب الهبوط غير مثبت.')
    p=r['observed_market_response']
    if p['price_status']=='STALE':st.warning('لقطة الأسعار قديمة؛ آخر جلسة '+p['last_session']+'. لا توجد قراءة سعر حي.')
    st.caption('الاستجابة المرصودة: '+p['response']+' · آخر جلسة '+p['last_session']+' · لا توجد بيانات مؤكدة كافية عن اتساع الأثر واستمراره.')
    st.write('**احتمال عمق التراجع: غير موثوق حاليًا — محجوب**')
    st.caption('المستويات البحثية: −5%، −10%، −20%، −30%، بعد أول إغلاق عند −3% من قمة الملف، خلال 63 جلسة وقبل استعادة القمة. لا يحوّل وصف الخبر إلى نسبة مئوية.')
    path=Path(root).parent/'research_history/ath_cause_v1/ath_cause_depth_audit_v1.json'
    if path.exists():
        try:
            a=json.loads(path.read_text());st.caption('الاختبار الأرشيفي: '+a['status']+' · لقطات '+str(a['snapshot_count'])+' · صفوف كاملة السياق '+str(a['events_with_full_context']))
        except (ValueError,KeyError,OSError) as e:st.warning('تعذر قراءة نتائج الاختبار: '+str(e))
    with st.expander('الحالات غير المتحققة وحدود الأدلة'):
        for c in r['causes']:
            if c['status']=='UNVERIFIED':st.write(c['label']+' — غير متحقق، لا يعني غير موجود.')
        st.json({'excluded_features':r['excluded_features'],'excluded_news_count':len(r['excluded_news']),
                 'limitations':r['limitations']})
    st.download_button('تنزيل أدلة الحالات الحالية',json.dumps(r,ensure_ascii=False,indent=2),
                       'ath-cause-current.json','application/json',key='ath_cause_current_download')
