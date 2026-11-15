"""Pruebas de las reglas de alerta (sin base de datos). Ejecutar: python tests/test_alert_rules.py"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notifications"))
import alert_rules as R  # noqa: E402


def serie(values):
    return pd.Series(values, index=pd.date_range("2016-01-01", periods=len(values), freq="MS"), dtype=float)


def test_condicion_falsa_no_dispara():
    a = R.evaluate_sales_drop(serie([100, 100, 100, 95]), "2016-04-01", 15)
    assert a["triggered"] is False and a["change_pct"] == -5.0


def test_condicion_verdadera_dispara_con_todos_los_campos():
    a = R.evaluate_sales_drop(serie([100, 100, 100, 80]), "2016-04-01", 15)
    assert a["triggered"] and a["change_pct"] == -20.0 and a["severity"] == "MEDIA"
    for k in ("rule_code", "source_type", "indicator", "entity", "period_label", "reference_label",
              "observed_value", "reference_value", "threshold_pct", "explanation", "recommended_action"):
        assert a[k] not in (None, "")
    assert a["source_type"] == "RULE" and not a["is_simulated"]


def test_justo_en_el_umbral_si_dispara_y_severidad_alta():
    assert R.evaluate_sales_drop(serie([100, 100, 100, 85]), "2016-04-01", 15)["triggered"]
    assert R.evaluate_sales_drop(serie([100, 100, 100, 60]), "2016-04-01", 15)["severity"] == "ALTA"


def test_sin_referencia_suficiente():
    assert R.evaluate_sales_drop(serie([100, 100, 50]), "2016-03-01", 15) is None


def test_mismo_evento_misma_clave_no_duplica():
    s = serie([100, 100, 100, 80])
    assert R.evaluate_sales_drop(s, "2016-04-01", 15)["event_key"] == R.evaluate_sales_drop(s, "2016-04-01", 15)["event_key"]


def test_simulacion_se_identifica_claramente():
    a = R.evaluate_sales_drop(serie([100, 100, 100, 100]), "2016-04-01", 15, simulate_drop_pct=30)
    assert a["triggered"] and a["is_simulated"] and a["event_key"].endswith("|SIM")
    assert "SIMULADO" in a["explanation"]


def test_alerta_basada_en_prediccion():
    s = serie([100, 100, 100])
    a = R.evaluate_forecast_drop(s, "2016-04-01", 70, "modelo_x", 15)
    assert a["triggered"] and a["source_type"] == "ML" and a["model_version"] == "modelo_x"
    assert "PREDICCION" in a["explanation"] and a["event_key"] == "FORECAST_DROP|modelo_x|2016-04"
    assert R.evaluate_forecast_drop(s, "2016-04-01", 99, "modelo_x", 15)["triggered"] is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK  ", name)
    print("Todas las pruebas pasaron")
