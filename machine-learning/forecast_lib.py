"""
Logica del modelo de pronostico de ventas mensuales (sin base de datos: facil de probar).

Problema : predecir las ventas netas de los proximos meses.
Decision : planificar inventario/compras y detectar caidas de ventas (alertas).
Objetivo : ventas netas mensuales (suma de FactSales.NetAmount).
Variables: SOLO se derivan de la fecha (tendencia y estacionalidad). Ninguna usa ventas del
           futuro ni del periodo de prueba -> no hay fuga de datos (data leakage).
Validacion: division POR TIEMPO (entrenamiento -> validacion -> prueba), nunca al azar.
Prueba   : el conjunto de prueba se usa UNA sola vez, despues de elegir el modelo con validacion.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

Z80 = 1.2816   # z para un intervalo nominal del 80 %


# ---------- datos ----------
def complete_monthly_series(df: pd.DataFrame, max_date, tolerance_days: int = 3) -> pd.Series:
    """df: columnas month_start y net_sales. Quita el ultimo mes si esta incompleto
    (p. ej. un solo dia de datos) y exige que no falten meses intermedios."""
    s = df.assign(month_start=pd.to_datetime(df["month_start"])).set_index("month_start")["net_sales"]
    s = s.astype(float).sort_index()
    month_end = s.index[-1] + pd.offsets.MonthEnd(0)
    if pd.Timestamp(max_date) < month_end - pd.Timedelta(days=tolerance_days):
        s = s.iloc[:-1]
    full = pd.date_range(s.index[0], s.index[-1], freq="MS")
    missing = full.difference(s.index)
    if len(missing):
        raise ValueError("Faltan meses en la serie: " + ", ".join(missing.strftime("%Y-%m")))
    return s.asfreq("MS")


# ---------- variables ----------
def make_features(idx: pd.DatetimeIndex, start_month: pd.Timestamp, harmonics: int) -> pd.DataFrame:
    """Tendencia (meses desde el inicio) + estacionalidad (senos/cosenos del mes). Solo usa fechas."""
    t = (idx.year - start_month.year) * 12 + (idx.month - start_month.month)
    cols = {"t": t.astype(float)}
    for k in range(1, harmonics + 1):
        cols[f"sin{k}"] = np.sin(2 * np.pi * k * idx.month / 12)
        cols[f"cos{k}"] = np.cos(2 * np.pi * k * idx.month / 12)
    return pd.DataFrame(cols, index=idx)


def fit_model(X: pd.DataFrame, y, alpha: float) -> Pipeline:
    # El escalador se ajusta SOLO con los datos que recibe (los de entrenamiento).
    pipe = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
    return pipe.fit(X, y)


# ---------- metricas y lineas base ----------
def metrics(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    err = y_pred - y_true
    return {"mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(np.mean(err ** 2))),
            "mape": float(np.mean(np.abs(err) / np.abs(y_true)) * 100)}


def baseline_predictions(hist: pd.Series, target_idx: pd.DatetimeIndex) -> dict:
    """Pronosticos simples hechos con la historia disponible al inicio del bloque a predecir."""
    seasonal = hist.reindex(target_idx - pd.DateOffset(months=12)).to_numpy()
    if np.isnan(seasonal).any():
        raise ValueError("Historia insuficiente para el baseline estacional (se necesitan >12 meses)")
    return {
        "naive_ultimo_valor": np.full(len(target_idx), hist.iloc[-1]),
        "naive_estacional": seasonal,                       # el mismo mes del ano anterior
        "promedio_entrenamiento": np.full(len(target_idx), hist.mean()),
    }


# ---------- experimentos y evaluacion ----------
def evaluate(series: pd.Series, val_n: int = 6, test_n: int = 6,
             harmonics_grid=(0, 1, 2), alpha_grid=(0.01, 0.1, 1, 10, 100)) -> dict:
    n = len(series)
    if n < val_n + test_n + 18:
        raise ValueError(f"Serie demasiado corta ({n} meses) para entrenar, validar y probar")
    train = series.iloc[: n - val_n - test_n]
    val = series.iloc[n - val_n - test_n: n - test_n]
    test = series.iloc[n - test_n:]
    start = series.index[0]

    # 1) Experimentos: se comparan con el conjunto de VALIDACION (la prueba no se toca)
    rows = []
    for h in harmonics_grid:
        for a in alpha_grid:
            m = fit_model(make_features(train.index, start, h), train.to_numpy(), a)
            pred = m.predict(make_features(val.index, start, h))
            rows.append({"harmonics": h, "alpha": a, **metrics(val.to_numpy(), pred)})
    exp = pd.DataFrame(rows).sort_values("mae").reset_index(drop=True)
    best = exp.iloc[0]
    h_best, a_best = int(best["harmonics"]), float(best["alpha"])
    val_metrics = {"modelo": {k: float(best[k]) for k in ("mae", "rmse", "mape")}}
    for name, pred in baseline_predictions(train, val.index).items():
        val_metrics[name] = metrics(val.to_numpy(), pred)

    # 2) Prueba final (una sola vez): se reentrena con entrenamiento + validacion
    trval = pd.concat([train, val])
    m_tv = fit_model(make_features(trval.index, start, h_best), trval.to_numpy(), a_best)
    test_pred = m_tv.predict(make_features(test.index, start, h_best))
    test_metrics = {"modelo": metrics(test.to_numpy(), test_pred)}
    for name, pred in baseline_predictions(trval, test.index).items():
        test_metrics[name] = metrics(test.to_numpy(), pred)

    best_base = min((k for k in test_metrics if k != "modelo"), key=lambda k: test_metrics[k]["mae"])
    gain = (test_metrics[best_base]["mae"] - test_metrics["modelo"]["mae"]) / test_metrics[best_base]["mae"] * 100
    verdict = (f"El modelo mejora al mejor baseline ({best_base}) en {gain:.1f}% de MAE en la prueba."
               if gain > 0 else
               f"El modelo NO supera al mejor baseline ({best_base}) en la prueba ({gain:.1f}% de MAE). "
               "Con tan pocos meses, un baseline simple puede ser mejor opcion.")

    # 3) Modelo final: se reentrena con TODOS los meses completos para pronosticar el futuro
    final = fit_model(make_features(series.index, start, h_best), series.to_numpy(), a_best)

    fmt = lambda s: f"{s.index[0]:%Y-%m} a {s.index[-1]:%Y-%m} ({len(s)} meses)"  # noqa: E731
    return {"experiments": exp, "harmonics": h_best, "alpha": a_best, "validation": val_metrics,
            "test": test_metrics, "best_baseline": best_base, "improvement_pct": float(gain),
            "verdict": verdict, "final_model": final, "start_month": start,
            "splits": {"train": fmt(train), "validation": fmt(val), "test": fmt(test)},
            "test_pred": pd.Series(test_pred, index=test.index)}


# ---------- pronostico ----------
def forecast(model, start_month, harmonics: int, last_month, horizon: int, rmse: float) -> pd.DataFrame:
    idx = pd.date_range(pd.Timestamp(last_month) + pd.DateOffset(months=1), periods=horizon, freq="MS")
    pred = model.predict(make_features(idx, pd.Timestamp(start_month), harmonics))
    pred = np.maximum(pred, 0)
    return pd.DataFrame({"horizon_months": np.arange(1, horizon + 1), "target_month": idx,
                         "predicted_net_sales": pred,
                         "lower_80": np.maximum(pred - Z80 * rmse, 0),   # intervalo APROXIMADO
                         "upper_80": pred + Z80 * rmse})
