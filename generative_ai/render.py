"""Redaccion DETERMINISTA de los hechos consultados (la parte que nunca inventa el modelo)."""


def usd(v):
    return f"${v:,.0f}"


def pct(v):
    return "sin base de comparación" if v is None else f"{v:+.1f}%"


def _filters(r):
    f = r.get("filters") or {}
    return " (" + ", ".join(f"{k}: {v}" for k, v in f.items()) + ")" if f else ""


def describe(r: dict) -> list[str]:
    t, d = r["tool"], r["data"]
    per = r["period"]["label"] if r.get("period") else ""
    if t == "sales_summary":
        c = d["current"]
        line = f"Ventas netas {per}{_filters(r)}: {usd(c['net_sales'])}"
        if d["previous"]:
            pp = d["previous_period"]
            line += (f" ({pct(d['delta_pct']['net_sales'])} frente al periodo anterior "
                     f"{pp['date_from']} a {pp['date_to']}: {usd(d['previous']['net_sales'])})")
        return [line + ".", f"Órdenes: {c['orders']:,}; unidades: {c['units']:,}; clientes activos: {c['customers']:,}; "
                            f"ticket promedio: ${c['avg_ticket']:,.2f}."]
    if t == "sales_by_dimension":
        out = [f"Ventas por {r['title'].split('por ')[-1]} en {per}{_filters(r)}:"]
        for i, x in enumerate(d["rows"], 1):
            g = f", {pct(x['growth_pct'])} vs periodo anterior" if x["growth_pct"] is not None else ""
            out.append(f"{i}. {x['label']}: {usd(x['sales'])} ({x['share_pct']}% del total{g}).")
        return out
    if t == "dimension_growth":
        pp = d["previous_period"]
        out = [f"{r['title']} en {per} frente a {pp['date_from']} a {pp['date_to']}{_filters(r)}: "
               f"ventas totales {usd(d['total_current'])} ({pct(d['total_growth_pct'])})."]
        out.append("Mayor crecimiento: " + ("; ".join(f"{x['label']} ({pct(x['growth_pct'])}, {usd(x['sales'])})" for x in d["up"]) or "ninguno") + ".")
        out.append(f"Disminuciones relevantes (caída de más de {d['relevant_drop_pct']:g}%): " +
                   ("; ".join(f"{x['label']} ({pct(x['growth_pct'])}, {usd(x['sales'])})" for x in d["down"]) or "ninguna") + ".")
        return out
    if t == "monthly_trend":
        return [f"Tendencia mensual {per}{_filters(r)}: {len(d['months'])} meses; primero {d['first']['ym']} "
                f"({usd(d['first']['sales'])}), último {d['last']['ym']} ({usd(d['last']['sales'])}).",
                f"Mejor mes: {d['best']['ym']} ({usd(d['best']['sales'])}). Peor mes: {d['worst']['ym']} ({usd(d['worst']['sales'])})."]
    if t == "forecast_info":
        m = d["model"]
        out = [f"PREDICCIÓN (no es dato histórico) del modelo {m['model_version']}, entrenado con datos hasta {m['trained_through']}:"]
        out += [f"{x['ym']}: {usd(x['predicted'])} (rango aproximado 80%: {usd(x['lower'])} a {usd(x['upper'])})." for x in d["forecast"]]
        if m.get("mae_test") is not None:
            out.append(f"Error medio del modelo en datos de prueba: {usd(m['mae_test'])} (MAPE {m['mape_test']:.1f}%).")
        return out
    if t == "open_alerts":
        out = ["Alertas por estado: " + ", ".join(f"{k}: {v}" for k, v in d["counts"].items()) + "."]
        out += [f"Alerta #{a['alert_id']} [{a['severity']}] {a['indicator']} {a['period_label']}: {a['change_pct']:+.1f}%"
                + (" (SIMULADA)" if a["is_simulated"] else "") + "." for a in d["latest_new"]]
        return out
    if t == "data_status":
        return [f"Última carga exitosa del Data Warehouse: {d['last_update'] or 'sin registro'}.",
                f"Los datos de ventas cubren de {d['data_min']} a {d['data_max']}."]
    if t == "kpi_definition":
        out = [f"{d['name']}: {d['definition']} Fórmula: {d['formula']}. Fuente: {d['source']}."]
        if d["sample_value"] is not None:
            v = d["sample_value"]
            out.append(f"Valor en {d['sample_period']['label']}: " + (usd(v) if d["kpi"] in ("net_sales", "avg_ticket") else f"{v:,.0f}") + ".")
        return out
    if t == "suggest_analysis":
        return ["Análisis sugeridos (recomendaciones, no datos):"] + [f"- {x}" for x in d["items"]]
    return []


def template_answer(results: list[dict], facts: list[str]) -> str:
    """Respuesta SIN modelo de lenguaje: las primeras lineas de hechos."""
    return " ".join(facts[:2]) if facts else ""
