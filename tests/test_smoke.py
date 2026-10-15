"""Smoke test: the dashboard opens without errors. Run with: pytest"""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parent.parent


def test_processed_data_exists():
    assert any((ROOT / "data" / "processed").glob("*.*"))


def test_dashboard_runs_without_errors():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    assert not at.exception
