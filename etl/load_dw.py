"""
ETL paso 3: crea el modelo dimensional y carga dimensiones y hechos desde clean.
  python etl/load_dw.py            -> crea (si falta) y carga. Se puede repetir sin duplicar.
  python etl/load_dw.py --reset    -> borra las tablas dw.* y el watermark, y recarga desde cero.
Orden: DimDate -> DimProduct -> DimCustomer -> FactSales (las claves se resuelven antes).
"""
import re
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

from extract_to_raw import make_engine

ROOT = Path(__file__).resolve().parent.parent
MODEL_SQL = ROOT / "database" / "scripts" / "03_create_dw_model.sql"

STEPS = [  # (nombre, procedimiento, origen, destino)
    ("dim_date", "dw.usp_load_dim_date", "clean.orders", "dw.DimDate"),
    ("dim_product", "dw.usp_load_dim_product", "clean.stock_items", "dw.DimProduct"),
    ("dim_customer", "dw.usp_load_dim_customer", "clean.customers", "dw.DimCustomer"),
    ("fact_sales", "dw.usp_load_fact_sales", "clean.order_lines", "dw.FactSales"),
]


def run_script(engine, path):
    sql = path.read_text(encoding="utf-8")
    batches = [b for b in re.split(r"^\s*GO\s*$", sql, flags=re.M | re.I) if b.strip()]
    with engine.begin() as conn:
        for b in batches:
            conn.exec_driver_sql(b)


def reset(engine):
    with engine.begin() as conn:
        for t in ("FactSales", "DimCustomer", "DimProduct", "DimDate"):
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS dw.{t}")
        conn.exec_driver_sql("DELETE FROM audit.etl_watermark WHERE pipeline_name = 'load_fact_sales'")
    print("  dw.* y watermark borrados")


def run_step(engine, name, proc, source, target):
    run_id = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("""INSERT INTO audit.etl_run
                          (execution_id, pipeline_name, source_object, target_object)
                          VALUES (:id, :p, :s, :t)"""),
                  {"id": run_id, "p": f"load_{name}", "s": source, "t": target})
    try:
        with engine.begin() as conn:      # una sola transaccion: todo o nada
            ins, upd, ws, we = conn.exec_driver_sql(f"EXEC {proc}").fetchone()
        status, err = "SUCCESS", None
        print(f"  OK   {target:<18} insertadas {ins:>7} | actualizadas {upd:>6}"
              + (f" | watermark {ws} -> {we}" if we else ""))
    except Exception as exc:  # noqa: BLE001
        ins = upd = ws = we = None
        status, err = "FAILED", str(exc)[:4000]
        print(f"  FAIL {target}: {exc}")
    with engine.begin() as c:
        c.execute(text("""UPDATE audit.etl_run
                          SET end_time = SYSDATETIME(), status = :st, rows_inserted = :i,
                              rows_updated = :u, watermark_start = :ws, watermark_end = :we,
                              error_detail = :e
                          WHERE execution_id = :id"""),
                  {"st": status, "i": ins, "u": upd, "ws": ws, "we": we, "e": err, "id": run_id})
    return status == "SUCCESS"


def main():
    engine = make_engine("AnalyticsDW")
    if "--reset" in sys.argv:
        reset(engine)
    print("Creando modelo dimensional (si no existe)...")
    run_script(engine, MODEL_SQL)
    print("Cargando Data Warehouse (clean -> dw)")
    for step in STEPS:
        if not run_step(engine, *step):
            sys.exit(1)
    print("Carga del DW completa.")


if __name__ == "__main__":
    main()
