"""
Verificacion de PUNTA A PUNTA contra tu base real (origen -> staging -> DW -> ML -> alertas -> API).
Requiere SQL Server arriba y el pipeline ya ejecutado.   Uso:  python tests/e2e_check.py
Genera documentation/tests/e2e_results.md
"""
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "etl"))
from extract_to_raw import make_engine   # noqa: E402

engine = make_engine("AnalyticsDW")
results = []


def scalar(sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def check(name, fn):
    try:
        status, detail = fn()
    except Exception as exc:  # noqa: BLE001
        status, detail = "FALLA", f"{type(exc).__name__}: {str(exc)[:160]}"
    results.append((name, status, detail))
    print(f"{status:<6} {name} - {detail}")


def counts():
    src = scalar("SELECT COUNT(*) FROM WideWorldImporters.Sales.OrderLines")
    dw = scalar("SELECT COUNT(*) FROM dw.FactSales")
    q = scalar("SELECT COUNT(*) FROM audit.quarantine WHERE source_object = 'raw.order_lines'")
    return ("PASA" if src == dw + q else "FALLA"), f"origen {src:,} = dw {dw:,} + cuarentena {q:,} (diferencia {src - dw - q})"


def totals():
    s = float(scalar("SELECT SUM(CAST(Quantity AS DECIMAL(18,2)) * UnitPrice) FROM WideWorldImporters.Sales.OrderLines") or 0)
    d = float(scalar("SELECT SUM(NetAmount) FROM dw.FactSales") or 0)
    q = scalar("SELECT COUNT(*) FROM audit.quarantine WHERE source_object = 'raw.order_lines'")
    ok = abs(s - d) < 0.01
    return ("PASA" if ok else ("AVISO" if q else "FALLA")), f"ventas netas origen {s:,.2f} vs dw {d:,.2f}" + ("" if ok or not q else " (hay filas en cuarentena)")


def no_dupes():
    n, d = scalar("SELECT COUNT(*) FROM dw.FactSales"), scalar("SELECT COUNT(DISTINCT OrderLineID) FROM dw.FactSales")
    return ("PASA" if n == d else "FALLA"), f"{n:,} filas, {d:,} líneas distintas"


def unknown_keys():
    n = scalar("SELECT COUNT(*) FROM dw.FactSales WHERE CustomerKey = -1 OR ProductKey = -1")
    return ("PASA" if n == 0 else "AVISO"), f"{n} hechos con cliente/producto desconocido"


def scd2():
    bad = scalar("SELECT COUNT(*) FROM (SELECT CustomerID FROM dw.DimCustomer WHERE IsCurrent = 1 GROUP BY CustomerID HAVING COUNT(*) > 1) x")
    hist = scalar("SELECT COUNT(*) FROM (SELECT CustomerID FROM dw.DimCustomer GROUP BY CustomerID HAVING COUNT(*) > 1) x")
    return ("PASA" if bad == 0 else "FALLA"), f"clientes con 2+ versiones vigentes: {bad}; clientes con historial (SCD2): {hist}"


def last_runs():
    rows = None
    with engine.connect() as c:
        rows = c.execute(text("""SELECT pipeline_name, status FROM (
                 SELECT pipeline_name, status, ROW_NUMBER() OVER (PARTITION BY pipeline_name, target_object ORDER BY start_time DESC) rn
                 FROM audit.etl_run) t WHERE rn = 1""")).fetchall()
    bad = [r[0] for r in rows if r[1] != "SUCCESS"]
    return ("PASA" if rows and not bad else "FALLA"), f"{len(rows)} procesos; última ejecución fallida en: {', '.join(bad) or 'ninguno'}"


def watermark():
    v = scalar("SELECT last_watermark FROM audit.etl_watermark WHERE pipeline_name = 'load_fact_sales'")
    return ("PASA" if v else "FALLA"), f"watermark de FactSales: {v}"


def ml():
    m = scalar("SELECT TOP 1 model_version FROM ml.model_registry WHERE is_active = 1")
    f = scalar("SELECT COUNT(*) FROM ml.forecast_sales") if m else 0
    return ("PASA" if m and f else "FALLA"), f"modelo activo: {m}; predicciones guardadas: {f}"


def alerts():
    n = scalar("SELECT COUNT(*) FROM alerts.alert")
    d = scalar("SELECT COUNT(*) FROM alerts.delivery")
    return ("PASA" if n else "AVISO"), f"{n} alertas, {d} entregas registradas"


def assistant_log():
    return "PASA", f"{scalar('SELECT COUNT(*) FROM ai.assistant_log')} consultas registradas"


def freshness():
    age = scalar("SELECT DATEDIFF(MINUTE, MAX(end_time), SYSDATETIME()) FROM audit.etl_run WHERE pipeline_name = 'load_fact_sales' AND status = 'SUCCESS'")
    return "INFO", f"última carga exitosa hace {age} minutos (oportunidad de los datos)"


def api():
    try:
        with urllib.request.urlopen("http://localhost:8000/api/health", timeout=5) as r:
            return ("PASA" if b"ok" in r.read() else "FALLA"), "API responde y alcanza la base de datos"
    except Exception:  # noqa: BLE001
        return "OMITIDA", "el servidor no está corriendo (arráncalo para esta comprobación)"


CHECKS = [("Conteo de filas: origen = DW + cuarentena", counts), ("Ventas netas: origen vs DW", totals),
          ("Sin duplicados en FactSales", no_dupes), ("Hechos con dimensión desconocida", unknown_keys),
          ("SCD Tipo 2: una sola versión vigente por cliente", scd2), ("Última ejecución de cada proceso exitosa", last_runs),
          ("Watermark de la carga incremental", watermark), ("Modelo de ML activo y predicciones", ml),
          ("Alertas y entregas registradas", alerts), ("Registro de consultas del asistente", assistant_log),
          ("Oportunidad de los datos", freshness), ("API en línea (opcional)", api)]

if __name__ == "__main__":
    for name, fn in CHECKS:
        check(name, fn)
    out = ROOT / "documentation" / "tests"
    out.mkdir(parents=True, exist_ok=True)
    md = ["# Verificación de punta a punta", "", f"Ejecutado: {datetime.now():%Y-%m-%d %H:%M}", "",
          "| Comprobación | Resultado | Detalle |", "|---|---|---|"] + [f"| {n} | {s} | {d} |" for n, s, d in results]
    (out / "e2e_results.md").write_text("\n".join(md), encoding="utf-8")
    fails = sum(1 for _, s, _ in results if s == "FALLA")
    print(f"\n{len(results) - fails}/{len(results)} sin fallas. Reporte: documentation/tests/e2e_results.md")
    sys.exit(1 if fails else 0)
