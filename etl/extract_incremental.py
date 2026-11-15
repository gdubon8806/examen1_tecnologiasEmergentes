"""
Extraccion INCREMENTAL hacia raw.
- orders y order_lines: solo filas con LastEditedWhen >= watermark - 1 dia (ventana de solapamiento).
  Las filas nuevas se insertan y las modificadas reemplazan a la anterior (upsert por clave),
  todo en UNA transaccion junto con el avance del watermark: si algo falla, no se mueve nada.
- Catalogos (clientes, productos, ubicaciones...): son pequenos, se recargan completos.
Se puede repetir las veces que se quiera sin duplicar (idempotente).
Uso:  python etl/extract_incremental.py
"""
import sys
import uuid
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text

from extract_to_raw import TABLES, load_table, make_engine

PIPELINE = "extract_incremental"
OVERLAP_DAYS = 1
INCREMENTAL = {"orders": "OrderID", "order_lines": "OrderLineID"}   # tabla -> clave de negocio


def get_watermark(dst, name):
    """Watermark guardado; si no existe (primera vez) se toma el maximo ya cargado en raw."""
    with dst.connect() as c:
        row = c.execute(text("SELECT last_watermark FROM audit.etl_watermark WHERE pipeline_name = :p"),
                        {"p": f"extract_{name}"}).fetchone()
        if row:
            return row[0]
        return c.execute(text(f"SELECT MAX(LastEditedWhen) FROM raw.{name}")).scalar() \
            or datetime(1900, 1, 1)


def extract_incremental(src, dst, name, key):
    run_id = str(uuid.uuid4())
    wm_prev = get_watermark(dst, name)
    from_ = wm_prev - timedelta(days=OVERLAP_DAYS)
    with dst.begin() as c:
        c.execute(text("""INSERT INTO audit.etl_run
                          (execution_id, pipeline_name, source_object, target_object, watermark_start)
                          VALUES (:id, :p, :s, :t, :w)"""),
                  {"id": run_id, "p": PIPELINE, "s": f"Sales.{name}", "t": f"raw.{name}", "w": from_})
    ins = upd = 0
    new_wm = wm_prev
    try:
        df = pd.read_sql(text(TABLES[name] + " WHERE LastEditedWhen >= :f"), src, params={"f": from_})
        if len(df):
            df["_execution_id"] = run_id
            df["_loaded_at"] = datetime.now()
            new_wm = max(wm_prev, df["LastEditedWhen"].max().to_pydatetime())
            with dst.begin() as conn:                       # todo o nada
                before = conn.execute(text(f"SELECT COUNT(*) FROM raw.{name}")).scalar()
                conn.execute(text(f"DELETE FROM raw.{name} WHERE {key} = :k"),
                             [{"k": int(k)} for k in df[key]])
                df.to_sql(name, conn, schema="raw", if_exists="append", index=False, chunksize=5000)
                after = conn.execute(text(f"SELECT COUNT(*) FROM raw.{name}")).scalar()
                conn.execute(text("""
                    IF EXISTS (SELECT 1 FROM audit.etl_watermark WHERE pipeline_name = :p)
                        UPDATE audit.etl_watermark SET last_watermark = :w, updated_at = SYSDATETIME()
                        WHERE pipeline_name = :p
                    ELSE
                        INSERT INTO audit.etl_watermark (pipeline_name, last_watermark) VALUES (:p, :w)"""),
                    {"p": f"extract_{name}", "w": new_wm})
            ins = after - before
            upd = len(df) - ins
        with dst.begin() as c:
            c.execute(text("""UPDATE audit.etl_run SET end_time = SYSDATETIME(), status = 'SUCCESS',
                              rows_read = :r, rows_inserted = :i, rows_updated = :u, watermark_end = :w
                              WHERE execution_id = :id"""),
                      {"r": len(df), "i": ins, "u": upd, "w": new_wm, "id": run_id})
        print(f"  OK   raw.{name:<14} leidas {len(df):>6} | nuevas {ins:>5} | modificadas {upd:>5}"
              f" | watermark {wm_prev} -> {new_wm}")
        return True
    except Exception as exc:  # noqa: BLE001
        with dst.begin() as c:
            c.execute(text("""UPDATE audit.etl_run SET end_time = SYSDATETIME(), status = 'FAILED',
                              error_detail = :e WHERE execution_id = :id"""),
                      {"e": str(exc)[:4000], "id": run_id})
        print(f"  FAIL raw.{name}: {exc}")
        return False


def main():
    src, dst = make_engine("WideWorldImporters"), make_engine("AnalyticsDW")
    print("Extraccion incremental (hechos) + recarga de catalogos")
    ok = [extract_incremental(src, dst, n, k) for n, k in INCREMENTAL.items()]
    ok += [load_table(src, dst, n, q) for n, q in TABLES.items() if n not in INCREMENTAL]
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    main()
