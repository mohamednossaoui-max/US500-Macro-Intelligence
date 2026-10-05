"""Production context cannot adopt tomorrow's technical availability date."""
import ast
import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def resolve(monkeypatch, value=None):
    if value is None:
        monkeypatch.delenv('RESEARCH_CONTEXT_AS_OF_DATE', raising=False)
    else:
        monkeypatch.setenv('RESEARCH_CONTEXT_AS_OF_DATE', value)
    tree = ast.parse((ROOT/'research-context-v1.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('fail', 'get_as_of_date')]
    namespace = {'pd': pd, 'os': os}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'cutoff', 'exec'), namespace)
    return namespace['get_as_of_date']()


def test_default_utc_cutoff_excludes_next_day_availability(monkeypatch):
    cutoff = resolve(monkeypatch)
    today = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    assert cutoff == today
    available = pd.Series([today-pd.Timedelta(days=1), today, today+pd.Timedelta(days=1)])
    assert available[available <= cutoff].tolist() == available.iloc[:2].tolist()
    assert available.iloc[2] == today+pd.Timedelta(days=1)


def test_historical_cutoff_preserved(monkeypatch):
    assert resolve(monkeypatch, '2020-01-02') == pd.Timestamp('2020-01-02')


def test_future_override_rejected(monkeypatch):
    future = (pd.Timestamp.now(tz='UTC')+pd.Timedelta(days=2)).date().isoformat()
    with pytest.raises(RuntimeError, match='future'):
        resolve(monkeypatch, future)


def test_invalid_override_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match='Invalid'):
        resolve(monkeypatch, 'invalid')


def test_timezone_override_converted_to_utc(monkeypatch):
    assert resolve(monkeypatch, '2020-01-02T01:00:00+02:00') == pd.Timestamp('2020-01-01')


def test_real_builder_excludes_unavailable_technical_row(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import sys

    today = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    macro = pd.read_csv(ROOT/'public_data/macro_context_v1.csv').tail(1).copy()
    macro['context_date'] = today.date().isoformat()
    sentiment = pd.read_csv(ROOT/'public_data/sentiment_engine_research_v1.csv').tail(1).copy()
    sentiment['asof_date'] = today.date().isoformat()
    prior = pd.read_csv(ROOT/'public_data/technical_intelligence_research_v1.csv').tail(1).copy()
    prior['observation_date'] = (today-pd.Timedelta(days=1)).date().isoformat()
    prior['availability_date'] = today.date().isoformat()
    future = prior.copy()
    future['observation_date'] = today.date().isoformat()
    future['availability_date'] = (today+pd.Timedelta(days=1)).date().isoformat()
    future['Close'] = 999999
    technical = pd.concat([prior, future], ignore_index=True)
    env = dict(os.environ)
    env.pop('RESEARCH_CONTEXT_AS_OF_DATE', None)
    for name, data in [('MACRO_CONTEXT_FILE', macro), ('SENTIMENT_ENGINE_FILE', sentiment),
                       ('TECHNICAL_INTELLIGENCE_FILE', technical)]:
        path = tmp_path/(name+'.csv')
        data.to_csv(path, index=False)
        env[name] = str(path)
    script = tmp_path/'research-context-v1.py'
    shutil.copy2(ROOT/script.name, script)
    result = subprocess.run([sys.executable, str(script)], env=env, cwd=tmp_path,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout+result.stderr
    context = pd.read_csv(tmp_path/'research_context_v1.csv')
    assert pd.to_datetime(context.context_date).max() == today
    assert (context.technical_Close != 999999).all()
    assert context.iloc[-1].technical_Close == prior.iloc[0].Close
    assert pd.to_datetime(context.technical_availability_date).max() <= today
    # Availability in the original source is retained; it was never backdated.
    source = pd.read_csv(env['TECHNICAL_INTELLIGENCE_FILE'])
    assert source.iloc[-1].availability_date == (today+pd.Timedelta(days=1)).date().isoformat()
