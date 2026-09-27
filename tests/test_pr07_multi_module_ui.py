from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")


def test_pr07_pages_are_wired():
    for name, fn in [
        ("Financial Stress", "financial_stress"),
        ("Liquidity", "liquidity"),
        ("Sentiment", "sentiment"),
        ("Technical Intelligence", "technical"),
        ("Market Breadth", "breadth"),
        ("Cross-Asset", "cross_asset"),
    ]:
        assert f'"{name}": {fn}' in APP


def test_pr07_preserves_research_boundaries():
    assert "No liquidity score is invented" in APP
    assert "pit_perfect = FALSE" in APP
    assert "No composite risk score is fabricated" in APP
    assert "No forecast, trading signal, or execution" in APP
