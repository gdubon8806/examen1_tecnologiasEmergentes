"""
ETL paso 2: raw -> clean. Aplica las reglas de etl/cleaning_rules.py, manda los registros
rechazados a audit.quarantine y registra cada tabla en audit.etl_run.
Es re-ejecutable (idempotente): reemplaza las tablas clean y la cuarentena de cada tabla.
Uso:  python etl/clean_raw_to_clean.py
"""
import sys
import uuid
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from cleaning_rules import CONFIG, Quarantine, clean_table
from extract_to_raw import make_engine, text_dtypes

PIPELINE = "raw_to_clean"


def audit_start(dst, run_id, name):
    with dst.begin() as c:
        c.execute(text("""INSERT INTO audit.etl_run
                          (execution_id, pipeline_name, source_object, target_object)
                          VALUES (:id, :p, :s, :t)"""),
                  {"id": run_id, "p": PIPELINE, "s": f"raw.{name}", "t": f"clean.{name}"})


def audit_end(dst, run_id, status, read=None, inserted=None, rejected=None, error=None):
    with dst.begin() as c:
        c.execute(text("""UPDATE audit.etl_run
                          SET end_time = SYSDATETIME(), status = :st, rows_read = :r,
                              rows_inserted = :i, rows_rejected = :j, error_detail = :e
                          WHERE execution_id = :id"""),
                  {"st": status, "r": read, "i": inserted, "j": rejected, "e": error, "id": run_id})


def save_quarantine(dst, frame):
    if frame.empty:
        return
    rows = [{"eid": r.execution_id, "src": r.source_object, "bk": r.business_key,
             "rule": r.failed_rule, "js": r.record_json} for r in frame.itertuples()]
    with dst.begin() as c:
        c.execute(text("""INSERT INTO audit.quarantine
                          (execution_id, source_object, business_key, failed_rule, record_json)
                          VALUES (CAST(:eid AS UNIQUEIDENTIFIER), :src, :bk, :rule, :js)"""), rows)


def main():
    dst = make_engine("AnalyticsDW")
    refs, all_ok = {}, True
    print("Limpieza raw -> clean")
    for cfg in CONFIG:
        name, run_id = cfg["name"], str(uuid.uuid4())
        audit_start(dst, run_id, name)
        try:
            raw = pd.read_sql(text(f"SELECT * FROM raw.{name}"), dst)
            raw = raw.rename(columns={"_execution_id": "_raw_execution_id",
                                      "_loaded_at": "_raw_loaded_at"})   # linaje
            with dst.begin() as c:
                c.execute(text("DELETE FROM audit.quarantine WHERE source_object = :s"),
                          {"s": f"raw.{name}"})
            q = Quarantine(run_id, f"raw.{name}")
            clean = clean_table(cfg, raw, refs, q)
            clean["_clean_execution_id"] = run_id
            clean["_cleaned_at"] = datetime.now()
            clean.to_sql(name, dst, schema="clean", if_exists="replace", index=False,
                         chunksize=5000, dtype=text_dtypes(clean))
            save_quarantine(dst, q.frame())
            refs[name] = set(clean[cfg["key"]].dropna().astype(int).tolist())
            audit_end(dst, run_id, "SUCCESS", len(raw), len(clean), q.count)
            check = "" if len(raw) == len(clean) + q.count else "  <-- NO CUADRA"
            print(f"  OK   clean.{name:<26} leidas {len(raw):>7} -> limpias {len(clean):>7}"
                  f" | cuarentena {q.count:>5}{check}")
        except Exception as exc:  # noqa: BLE001
            audit_end(dst, run_id, "FAILED", error=str(exc)[:4000])
            print(f"  FAIL {name}: {exc}")
            all_ok = False
            break          # las tablas siguientes dependen de esta
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
