"""Pruebas del modelo de pronostico con datos sinteticos (sin base de datos).
Ejecutar:  python tests/test_forecast_lib.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "machine-learning"))
from forecast_lib import (baseline_predictions, complete_monthly_series, evaluate,  # noqa: E402
                          forecast, make_features, metrics)


def synthetic(n=42, seed=0):
    idx = pd.date_range("2013-01-01", periods=n, freq="MS")
    rng = np.random.default_rng(seed)
    y = 1_000_000 + 25_000 * np.arange(n) + 120_000 * np.sin(2 * np.pi * idx.month / 12) \
        + rng.normal(0, 15_000, n)
    return pd.Series(y, index=idx)


def test_metricas():
    m = metrics([100, 200], [110, 180])
    assert m["mae"] == 15 and abs(m["rmse"] - np.sqrt(250)) < 1e-9
    assert abs(m["mape"] - 10.0) < 1e-9


def test_variables_solo_dependen_de_la_fecha():
    idx = pd.date_range("2016-06-01", periods=3, freq="MS")
    f = make_features(idx, pd.Timestamp("2013-01-01"), 2)
    assert list(f.columns) == ["t", "sin1", "cos1", "sin2", "cos2"]
    assert f["t"].tolist() == [41.0, 42.0, 43.0]


def test_division_temporal_sin_solapes_y_en_orden():
    s = synthetic()
    r = evaluate(s)
    assert r["splits"]["train"].startswith("2013-01") and r["splits"]["test"].endswith("(6 meses)")
    assert r["splits"]["train"] == "2013-01 a 2015-06 (30 meses)"
    assert r["splits"]["validation"] == "2015-07 a 2015-12 (6 meses)"
    assert r["splits"]["test"] == "2016-01 a 2016-06 (6 meses)"          # en orden, sin solapes


def test_experimentos_y_modelo_supera_baseline_en_serie_con_tendencia():
    r = evaluate(synthetic())
    assert len(r["experiments"]) == 15
    assert r["test"]["modelo"]["mae"] < r["test"]["naive_ultimo_valor"]["mae"]
    assert r["improvement_pct"] > 0 and "mejora" in r["verdict"]


def test_se_declara_cuando_el_modelo_no_supera_al_baseline():
    s = pd.Series(np.random.default_rng(1).normal(1_000_000, 50_000, 42),
                  index=pd.date_range("2013-01-01", periods=42, freq="MS"))   # ruido puro
    r = evaluate(s)
    assert ("mejora" in r["verdict"]) or ("NO supera" in r["verdict"])         # siempre se informa


def test_serie_muy_corta_se_rechaza():
    try:
        evaluate(synthetic(20))
        assert False
    except ValueError:
        pass


def test_baseline_estacional_usa_el_mismo_mes_del_ano_anterior():
    s = synthetic(30)
    tgt = pd.date_range("2015-04-01", periods=2, freq="MS")
    b = baseline_predictions(s.iloc[:27], tgt)
    assert b["naive_estacional"].tolist() == [s["2014-04-01"], s["2014-05-01"]]
    assert (b["naive_ultimo_valor"] == s.iloc[26]).all()


def test_mes_incompleto_se_descarta_y_huecos_se_rechazan():
    df = pd.DataFrame({"month_start": pd.date_range("2016-01-01", periods=6, freq="MS"),
                       "net_sales": [1, 2, 3, 4, 5, 6.0]})
    assert len(complete_monthly_series(df, pd.Timestamp("2016-06-01"))) == 5      # junio incompleto
    assert len(complete_monthly_series(df, pd.Timestamp("2016-06-29"))) == 6      # fin de semana: ok
    try:
        complete_monthly_series(df.drop(index=2), pd.Timestamp("2016-06-30"))
        assert False
    except ValueError as e:
        assert "2016-03" in str(e)


def test_pronostico_fechas_horizonte_e_intervalo():
    s = synthetic()
    r = evaluate(s)
    fc = forecast(r["final_model"], r["start_month"], r["harmonics"], s.index[-1], 3, 20_000)
    assert fc["target_month"].dt.strftime("%Y-%m").tolist() == ["2016-07", "2016-08", "2016-09"]
    assert fc["horizon_months"].tolist() == [1, 2, 3]
    assert (fc["lower_80"] <= fc["predicted_net_sales"]).all() and (fc["upper_80"] > fc["predicted_net_sales"]).all()
    assert (fc["lower_80"] >= 0).all()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK  ", name)
    print("Todas las pruebas pasaron")
