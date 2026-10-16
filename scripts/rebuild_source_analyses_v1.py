"""Recompute derived layers from the exact synchronized source CSVs, without network I/O.
Run only in the isolated integrated build workspace after public_data is copied to root.
"""
import os,subprocess,sys,shutil,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STAGES=[
 ('financial_stress_analyzer_v1.py',['financial_stress_research_v1.csv','financial_stress_research_summary_v1.csv']),
 ('cot_positioning_analyzer_v1.py',['cot_positioning_research_v1.csv','cot_positioning_research_summary_v1.csv','cot_positioning_extremes_v1.csv']),
 ('vix_sentiment_analyzer_v1.py',['vix_sentiment_research_v1.csv','vix_sentiment_research_summary_v1.csv','vix_sentiment_extremes_v1.csv']),
 ('aaii_sentiment_analyzer_v1.py',['aaii_sentiment_research_v1.csv','aaii_sentiment_research_summary_v1.csv','aaii_sentiment_extremes_v1.csv']),
 ('sentiment-engine-v1.py',['sentiment_engine_research_v1.csv','sentiment_engine_research_summary_v1.csv','sentiment_engine_extremes_v1.csv']),
 ('liquidity_intelligence_analyzer_v1.py',['liquidity_intelligence_research_v1.csv','liquidity_intelligence_summary_v1.csv'])]

def main():
    sources=['financial_stress_records_input_v1.csv','cot_historical_records_input_v1.csv','vix_historical_records_input_v1.csv','aaii_historical_records_input_v1.csv','liquidity_historical_records_input_v1.csv']
    provenance={'recomputed_from_synchronized_inputs':True,'source_files':{},'analysis_code':{}}
    for n in sources:provenance['source_files'][n]=hashlib.sha256((ROOT/n).read_bytes()).hexdigest()
    for script,outputs in STAGES:
        env=os.environ.copy()
        if script=='liquidity_intelligence_analyzer_v1.py':
            env.update(LIQUIDITY_INPUT_FILE=str(ROOT/'liquidity_historical_records_input_v1.csv'),LIQUIDITY_OUTPUT_FILE=str(ROOT/outputs[0]),LIQUIDITY_SUMMARY_FILE=str(ROOT/outputs[1]))
        subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,env=env,check=True)
        provenance['analysis_code'][script]=hashlib.sha256((ROOT/script).read_bytes()).hexdigest()
        for n in outputs:shutil.copy2(ROOT/n,ROOT/'public_data'/n)
    (ROOT/'public_data/build_provenance_v1.json').write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
