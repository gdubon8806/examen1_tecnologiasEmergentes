"""
Entrena y evalua el modelo de pronostico de ventas mensuales y lo registra.
Uso (desde data-platform, con el entorno virtual activo):   python machine-learning/train_forecast.py
Genera: modelo en machine-learning/models/, registro en ml.model_registry,
        documentation/ml/experiments.csv y documentation/ml/model_report.md
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "etl"))
sys.path.insert(0, str(HERE))

from extract_to_raw import make_engine   # noqa: E402
from forecast_lib import complete_monthly_series, evaluate   # noqa: E402
from load_dw import run_script   # noqa: E402

SQL = ROOT / "database" / "scripts" / "08_create_ml_objects.sql"
DOCS = ROOT / "documentation" / "ml"


def load_series(engine):
    df = pd.read_sql(text("SELECT month_start, net_sales, last_day_with_data FROM dw.vw_monthly_sales "
                          "ORDER BY month_start"), engine)
    return complete_monthly_series(df, pd.to_datetime(df["last_day_with_data"]).max())


def write_report(res, version, series):
    DOCS.mkdir(parents=True, exist_ok=True)
    res["experiments"].to_csv(DOCS / "experiments.csv", index=False)
    t = res["test"]
    rows = "\n".join(f"| {k} | {v['mae']:,.0f} | {v['rmse']:,.0f} | {v['mape']:.1f}% |" for k, v in t.items())
    (DOCS / "model_report.md").write_text(f"""# Modelo de pronostico de ventas mensuales

- **Version:** {version}
- **Problema:** pronosticar las ventas netas mensuales (regresion sobre serie de tiempo).
- **Decision que apoya:** planificar inventario/compras y detectar caidas de ventas (alertas).
- **Datos:** `dw.vw_monthly_sales` (Data Warehouse), {len(series)} meses completos
  ({series.index[0]:%Y-%m} a {series.index[-1]:%Y-%m}). El ultimo mes se excluye si esta incompleto.
- **Algoritmo:** Ridge (regresion lineal regularizada) con tendencia + estacionalidad
  ({res['harmonics']} armonicos), alpha = {res['alpha']}. Escalador ajustado solo con entrenamiento.
- **Variables:** solo derivadas de la fecha (tendencia y senos/cosenos del mes). Sin fuga de datos.

## Division temporal (nunca aleatoria)
| Conjunto | Periodo |
|---|---|
| Entrenamiento | {res['splits']['train']} |
| Validacion (elegir hiperparametros) | {res['splits']['validation']} |
| Prueba (usada una sola vez) | {res['splits']['test']} |

## Resultados en PRUEBA (datos no usados para entrenar ni para elegir el modelo)
| Modelo / baseline | MAE | RMSE | MAPE |
|---|---|---|---|
{rows}

**Conclusion:** {res['verdict']}

## Limitaciones
- Pocos meses de historia: la estimacion es inestable y el periodo de prueba es corto (6 meses).
- Solo usa tendencia y estacionalidad: no conoce promociones, precios, inventario ni eventos externos.
- El intervalo del 80 % es aproximado (supone errores normales con la RMSE de la prueba).
- Datos de ejemplo (WideWorldImporters): sirven para demostrar el proceso, no para decisiones reales.
- Reentrenar cada vez que se carguen meses nuevos; vigilar que el error en produccion no crezca.
""", encoding="utf-8")


def main():
    engine = make_engine("AnalyticsDW")
    run_script(engine, SQL)
    series = load_series(engine)
    print(f"Serie: {len(series)} meses completos ({series.index[0]:%Y-%m} a {series.index[-1]:%Y-%m})")
    res = evaluate(series)

    version = f"sales_ridge_{datetime.now():%Y%m%d_%H%M%S}"
    model_file = HERE / "models" / f"{version}.joblib"
    model_file.parent.mkdir(exist_ok=True)
    joblib.dump({"model": res["final_model"], "start_month": res["start_month"],
                 "harmonics": res["harmonics"], "alpha": res["alpha"],
                 "rmse_test": res["test"]["modelo"]["rmse"], "version": version}, model_file)

    t = res["test"]
    base = t[res["best_baseline"]]
    detail = {"validation": res["validation"], "test": t, "splits": res["splits"],
              "verdict": res["verdict"], "best_baseline": res["best_baseline"],
              "experiments_top5": res["experiments"].head(5).to_dict("records")}
    with engine.begin() as c:
        c.execute(text("UPDATE ml.model_registry SET is_active = 0"))
        c.execute(text("""INSERT INTO ml.model_registry
            (model_version, algorithm, target, trained_through, n_months, harmonics, alpha,
             mae_test, rmse_test, mape_test, baseline_name, baseline_mae_test, baseline_rmse_test,
             baseline_mape_test, metrics_json, model_path, is_active)
            VALUES (:v, 'Ridge (tendencia + estacionalidad)', 'ventas netas mensuales', :thr, :n, :h, :a,
                    :mae, :rmse, :mape, :bn, :bmae, :brmse, :bmape, :js, :path, 1)"""),
                  {"v": version, "thr": series.index[-1].date(), "n": len(series), "h": res["harmonics"],
                   "a": res["alpha"], "mae": t["modelo"]["mae"], "rmse": t["modelo"]["rmse"],
                   "mape": t["modelo"]["mape"], "bn": res["best_baseline"], "bmae": base["mae"],
                   "brmse": base["rmse"], "bmape": base["mape"],
                   "js": json.dumps(detail, default=float),
                   "path": str(model_file.relative_to(ROOT)).replace("\\", "/")})
    write_report(res, version, series)

    print(f"\nModelo {version}: harmonicos={res['harmonics']} alpha={res['alpha']}")
    print(f"Division: train {res['splits']['train']} | val {res['splits']['validation']} | test {res['splits']['test']}")
    print("\nResultados en PRUEBA:")
    print(pd.DataFrame(t).T.rename(columns=str.upper).round(1).to_string())
    print("\n" + res["verdict"])
    print("Documentos: documentation/ml/model_report.md y experiments.csv")


if __name__ == "__main__":
    main()
