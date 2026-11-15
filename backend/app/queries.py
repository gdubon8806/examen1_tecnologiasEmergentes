"""
Consultas del dashboard. SQL SIEMPRE parametrizado (:nombre). Los nombres de columna que se
insertan en el SQL salen de listas blancas (FILTER_COLUMNS / DIMENSIONS), nunca del usuario.
No depende de FastAPI, asi que se puede probar sin servidor ni base de datos.
"""
from datetime import date, timedelta

BASE_FROM = """
FROM dw.FactSales f
JOIN dw.DimDate d     ON d.DateKey = f.DateKey
JOIN dw.DimCustomer c ON c.CustomerKey = f.CustomerKey
JOIN dw.DimProduct p  ON p.ProductKey = f.ProductKey
"""  # todos los joins son muchos-a-uno: no multiplican importes

FILTER_COLUMNS = {
    "category": "c.CustomerCategory",
    "product_group": "p.ProductGroup",
    "territory": "c.SalesTerritory",
}
DIMENSIONS = {
    "product_group": "p.ProductGroup",
    "customer_category": "c.CustomerCategory",
    "territory": "c.SalesTerritory",
    "customer": "c.CustomerName",
}
FILTER_KEYS = ("date_from", "date_to", "category", "product_group", "territory")


def build_where(f: dict):
    clauses, params = [], {}
    if f.get("date_from"):
        clauses.append("d.[Date] >= :date_from")
        params["date_from"] = f["date_from"]
    if f.get("date_to"):
        clauses.append("d.[Date] <= :date_to")
        params["date_to"] = f["date_to"]
    for key, col in FILTER_COLUMNS.items():
        if f.get(key):
            clauses.append(f"{col} = :{key}")
            params[key] = f[key]
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def kpi_query(f: dict):
    where, params = build_where(f)
    sql = f"""SELECT SUM(f.NetAmount) AS net_sales, COUNT(DISTINCT f.OrderID) AS orders,
                     SUM(f.Quantity) AS units, COUNT(DISTINCT c.CustomerID) AS customers
              {BASE_FROM} {where}"""
    return sql, params


def trend_query(f: dict):
    where, params = build_where(f)
    sql = f"""SELECT d.YearMonth AS ym, SUM(f.NetAmount) AS sales, SUM(f.Quantity) AS units
              {BASE_FROM} {where}
              GROUP BY d.[Year], d.[Month], d.YearMonth
              ORDER BY d.[Year], d.[Month]"""
    return sql, params


def dimension_query(dimension: str, f: dict, limit: int = 10):
    if dimension not in DIMENSIONS:
        raise ValueError(f"Dimension no permitida: {dimension}")
    expr = DIMENSIONS[dimension]
    where, params = build_where(f)
    params["n"] = max(1, min(int(limit), 50))
    sql = f"""SELECT TOP (:n) {expr} AS label, SUM(f.NetAmount) AS sales, SUM(f.Quantity) AS units
              {BASE_FROM} {where}
              GROUP BY {expr}
              ORDER BY SUM(f.NetAmount) DESC"""
    return sql, params


def count_query(f: dict):
    where, params = build_where(f)
    return f"SELECT COUNT(*) AS total {BASE_FROM} {where}", params


def detail_query(f: dict, page: int = 1, page_size: int = 15):
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    where, params = build_where(f)
    params["offset"] = (page - 1) * page_size
    params["limit"] = page_size
    sql = f"""SELECT f.OrderID AS order_id, f.OrderLineID AS order_line_id, d.[Date] AS order_date,
                     c.CustomerName AS customer, c.CustomerCategory AS category,
                     p.ProductName AS product, p.ProductGroup AS product_group,
                     f.Quantity AS quantity, f.UnitPrice AS unit_price, f.NetAmount AS net_amount
              {BASE_FROM} {where}
              ORDER BY d.[Date] DESC, f.OrderLineID DESC
              OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"""
    return sql, params


def previous_period(date_from: date, date_to: date):
    """Periodo anterior de la misma duracion, terminando el dia antes de date_from."""
    days = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    return prev_to - timedelta(days=days - 1), prev_to


def shape_kpis(row: dict) -> dict:
    net = float(row.get("net_sales") or 0)
    orders = int(row.get("orders") or 0)
    return {
        "net_sales": net,
        "orders": orders,
        "units": int(row.get("units") or 0),
        "customers": int(row.get("customers") or 0),
        "avg_ticket": round(net / orders, 2) if orders else 0.0,
    }


def pct_change(current: float, previous: float):
    """Variacion porcentual; None si no hay base de comparacion."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)
