"""
Reglas de limpieza raw -> clean. Son funciones puras (solo pandas, sin base de datos)
para poder probarlas con tests/test_cleaning_rules.py.

Cada fila rechazada va a cuarentena con la regla que falló. Todo registro leído termina
en 'clean' o en cuarentena (nada se pierde en silencio):  leídos = limpios + rechazados.
"""
import pandas as pd


class Quarantine:
    COLUMNS = ["execution_id", "source_object", "business_key", "failed_rule", "record_json"]

    def __init__(self, run_id, source):
        self.run_id, self.source = run_id, source
        self.parts, self.count = [], 0

    def reject(self, bad, key, rule):
        if len(bad) == 0:
            return
        self.count += len(bad)
        self.parts.append(pd.DataFrame({
            "execution_id": [self.run_id] * len(bad),
            "source_object": [self.source] * len(bad),
            "business_key": bad[key].astype(str).tolist(),
            "failed_rule": [rule] * len(bad),
            "record_json": [row.to_json(date_format="iso") for _, row in bad.iterrows()],
        }))

    def frame(self):
        if not self.parts:
            return pd.DataFrame(columns=self.COLUMNS)
        return pd.concat(self.parts, ignore_index=True)


# ---------- utilidades ----------
def trim_strings(df):
    """Quita espacios al inicio/fin; texto vacío -> NULL (regla documentada)."""
    df = df.copy()
    for c in df.columns:
        s = df[c]
        if c.startswith("_") or pd.api.types.is_numeric_dtype(s) \
                or pd.api.types.is_bool_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        df[c] = s.map(lambda v: (v.strip() or None) if isinstance(v, str) else v)
    return df


def keep(df, bad_mask, key, rule, q):
    """Manda a cuarentena las filas donde bad_mask es True y devuelve el resto."""
    bad_mask = pd.Series(bad_mask, index=df.index).fillna(False).astype(bool)
    q.reject(df[bad_mask], key, rule)
    return df[~bad_mask]


def dedupe(df, key, q):
    """Clave nula -> cuarentena. Duplicados: sobrevive la fila con LastEditedWhen más reciente
    (si no existe esa columna, la última). Las demás van a cuarentena, no se borran."""
    df = keep(df, df[key].isna(), key, "NULL_KEY", q)
    if "LastEditedWhen" in df.columns:
        df = df.sort_values("LastEditedWhen", kind="stable")
    return keep(df, df.duplicated(key, keep="last"), key, "DUPLICATE_KEY_SUPERSEDED", q)


# ---------- reglas específicas por tabla ----------
def _rules_customers(df, q):
    # BuyingGroupID / CreditLimit nulos = "no aplica": se conservan como NULL (no se rellenan con 0)
    return keep(df, df["CustomerName"].isna(), "CustomerID", "CUSTOMER_NAME_NULL", q)


def _rules_orders(df, q):
    order_date = pd.to_datetime(df["OrderDate"], errors="coerce")
    df = keep(df, order_date.isna(), "OrderID", "ORDER_DATE_INVALID_OR_NULL", q)
    df = df.assign(OrderDate=order_date.loc[df.index])
    expected = pd.to_datetime(df["ExpectedDeliveryDate"], errors="coerce")
    df = keep(df, expected.notna() & (expected < df["OrderDate"]),
              "OrderID", "EXPECTED_DELIVERY_BEFORE_ORDER_DATE", q)
    return df.assign(ExpectedDeliveryDate=expected.loc[df.index])


def _rules_order_lines(df, q):
    key = "OrderLineID"
    qty = pd.to_numeric(df["Quantity"], errors="coerce")
    df = keep(df, qty.isna() | (qty <= 0), key, "QUANTITY_NOT_POSITIVE", q)
    price = pd.to_numeric(df["UnitPrice"], errors="coerce")
    df = keep(df, price.isna() | (price < 0), key, "UNIT_PRICE_INVALID", q)
    tax = pd.to_numeric(df["TaxRate"], errors="coerce")
    df = keep(df, tax.isna() | (tax < 0) | (tax > 100), key, "TAX_RATE_OUT_OF_RANGE", q)

    df = df.copy()
    # PickedQuantity nulo = pendiente de preparar: se conserva NULL
    df["UnitPrice"] = pd.to_numeric(df["UnitPrice"]).round(2)
    df["LineAmount"] = (pd.to_numeric(df["Quantity"]) * df["UnitPrice"]).round(2)       # importe neto
    df["TaxAmount"] = (df["LineAmount"] * pd.to_numeric(df["TaxRate"]) / 100).round(2)
    # Outliers: se MARCAN (no se eliminan). Regla: precio > Q3 + 3*IQR
    p25, p75 = df["UnitPrice"].quantile([0.25, 0.75])
    df["IsPriceOutlier"] = df["UnitPrice"] > (p75 + 3 * (p75 - p25))
    return df


CUSTOM = {"customers": _rules_customers, "orders": _rules_orders,
          "order_lines": _rules_order_lines}

# Orden importa: primero catálogos, al final hechos (para validar llaves foráneas)
CONFIG = [
    {"name": "customer_categories", "key": "CustomerCategoryID", "ints": ["CustomerCategoryID"]},
    {"name": "countries", "key": "CountryID", "ints": ["CountryID"]},
    {"name": "state_provinces", "key": "StateProvinceID", "ints": ["StateProvinceID", "CountryID"],
     "fks": [("CountryID", "countries")]},
    {"name": "cities", "key": "CityID", "ints": ["CityID", "StateProvinceID"],
     "fks": [("StateProvinceID", "state_provinces")]},
    {"name": "stock_groups", "key": "StockGroupID", "ints": ["StockGroupID"]},
    {"name": "stock_items", "key": "StockItemID",
     "ints": ["StockItemID", "SupplierID", "ColorID", "UnitPackageID"]},
    {"name": "stock_item_stock_groups", "key": "StockItemStockGroupID",
     "ints": ["StockItemStockGroupID", "StockItemID", "StockGroupID"],
     "fks": [("StockItemID", "stock_items"), ("StockGroupID", "stock_groups")]},
    {"name": "customers", "key": "CustomerID",
     "ints": ["CustomerID", "BillToCustomerID", "CustomerCategoryID", "BuyingGroupID",
              "DeliveryCityID", "PaymentDays"],
     "fks": [("CustomerCategoryID", "customer_categories"), ("DeliveryCityID", "cities")]},
    {"name": "orders", "key": "OrderID",
     "ints": ["OrderID", "CustomerID", "SalespersonPersonID", "PickedByPersonID",
              "ContactPersonID", "BackorderOrderID"],
     "fks": [("CustomerID", "customers")]},
    {"name": "order_lines", "key": "OrderLineID",
     "ints": ["OrderLineID", "OrderID", "StockItemID", "PackageTypeID", "Quantity", "PickedQuantity"],
     "fks": [("OrderID", "orders"), ("StockItemID", "stock_items")]},
]


def clean_table(cfg, df, refs, q):
    """Aplica: trim -> duplicados -> reglas propias -> integridad referencial -> tipos."""
    key = cfg["key"]
    df = trim_strings(df)
    df = dedupe(df, key, q)
    hook = CUSTOM.get(cfg["name"])
    if hook:
        df = hook(df, q)
    for col, ref in cfg.get("fks", []):
        df = keep(df, ~df[col].isin(refs[ref]), key, f"ORPHAN_{col}_IN_{ref}", q)
    df = df.copy()
    for c in cfg.get("ints", []):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df.reset_index(drop=True)
