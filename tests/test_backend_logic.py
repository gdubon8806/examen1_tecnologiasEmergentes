"""Pruebas de la logica del backend que NO necesitan base de datos ni servidor.
Ejecutar:  python tests/test_backend_logic.py"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import queries as q  # noqa: E402
from backend.app.security import make_token, same_text, verify_token  # noqa: E402


def test_sin_filtros_no_hay_where():
    where, params = q.build_where({})
    assert where == "" and params == {}


def test_filtros_son_parametros_no_texto_en_el_sql():
    f = {"date_from": date(2016, 1, 1), "date_to": date(2016, 3, 31),
         "category": "Novelty Shop'; DROP TABLE dw.FactSales;--"}
    where, params = q.build_where(f)
    assert "DROP" not in where and ":category" in where          # el valor va como parametro
    assert params["category"].startswith("Novelty Shop")
    assert "d.[Date] >= :date_from" in where and "d.[Date] <= :date_to" in where


def test_dimension_fuera_de_lista_blanca_se_rechaza():
    try:
        q.dimension_query("CustomerName; DROP TABLE x", {})
        assert False, "debio fallar"
    except ValueError:
        pass
    sql, params = q.dimension_query("product_group", {}, limit=9999)
    assert "p.ProductGroup" in sql and params["n"] == 50          # limite maximo


def test_paginacion_con_limites():
    _, params = q.detail_query({}, page=3, page_size=15)
    assert params["offset"] == 30 and params["limit"] == 15
    _, params = q.detail_query({}, page=0, page_size=10000)
    assert params["offset"] == 0 and params["limit"] == 100


def test_periodo_anterior_misma_duracion():
    pf, pt = q.previous_period(date(2016, 1, 1), date(2016, 3, 31))   # 91 dias
    assert pt == date(2015, 12, 31) and (pt - pf).days + 1 == 91
    pf, pt = q.previous_period(date(2015, 6, 1), date(2016, 5, 31))   # 366 dias
    assert pt == date(2015, 5, 31) and (pt - pf).days + 1 == 366


def test_kpis_y_variacion():
    k = q.shape_kpis({"net_sales": 1000, "orders": 4, "units": 10, "customers": 2})
    assert k["avg_ticket"] == 250.0
    assert q.shape_kpis({})["avg_ticket"] == 0.0                   # periodo sin datos
    assert q.pct_change(110, 100) == 10.0 and q.pct_change(5, 0) is None


def test_token_valido_manipulado_y_expirado():
    t = make_token("admin", "secreto", ttl=60, now=1000)
    assert verify_token(t, "secreto", now=1010) == "admin"
    assert verify_token(t, "otro-secreto", now=1010) is None        # firma distinta
    assert verify_token(t + "x", "secreto", now=1010) is None       # manipulado
    assert verify_token(t, "secreto", now=2000) is None             # expirado
    assert verify_token("basura", "secreto") is None
    assert same_text("contraseña", "contraseña") and not same_text("a", "b")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK  ", name)
    print("Todas las pruebas pasaron")
