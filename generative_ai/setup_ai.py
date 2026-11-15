"""Crea el esquema ai (registro de consultas del asistente). Uso: python generative_ai/setup_ai.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "etl"))
from extract_to_raw import make_engine   # noqa: E402
from load_dw import run_script   # noqa: E402

if __name__ == "__main__":
    run_script(make_engine("AnalyticsDW"), ROOT / "database" / "scripts" / "10_create_ai_objects.sql")
    print("Esquema ai listo (ai.assistant_log).")
