"""
Inferencia: usa el modelo ACTIVO para pronosticar los proximos meses y guarda el resultado en
ml.forecast_sales con version del modelo, fecha de prediccion y horizonte.
Se puede programar (cron / Programador de tareas) o llamar desde el pipeline.
Uso:   python machine-learning/predict_forecast.py [meses]      (por defecto 3)
Repetirlo el mismo dia no duplica filas.
"""
import sys
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "etl"))
sys.path.insert(0, str(HERE))

from extract_to_raw import make_engine   # noqa: E402
from forecast_lib import forecast   # noqa: E402
from train_forecast import load_series   # noqa: E402


def main(horizon: int = 3):
    engine = make_engine("AnalyticsDW")
    with engine.connect() as c:
        row = c.execute(text("SELECT TOP 1 model_version, model_path FROM ml.model_registry "
                             "WHERE is_active = 1 ORDER BY trained_at DESC")).fetchone()
    if not row:
        sys.exit("No hay modelo activo. Ejecuta primero: python machine-learning/train_forecast.py")
    version, path = row
    bundle = joblib.load(ROOT / path)
    series = load_series(engine)
    fc = forecast(bundle["model"], bundle["start_month"], bundle["harmonics"], series.index[-1],
                  horizon, bundle["rmse_test"])
    with engine.begin() as c:
        c.execute(text("DELETE FROM ml.forecast_sales WHERE model_version = :v "
                       "AND CAST(prediction_date AS DATE) = CAST(SYSDATETIME() AS DATE)"), {"v": version})
        c.execute(text("""INSERT INTO ml.forecast_sales
                          (model_version, horizon_months, target_month, predicted_net_sales, lower_80, upper_80)
                          VALUES (:v, :h, :m, :p, :lo, :up)"""),
                  [{"v": version, "h": int(r.horizon_months), "m": r.target_month.date(),
                    "p": round(float(r.predicted_net_sales), 2), "lo": round(float(r.lower_80), 2),
                    "up": round(float(r.upper_80), 2)} for r in fc.itertuples()])
    print(f"Modelo {version} | ultimo mes real: {series.index[-1]:%Y-%m} | PREDICCION:")
    print(fc.assign(target_month=fc["target_month"].dt.strftime("%Y-%m")).round(0).to_string(index=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
