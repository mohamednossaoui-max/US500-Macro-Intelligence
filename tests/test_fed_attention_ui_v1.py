import ast
import copy
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import typing
import unittest
from executive_attention_v1 import attention_rows, decision_explanation
from scripts.apply_fed_attention_ui_v1 import patch

ROOT=Path(__file__).resolve().parents[1]
BASE=Path(os.environ.get('US500_REVIEW_BASE', ROOT))

class AttentionTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'source':'Technical','category':'technical','stance':'SUPPORTIVE'},
                   {'source':'Macro','category':'macro','stance':'MIXED'},
                   {'source':'Stress','category':'stress','stance':'MIXED'},
                   {'source':'Sentiment','category':'sentiment','stance':'MIXED'}]
        self.fed={'available':True,'as_of_date':'2026-10-22',
                  'fed_score':{'score':61.6,'classification':'MODERATELY HAWKISH'},
                  'quality':{'quality_gate':'ELIGIBLE','pit_status':'OBSERVATION_CHECKED','freshness_status':'CURRENT'}}

    def test_fed_added_without_directional_vote(self):
        result=attention_rows(self.rows,self.fed)
        self.assertEqual(len(result),5)
        self.assertEqual(result[-1]['stance'],'CONTEXTUAL')
        self.assertIn('MODERATELY HAWKISH',result[-1]['reason'])
        self.assertIn('61.6',result[-1]['reason'])
        self.assertIn('excluded from Decision State',result[-1]['reason'])

    def test_missing_snapshot_not_invented(self):
        self.assertEqual(attention_rows(self.rows,None)[-1]['stance'],'UNAVAILABLE')
        self.fed['available']=False
        self.assertEqual(attention_rows(self.rows,self.fed)[-1]['stance'],'UNAVAILABLE')

    def test_degraded_snapshot_limits_visible(self):
        self.fed['quality'].update(quality_gate='DEGRADED',freshness_status='STALE')
        row=attention_rows(self.rows,self.fed)[-1]
        self.assertIn('DEGRADED',row['reason']); self.assertIn('STALE',row['reason'])
        self.assertEqual(row['stance'],'CONTEXTUAL')

    def test_inputs_unchanged(self):
        before=copy.deepcopy((self.rows,self.fed));attention_rows(self.rows,self.fed)
        self.assertEqual(before,(self.rows,self.fed))

    def test_no_duplicate_independent_fed(self):
        self.rows.append({'source':'Fed Intelligence (current)','category':'fed','stance':'CONTEXTUAL'})
        self.assertEqual(sum(r['source']=='Fed Intelligence (current)' for r in attention_rows(self.rows,self.fed)),1)

    def test_counts_explain_actual_screenshot(self):
        text=decision_explanation(self.rows,'SUPPORTIVE')
        self.assertIn('1 supportive · 0 contradictory · 3 mixed',text)
        self.assertIn('not broad agreement',text)

    def test_other_published_state_not_reclassified(self):
        self.assertIn('does not recalculate',decision_explanation(self.rows,'MIXED'))

    def test_actual_v1_rule_reproduced(self):
        source=(BASE/'tests/decision_engine/decision_engine_v1.py').read_text()
        tree=ast.parse(source); fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='classify_evidence')
        ns={'List':typing.List,'Dict':typing.Dict,'Any':typing.Any,'Evidence':object,
            'MIN_EVIDENCE':2,'MAJORITY_RATIO':0.67,'HIGH_CONFIDENCE_EVIDENCE':4}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual v1 classifier>','exec'),ns)
        result=ns['classify_evidence']([SimpleNamespace(stance=x['stance']) for x in self.rows])
        self.assertEqual(result,{'state':'SUPPORTIVE','confidence':1.0,'evidence_count':4,'supportive_count':1,'contradictory_count':0,'mixed_count':3})

    def test_patch_is_idempotent_and_syntax_valid(self):
        source=(BASE/'app.py').read_text(); updated=patch(source)
        self.assertEqual(patch(updated),updated);ast.parse(updated)
        self.assertIn('CORE + FED CONTEXT',updated)

    def test_patch_preserves_other_executable_code(self):
        original=(BASE/'app.py').read_text();updated=patch(original)
        def outside(source):
            tree=ast.parse(source)
            tree.body=[x for x in tree.body if not (isinstance(x,ast.FunctionDef) and x.name=='executive')
                       and not (isinstance(x,ast.ImportFrom) and x.module=='executive_attention_v1')]
            return ast.dump(tree)
        self.assertEqual(outside(original),outside(updated))

    def legacy_dashboard(self):
        # Exercise the legacy patch path even when app.py is already patched.
        return ('from __future__ import annotations\n'
                'def executive():\n'
                '    if True:\n'
                '        ui_section("Evidence Attention Order", "CORE EVIDENCE")\n'
                '        view = evidence.copy()\n'
                '        rank_item(1, "source", "MIXED", "reason")\n'
                '        st.caption("CORE eligibility, weights or state.")\n'
                '    with right:\n'
                '        pass\n')

    def test_legacy_dashboard_patch_is_valid_and_idempotent(self):
        source = self.legacy_dashboard()
        updated = patch(source)
        ast.parse(updated)
        self.assertNotEqual(updated, source)
        self.assertIn('CORE + FED CONTEXT', updated)
        self.assertEqual(patch(updated), updated)

    def test_changed_ui_rejected(self):
        source = self.legacy_dashboard()
        changed = source.replace('view = evidence.copy()', 'view = evidence')
        self.assertNotEqual(changed, source)
        with self.assertRaises(ValueError):
            patch(changed)

if __name__=='__main__': unittest.main()
