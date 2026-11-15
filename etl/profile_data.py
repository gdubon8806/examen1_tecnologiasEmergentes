"""
Perfilado de datos (data profiling): nulos, distintos, mínimo y máximo por columna.
Guarda el resultado en audit.data_profile y en documentation/quality/profile_<capa>.csv
Uso:  python etl/profile_data.py raw      (antes de limpiar)
      python etl/profile_data.py clean    (después de limpiar)
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from extract_to_raw import make_engine, text_dtypes


def main(layer):
    dst = make_engine("AnalyticsDW")
    tables = pd.read_sql(
        text("""SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :s AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"""),
        dst, params={"s": layer})["TABLE_NAME"].tolist()
    if not tables:
        sys.exit(f"No hay tablas en el esquema {layer}")

    rows = []
    for t in tables:
        df = pd.read_sql(text(f"SELECT * FROM {layer}.{t}"), dst)
        n = len(df)
        for col in df.columns:
            if col.startswith("_"):
                continue
            s = df[col]
            try:
                mn, mx = str(s.min()), str(s.max())
            except TypeError:
                mn = mx = None
            nulls = int(s.isna().sum())
            rows.append({"layer": layer, "table_name": t, "column_name": col,
                         "data_type": str(s.dtype), "total_rows": n, "null_count": nulls,
                         "null_pct": round(100 * nulls / n, 2) if n else 0,
                         "distinct_values": int(s.nunique(dropna=True)),
                         "min_value": mn, "max_value": mx})
        print(f"  perfilada {layer}.{t} ({n} filas)")

    prof = pd.DataFrame(rows)
    with dst.begin() as c:
        c.execute(text("IF OBJECT_ID('audit.data_profile') IS NOT NULL "
                       "DELETE FROM audit.data_profile WHERE layer = :l"), {"l": layer})
    prof.to_sql("data_profile", dst, schema="audit", if_exists="append", index=False,
                dtype=text_dtypes(prof))
    out = Path(__file__).resolve().parent.parent / "documentation" / "quality"
    out.mkdir(parents=True, exist_ok=True)
    prof.to_csv(out / f"profile_{layer}.csv", index=False, encoding="utf-8-sig")
    con_nulos = prof[prof.null_count > 0]
    print(f"\nColumnas con nulos en {layer}: {len(con_nulos)}")
    print(con_nulos[["table_name", "column_name", "null_count", "null_pct"]].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "raw")
