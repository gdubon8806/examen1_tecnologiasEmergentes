"""
Planificador: convierte la pregunta en llamadas a herramientas APROBADAS.
- rule_plan : por reglas y palabras clave (siempre disponible, determinista).
- llm_plan  : opcional, pide al modelo un JSON; luego tools.validate_call lo valida estrictamente.
"""
import json
import re

from .tools import DIMENSION_LABELS, KPI_DEFS, norm

MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
ORD = {"primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4}

HELP = ("Puedo responder con los datos del Data Warehouse sobre: ventas por periodo, comparaciones con el periodo "
        "anterior, crecimiento o caída por grupo de producto, categoría de cliente o territorio, tendencia mensual, "
        "predicción de ventas, alertas y estado de los datos. Ejemplos: «¿Cuáles fueron las ventas del último "
        "trimestre?», «¿Qué territorios presentan una disminución relevante?».")


def detect_period(nq: str):
    y = re.search(r"\b(19\d{2}|20\d{2})\b", nq)
    if y:
        year = y.group(1)
        m = re.search(r"\bq([1-4])\b", nq)
        if m:
            return f"{year}-Q{m.group(1)}"
        m = re.search(r"\b(primer|primero|segundo|tercer|tercero|cuarto)\s+trimestre\b", nq)
        if m:
            return f"{year}-Q{ORD[m.group(1)]}"
        for name, n in MONTHS.items():
            if re.search(rf"\b{name}\b", nq):
                return f"{year}-{n:02d}"
        return year
    if re.search(r"ultimo trimestre|trimestre pasado|trimestre anterior|ultimo cuarto", nq):
        return "last_quarter"
    if re.search(r"ultimo mes|mes pasado|mes anterior", nq):
        return "last_month"
    if re.search(r"ultimos 12 meses|ultimos doce meses|ultimo ano", nq):
        return "last_12_months"
    if re.search(r"historico|todo el tiempo|desde el inicio", nq):
        return "all"
    return None


def detect_dimension(nq: str):
    if re.search(r"categorias? de clientes?|tipos? de clientes?|segmento", nq):
        return "customer_category"
    if re.search(r"region|territorio|zona", nq):
        return "territory"
    if re.search(r"grupos?|categoria|producto|linea", nq):
        return "product_group"
    if re.search(r"cliente", nq) and not re.search(r"clientes activos", nq):
        return "customer"
    return None


def detect_kpi(nq: str):
    for kpi in ("avg_ticket", "customers", "orders", "units", "net_sales"):
        if any(w in nq for w in KPI_DEFS[kpi]["words"]):
            return kpi
    return None


def detect_filters(nq: str, meta: dict) -> dict:
    out = {}
    for key, meta_key in (("category", "categories"), ("product_group", "product_groups"), ("territory", "territories")):
        for v in meta[meta_key]:
            if len(norm(v)) >= 4 and norm(v) in nq:
                out[key] = v
    return out


def detect_limit(nq: str):
    m = re.search(r"\b(?:top\s*)?(\d{1,2})\s+(?:grupos|categorias|productos|clientes|regiones|territorios|mejores)", nq) \
        or re.search(r"\btop\s*(\d{1,2})\b", nq)
    return int(m.group(1)) if m else None


def rule_plan(question: str, meta: dict) -> dict:
    nq = norm(question)
    has = lambda *pats: any(re.search(p, nq) for p in pats)  # noqa: E731
    plan = {"calls": [], "reason": None, "message": None}

    # Entidad inexistente nombrada por el usuario (p. ej. «territorio Atlantis»)
    m = re.search(r"(?:territorio|region|región)\s+([A-ZÁÉÍÓÚÑ][\w-]*(?:\s+[A-ZÁÉÍÓÚÑ][\w-]*)*)", question)
    if m:
        known = {norm(v) for v in meta["territories"]}
        if norm(m.group(1)) not in known:
            plan.update(reason="unknown_entity",
                        message=f"No existe el territorio «{m.group(1)}» en los datos. Territorios disponibles: "
                                + ", ".join(meta["territories"]) + ".")
            return plan

    filters = detect_filters(nq, meta)
    period = detect_period(nq)

    def call(tool, params, default_period=None):
        p = {**filters, **params}
        assumed = False
        if "period" not in p:
            p["period"] = period or default_period
            assumed = period is None
        return {"tool": tool, "params": p, "assumed_period": assumed}

    dim = detect_dimension(nq)
    if has(r"alerta"):
        plan["calls"] = [call("open_alerts", {})]
    elif has(r"prediccion|predic|pronostic|proyeccion|proximo mes|proximos meses|se espera"):
        plan["calls"] = [call("forecast_info", {})]
    elif has(r"actualizad|ultima carga|frescura|datos al dia|cuando se cargo"):
        plan["calls"] = [call("data_status", {})]
    elif has(r"explica|\bque es\b|define|como se calcula|que significa"):
        kpi = detect_kpi(nq)
        if kpi:
            plan["calls"] = [call("kpi_definition", {"kpi": kpi})]
        else:
            plan.update(reason="ambiguous", message="¿Qué indicador quieres que explique? Por ejemplo: ventas netas, órdenes, unidades, ticket promedio o clientes activos.")
    elif has(r"analisis adicional", r"que mas (?:analizar|revisar)", r"convendria", r"recomiend"):
        plan["calls"] = [call("suggest_analysis", {})]
    elif has(r"crecimiento|crecieron|crecio|aumento|aumentaron|disminu|caida|cayeron|cayo|bajaron|descenso|decrec"):
        plan["calls"] = [call("dimension_growth", {"dimension": dim if dim not in (None, "customer") else "product_group"}, "last_quarter")]
    elif has(r"principales cambios|resume|resumen|cambios respecto|periodo anterior|comparad"):
        plan["calls"] = [call("sales_summary", {}, "last_quarter"), call("dimension_growth", {"dimension": "product_group"}, "last_quarter")]
    elif has(r"tendencia|evolucion|mensual|por mes|mes a mes"):
        plan["calls"] = [call("monthly_trend", {}, "last_12_months")]
    elif dim and has(r"mas vendid", r"\btop\b", r"mejores", r"principales", r"mayores", r"ranking", r"\bpor (?:categoria|grupo|region|territorio|producto|cliente)"):
        params = {"dimension": dim}
        lim = detect_limit(nq)
        if lim:
            params["limit"] = lim
        plan["calls"] = [call("sales_by_dimension", params, "last_12_months")]
    elif has(r"ventas|vendimos|vendido|ingresos|facturacion|ordenes|pedidos|unidades|clientes activos|ticket"):
        plan["calls"] = [call("sales_summary", {}, "last_12_months")]
    else:
        plan.update(reason="out_of_scope", message="Esa pregunta está fuera de lo que puedo responder con los datos disponibles. " + HELP)
    return plan


# ---------------- planificador con modelo de lenguaje (opcional) ----------------
PLANNER_SYSTEM = """Eres el planificador de un asistente analitico de ventas. Convierte la pregunta del usuario en JSON.
Responde SOLO con JSON: {"calls":[{"tool":"...","params":{...}}]}  (maximo 2 llamadas) o {"calls":[],"reason":"fuera_de_alcance"}.
Herramientas:
- sales_summary(period?, category?, product_group?, territory?): ventas, ordenes, unidades, clientes y comparacion con el periodo anterior.
- sales_by_dimension(dimension, period?, limit?, filtros?): ranking de ventas por dimension.
- dimension_growth(dimension, period?, limit?, filtros?): que crecio y que cayo frente al periodo anterior.
- monthly_trend(period?, filtros?): ventas por mes.
- forecast_info(): prediccion de ventas de los proximos meses.
- open_alerts(): alertas. data_status(): actualizacion de datos. suggest_analysis(): analisis recomendados.
- kpi_definition(kpi): kpi en {net_sales, orders, units, avg_ticket, customers}.
dimension en {product_group (categoria/grupo de producto), customer_category (categoria de cliente), territory (region/territorio), customer}.
period: last_month | last_quarter | last_12_months | all | YYYY | YYYY-MM | YYYY-Qn.  "ultimo" = ultimo periodo completo de los datos.
Nunca generes SQL. Si la pregunta no trata de ventas, clientes, productos, predicciones o alertas, responde fuera_de_alcance."""


def llm_plan(provider, question: str, meta: dict):
    ctx = (f"Datos disponibles: {meta['data_min']} a {meta['data_max']}. Categorias de cliente: {meta['categories']}. "
           f"Grupos de producto: {meta['product_groups']}. Territorios: {meta['territories']}.\nPregunta: {question}")
    raw = provider.chat(PLANNER_SYSTEM, ctx, json_mode=True, max_tokens=300)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("El modelo no devolvio JSON")
    data = json.loads(m.group(0))
    calls = data.get("calls") or []
    return [{"tool": c.get("tool"), "params": c.get("params") or {}, "assumed_period": "period" not in (c.get("params") or {})}
            for c in calls[:2] if isinstance(c, dict)]
