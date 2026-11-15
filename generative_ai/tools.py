"""
Herramientas analiticas APROBADAS del asistente. El modelo de lenguaje NO ejecuta SQL: solo puede
pedir una de estas herramientas con parametros validados; cada una usa consultas parametrizadas
sobre el Data Warehouse (las mismas del dashboard).
"""
import re
import unicodedata
from datetime import date, timedelta

import pandas as pd

from backend.app import queries as q

RELEVANT_DROP_PCT = 5.0      # "disminucion relevante" = caida de mas de 5 %
DIMENSION_LABELS = {"product_group": "grupo de producto", "customer_category": "categoría de cliente",
                    "territory": "territorio de ventas", "customer": "cliente"}
KPI_DEFS = {
    "net_sales": {"name": "Ventas netas", "words": ["ventas netas", "ventas", "ingresos"],
                  "definition": "Importe vendido sin impuestos.", "formula": "Suma de (cantidad × precio unitario)",
                  "source": "dw.FactSales.NetAmount"},
    "orders": {"name": "Órdenes", "words": ["ordenes", "pedidos"], "definition": "Cantidad de órdenes distintas.",
               "formula": "Conteo distinto de OrderID", "source": "dw.FactSales.OrderID"},
    "units": {"name": "Unidades vendidas", "words": ["unidades"], "definition": "Total de unidades vendidas.",
              "formula": "Suma de Quantity", "source": "dw.FactSales.Quantity"},
    "avg_ticket": {"name": "Ticket promedio por orden", "words": ["ticket"],
                   "definition": "Ventas netas promedio de cada orden.", "formula": "Ventas netas ÷ órdenes",
                   "source": "dw.FactSales (NetAmount y OrderID)"},
    "customers": {"name": "Clientes activos", "words": ["clientes activos"],
                  "definition": "Clientes distintos con al menos una compra en el periodo.",
                  "formula": "Conteo distinto de CustomerID", "source": "dw.FactSales + dw.DimCustomer"},
}


class UnknownEntity(Exception):
    """El usuario nombro un valor (territorio, categoria...) que no existe en los datos."""


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", str(text).lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ---------------- periodos ----------------
def _month_end(d: date) -> date:
    return (pd.Timestamp(d) + pd.offsets.MonthEnd(0)).date()


def _add_months(d: date, n: int) -> date:
    return (pd.Timestamp(d) + pd.DateOffset(months=n)).date()


def last_complete_month_end(data_max: date, tol: int = 3) -> date:
    me = _month_end(data_max)
    if data_max >= me - timedelta(days=tol):
        return me
    return _month_end(date(data_max.year, data_max.month, 1) - timedelta(days=1))


def resolve_period(spec: str, data_min: date, data_max: date):
    """Devuelve (desde, hasta, etiqueta). 'Ultimo' se refiere al ultimo periodo COMPLETO de los datos."""
    spec = (spec or "last_12_months").strip()
    end = last_complete_month_end(data_max)
    if spec == "all":
        return data_min, data_max, "todo el historial"
    if spec == "last_month":
        return end.replace(day=1), end, f"{end:%Y-%m}"
    if spec == "last_quarter":
        qm = end.month if end.month % 3 == 0 else end.month - end.month % 3
        y = end.year
        if qm == 0:
            qm, y = 12, y - 1
        return date(y, qm - 2, 1), _month_end(date(y, qm, 1)), f"{y}-Q{qm // 3}"
    if spec == "last_12_months":
        start = _add_months(end.replace(day=1), -11)
        return start, end, f"últimos 12 meses ({start:%Y-%m} a {end:%Y-%m})"
    if re.fullmatch(r"\d{4}", spec):
        y = int(spec)
        return date(y, 1, 1), date(y, 12, 31), spec
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", spec):
        y, m = int(spec[:4]), int(spec[5:])
        return date(y, m, 1), _month_end(date(y, m, 1)), spec
    m = re.fullmatch(r"(\d{4})-Q([1-4])", spec)
    if m:
        y, n = int(m.group(1)), int(m.group(2))
        return date(y, 3 * n - 2, 1), _month_end(date(y, 3 * n, 1)), spec
    raise ValueError(f"Periodo no valido: {spec}")


def previous_range(d_from: date, d_to: date):
    n = (d_to.year - d_from.year) * 12 + d_to.month - d_from.month + 1
    return _add_months(d_from, -n), d_from - timedelta(days=1)


def _period(params, ctx, default):
    spec = params.get("period") or default
    d_from, d_to, label = resolve_period(spec, ctx["data_min"], ctx["data_max"])
    return {"spec": spec, "date_from": d_from, "date_to": d_to, "label": label, "partial": d_to > ctx["data_max"]}


def _pub(p):
    return {"label": p["label"], "date_from": p["date_from"].isoformat(), "date_to": p["date_to"].isoformat(),
            "partial": p["partial"]}


def _outside(p, ctx):
    return p["date_to"] < ctx["data_min"] or p["date_from"] > ctx["data_max"]


def _f(p, params, **over):
    return {"date_from": p["date_from"], "date_to": p["date_to"], "category": params.get("category"),
            "product_group": params.get("product_group"), "territory": params.get("territory"), **over}


def _active_filters(params):
    return {k: params[k] for k in ("category", "product_group", "territory") if params.get(k)}


def _result(tool, title, p=None, params=None, kind="fact"):
    return {"tool": tool, "title": title, "kind": kind, "period": _pub(p) if p else None,
            "filters": _active_filters(params or {}), "empty": False, "data": {}}


def _dim_map(db, dimension, f):
    rows = db.run(*q.dimension_query(dimension, f, 50))
    return {r["label"]: float(r["sales"] or 0) for r in rows}


# ---------------- herramientas ----------------
def sales_summary(params, ctx):
    p = _period(params, ctx, "last_12_months")
    res = _result("sales_summary", "Resumen de ventas", p, params)
    if _outside(p, ctx):
        res["empty"] = True
        return res
    cur = q.shape_kpis(ctx["db"].one(*q.kpi_query(_f(p, params))))
    if cur["orders"] == 0:
        res["empty"] = True
        return res
    data = {"current": cur, "previous": None, "previous_period": None, "delta_pct": {}}
    if p["spec"] != "all":
        pf, pt = previous_range(p["date_from"], p["date_to"])
        prev = q.shape_kpis(ctx["db"].one(*q.kpi_query(_f(p, params, date_from=pf, date_to=pt))))
        if prev["orders"] > 0:
            data.update(previous=prev, previous_period={"date_from": pf.isoformat(), "date_to": pt.isoformat()},
                        delta_pct={k: q.pct_change(cur[k], prev[k]) for k in cur})
    res["data"] = data
    return res


def sales_by_dimension(params, ctx):
    p = _period(params, ctx, "last_12_months")
    dim, limit = params["dimension"], params.get("limit", 5)
    res = _result("sales_by_dimension", f"Ventas por {DIMENSION_LABELS[dim]}", p, params)
    res["dimension"] = dim
    if _outside(p, ctx):
        res["empty"] = True
        return res
    db = ctx["db"]
    rows = db.run(*q.dimension_query(dim, _f(p, params), limit))
    if not rows:
        res["empty"] = True
        return res
    total = q.shape_kpis(db.one(*q.kpi_query(_f(p, params))))["net_sales"]
    prev = {}
    if p["spec"] != "all":
        pf, pt = previous_range(p["date_from"], p["date_to"])
        prev = _dim_map(db, dim, _f(p, params, date_from=pf, date_to=pt))
    out = []
    for r in rows:
        s = float(r["sales"] or 0)
        out.append({"label": r["label"], "sales": s, "units": int(r["units"] or 0),
                    "share_pct": round(s / total * 100, 1) if total else None,
                    "growth_pct": q.pct_change(s, prev[r["label"]]) if prev.get(r["label"]) else None})
    res["data"] = {"rows": out, "total_sales": total}
    return res


def dimension_growth(params, ctx):
    p = _period(params, ctx, "last_quarter")
    dim, limit = params["dimension"], params.get("limit", 3)
    res = _result("dimension_growth", f"Crecimiento por {DIMENSION_LABELS[dim]}", p, params)
    res["dimension"] = dim
    if _outside(p, ctx) or p["spec"] == "all":
        res["empty"] = True
        return res
    db = ctx["db"]
    pf, pt = previous_range(p["date_from"], p["date_to"])
    cur = _dim_map(db, dim, _f(p, params))
    prev = _dim_map(db, dim, _f(p, params, date_from=pf, date_to=pt))
    rows = []
    for label, s_prev in prev.items():
        if s_prev > 0:
            s_cur = cur.get(label, 0.0)
            rows.append({"label": label, "sales": s_cur, "prev_sales": s_prev,
                         "growth_pct": round((s_cur - s_prev) / s_prev * 100, 1)})
    if not rows or not cur:
        res["empty"] = True
        return res
    tc, tp = sum(cur.values()), sum(prev.values())
    res["data"] = {
        "up": sorted([r for r in rows if r["growth_pct"] > 0], key=lambda r: -r["growth_pct"])[:limit],
        "down": sorted([r for r in rows if r["growth_pct"] <= -RELEVANT_DROP_PCT], key=lambda r: r["growth_pct"])[:limit],
        "total_current": tc, "total_previous": tp, "total_growth_pct": q.pct_change(tc, tp),
        "relevant_drop_pct": RELEVANT_DROP_PCT,
        "previous_period": {"date_from": pf.isoformat(), "date_to": pt.isoformat()}}
    return res


def monthly_trend(params, ctx):
    p = _period(params, ctx, "last_12_months")
    res = _result("monthly_trend", "Tendencia mensual de ventas", p, params)
    if _outside(p, ctx):
        res["empty"] = True
        return res
    rows = ctx["db"].run(*q.trend_query(_f(p, params)))
    if not rows:
        res["empty"] = True
        return res
    months = [{"ym": r["ym"], "sales": float(r["sales"] or 0)} for r in rows]
    res["data"] = {"months": months, "best": max(months, key=lambda m: m["sales"]),
                   "worst": min(months, key=lambda m: m["sales"]), "first": months[0], "last": months[-1]}
    return res


def forecast_info(params, ctx):
    res = _result("forecast_info", "Predicción de ventas (modelo de ML)", kind="prediction")
    db = ctx["db"]
    try:
        m = db.one("""SELECT TOP 1 model_version, trained_at, trained_through, mae_test, mape_test, baseline_name,
                             baseline_mape_test FROM ml.model_registry WHERE is_active = 1 ORDER BY trained_at DESC""")
        if not m:
            res["empty"] = True
            return res
        fc = db.run("""SELECT target_month, predicted_net_sales, lower_80, upper_80, prediction_date
                       FROM ml.forecast_sales WHERE model_version = :v AND prediction_date =
                       (SELECT MAX(prediction_date) FROM ml.forecast_sales WHERE model_version = :v)
                       ORDER BY target_month""", {"v": m["model_version"]})
    except Exception:  # noqa: BLE001
        res["empty"] = True
        return res
    if not fc:
        res["empty"] = True
        return res
    res["data"] = {"model": {k: (str(v) if not isinstance(v, (int, float, type(None))) else v) for k, v in m.items()},
                   "forecast": [{"ym": str(r["target_month"])[:7], "predicted": float(r["predicted_net_sales"]),
                                 "lower": float(r["lower_80"]), "upper": float(r["upper_80"])} for r in fc]}
    return res


def open_alerts(params, ctx):
    res = _result("open_alerts", "Alertas")
    db = ctx["db"]
    try:
        counts = {r["status"]: int(r["n"]) for r in db.run("SELECT status, COUNT(*) AS n FROM alerts.alert GROUP BY status")}
        latest = db.run("""SELECT TOP 5 alert_id, severity, indicator, period_label, change_pct, is_simulated
                           FROM alerts.alert WHERE status = N'NUEVA' ORDER BY created_at DESC""")
    except Exception:  # noqa: BLE001
        counts, latest = {}, []
    if not counts:
        res["empty"] = True
        return res
    res["data"] = {"counts": counts, "latest_new": [{**r, "change_pct": float(r["change_pct"]), "is_simulated": bool(r["is_simulated"])} for r in latest]}
    return res


def data_status(params, ctx):
    res = _result("data_status", "Estado de los datos")
    last = ctx.get("last_update")
    res["data"] = {"last_update": str(last) if last else None, "data_min": ctx["data_min"].isoformat(),
                   "data_max": ctx["data_max"].isoformat()}
    return res


def kpi_definition(params, ctx):
    kpi = params["kpi"]
    d = KPI_DEFS[kpi]
    res = _result("kpi_definition", f"Definición: {d['name']}")
    sample = sales_summary({"period": "last_month"}, ctx)
    res["data"] = {"kpi": kpi, **{k: d[k] for k in ("name", "definition", "formula", "source")},
                   "sample_period": sample["period"], "sample_value": None if sample["empty"] else sample["data"]["current"][kpi]}
    return res


def suggest_analysis(params, ctx):
    res = _result("suggest_analysis", "Análisis sugeridos")
    res["data"] = {"items": [
        "Comparar el crecimiento de cada grupo de producto contra el mismo periodo del año anterior.",
        "Revisar qué clientes dejaron de comprar en los últimos 3 meses (riesgo de abandono).",
        "Analizar la concentración de ventas: qué porcentaje aporta el top 10 de clientes.",
        "Medir la estacionalidad por territorio para ajustar compras e inventario.",
        "Evaluar el error del modelo de predicción mes a mes y reentrenarlo cuando haya datos nuevos."]}
    return res


TOOLS = {
    "sales_summary": (sales_summary, {"period", "category", "product_group", "territory"}),
    "sales_by_dimension": (sales_by_dimension, {"dimension", "period", "limit", "category", "product_group", "territory"}),
    "dimension_growth": (dimension_growth, {"dimension", "period", "limit", "category", "product_group", "territory"}),
    "monthly_trend": (monthly_trend, {"period", "category", "product_group", "territory"}),
    "forecast_info": (forecast_info, set()),
    "open_alerts": (open_alerts, set()),
    "data_status": (data_status, set()),
    "kpi_definition": (kpi_definition, {"kpi"}),
    "suggest_analysis": (suggest_analysis, set()),
}
FILTER_LABEL = {"category": "categoría de cliente", "product_group": "grupo de producto", "territory": "territorio"}
FILTER_META = {"category": "categories", "product_group": "product_groups", "territory": "territories"}


def validate_call(call: dict, meta: dict) -> dict:
    """Valida una llamada a herramienta (venga de reglas o del modelo). Rechaza todo lo que no este aprobado."""
    if not isinstance(call, dict) or call.get("tool") not in TOOLS:
        raise ValueError("Herramienta no permitida")
    tool = call["tool"]
    allowed = TOOLS[tool][1]
    raw = call.get("params") or {}
    if not isinstance(raw, dict):
        raise ValueError("Parametros invalidos")
    params = {k: v for k, v in raw.items() if k in allowed and v not in (None, "")}   # descarta lo desconocido
    if "period" in params:
        resolve_period(str(params["period"]), meta["data_min"], meta["data_max"])    # ValueError si no es valido
        params["period"] = str(params["period"])
    if tool in ("sales_by_dimension", "dimension_growth"):
        if params.get("dimension") not in DIMENSION_LABELS:
            raise ValueError("Dimension no permitida")
        default = 5 if tool == "sales_by_dimension" else 3
        try:
            params["limit"] = max(1, min(int(params.get("limit", default)), 10))
        except (TypeError, ValueError):
            params["limit"] = default
    if tool == "kpi_definition" and params.get("kpi") not in KPI_DEFS:
        raise ValueError("Indicador no reconocido")
    for key, meta_key in FILTER_META.items():
        if key in params:
            match = {norm(v): v for v in meta[meta_key]}.get(norm(params[key]))
            if not match:
                raise UnknownEntity(f"No existe «{params[key]}» entre los valores de {FILTER_LABEL[key]} de los datos.")
            params[key] = match
    return {"tool": tool, "params": params, "assumed_period": bool(call.get("assumed_period"))}


def load_meta(db) -> dict:
    rng = db.one("""SELECT MIN(d.[Date]) AS date_min, MAX(d.[Date]) AS date_max
                    FROM dw.FactSales f JOIN dw.DimDate d ON d.DateKey = f.DateKey""")
    last = db.one("""SELECT TOP 1 end_time FROM audit.etl_run
                     WHERE pipeline_name = 'load_fact_sales' AND status = 'SUCCESS' ORDER BY end_time DESC""")
    vals = lambda sql: [r["v"] for r in db.run(sql)]  # noqa: E731
    return {"data_min": rng["date_min"], "data_max": rng["date_max"], "last_update": last.get("end_time"),
            "categories": vals("SELECT DISTINCT CustomerCategory AS v FROM dw.DimCustomer WHERE CustomerKey <> -1 ORDER BY 1"),
            "product_groups": vals("SELECT DISTINCT ProductGroup AS v FROM dw.DimProduct WHERE ProductKey <> -1 ORDER BY 1"),
            "territories": vals("SELECT DISTINCT SalesTerritory AS v FROM dw.DimCustomer WHERE CustomerKey <> -1 ORDER BY 1")}
