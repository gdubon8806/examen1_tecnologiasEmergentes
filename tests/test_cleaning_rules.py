"""Pruebas de las reglas de limpieza. Ejecutar:  python tests/test_cleaning_rules.py
(o con pytest). No necesitan base de datos."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
from cleaning_rules import CONFIG, Quarantine, clean_table  # noqa: E402

CFG = {c["name"]: c for c in CONFIG}


def rules(q):
    return q.frame()["failed_rule"].tolist()


def test_duplicados_sobrevive_el_mas_reciente():
    df = pd.DataFrame({"CustomerCategoryID": [1, 1, 2],
                       "CustomerCategoryName": ["Viejo", "Nuevo", "Otro"],
                       "LastEditedWhen": pd.to_datetime(["2020-01-01", "2021-01-01", "2020-05-05"])})
    q = Quarantine("r1", "raw.customer_categories")
    out = clean_table(CFG["customer_categories"], df, {}, q)
    assert len(out) == 2
    assert out.loc[out.CustomerCategoryID == 1, "CustomerCategoryName"].iloc[0] == "Nuevo"
    assert rules(q) == ["DUPLICATE_KEY_SUPERSEDED"]


def test_trim_y_vacio_a_null():
    df = pd.DataFrame({"CustomerCategoryID": [1, 2], "CustomerCategoryName": ["  Hola  ", "   "]})
    out = clean_table(CFG["customer_categories"], df, {}, Quarantine("r", "x"))
    assert out.CustomerCategoryName.iloc[0] == "Hola"
    assert pd.isna(out.CustomerCategoryName.iloc[1])


def _lines(**over):
    base = {"OrderLineID": [1], "OrderID": [10], "StockItemID": [5], "PackageTypeID": [7],
            "Quantity": [3], "UnitPrice": [10.0], "TaxRate": [15.0], "PickedQuantity": [None],
            "Description": ["x"]}
    base.update(over)
    return pd.DataFrame(base)


def test_linea_valida_calcula_importes_y_conserva_nulos():
    q = Quarantine("r", "raw.order_lines")
    out = clean_table(CFG["order_lines"], _lines(), {"orders": {10}, "stock_items": {5}}, q)
    assert len(out) == 1 and q.count == 0
    assert out.LineAmount.iloc[0] == 30.0 and out.TaxAmount.iloc[0] == 4.5
    assert pd.isna(out.PickedQuantity.iloc[0])          # pendiente: NO se rellena con 0


def test_cantidad_invalida_y_huerfanos_van_a_cuarentena():
    df = _lines(OrderLineID=[1, 2, 3], OrderID=[10, 10, 99], StockItemID=[5, 5, 5],
                PackageTypeID=[7, 7, 7], Quantity=[0, 2, 2], UnitPrice=[10.0] * 3,
                TaxRate=[15.0] * 3, PickedQuantity=[None] * 3, Description=["a", "b", "c"])
    q = Quarantine("r", "raw.order_lines")
    out = clean_table(CFG["order_lines"], df, {"orders": {10}, "stock_items": {5}}, q)
    assert out.OrderLineID.tolist() == [2]
    assert sorted(rules(q)) == ["ORPHAN_OrderID_IN_orders", "QUANTITY_NOT_POSITIVE"]
    assert len(out) + q.count == len(df)               # nada se pierde en silencio


def test_entrega_antes_de_pedido_se_rechaza():
    df = pd.DataFrame({"OrderID": [1, 2], "CustomerID": [1, 1],
                       "OrderDate": ["2016-01-10", "2016-01-10"],
                       "ExpectedDeliveryDate": ["2016-01-09", "2016-01-12"],
                       "SalespersonPersonID": [1, 1], "PickedByPersonID": [None, None],
                       "ContactPersonID": [1, 1], "BackorderOrderID": [None, None]})
    q = Quarantine("r", "raw.orders")
    out = clean_table(CFG["orders"], df, {"customers": {1}}, q)
    assert out.OrderID.tolist() == [2]
    assert rules(q) == ["EXPECTED_DELIVERY_BEFORE_ORDER_DATE"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK  ", name)
    print("Todas las pruebas pasaron")
