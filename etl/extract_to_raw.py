"""
ETL paso 1: extrae tablas de WideWorldImporters (origen) hacia AnalyticsDW.raw.
- Carga completa (inicial) de cada tabla.
- Cada tabla queda registrada en audit.etl_run (conteos, estado, errores).
- Se seleccionan columnas explícitas: las columnas geography/foto no se pueden
  leer con pandas y no las necesitamos.
Uso (desde la carpeta data-platform, con el entorno virtual activo):
    python etl/extract_to_raw.py
"""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.types import NVARCHAR

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = os.getenv("MSSQL_HOST", "localhost")
PORT = os.getenv("MSSQL_PORT", "1434")
PASSWORD = os.environ["MSSQL_SA_PASSWORD"]
PIPELINE = "extract_to_raw"

# nombre en raw -> consulta al origen
TABLES = {
    "orders": """SELECT OrderID, CustomerID, SalespersonPersonID, PickedByPersonID,
                 ContactPersonID, BackorderOrderID, OrderDate, ExpectedDeliveryDate,
                 CustomerPurchaseOrderNumber, IsUndersupplyBackordered,
                 PickingCompletedWhen, LastEditedBy, LastEditedWhen
                 FROM Sales.Orders""",
    "order_lines": """SELECT OrderLineID, OrderID, StockItemID, Description, PackageTypeID,
                 Quantity, UnitPrice, TaxRate, PickedQuantity, PickingCompletedWhen,
                 LastEditedBy, LastEditedWhen
                 FROM Sales.OrderLines""",
    "customers": """SELECT CustomerID, CustomerName, BillToCustomerID, CustomerCategoryID,
                 BuyingGroupID, DeliveryCityID, CreditLimit, AccountOpenedDate,
                 StandardDiscountPercentage, IsOnCreditHold, PaymentDays,
                 DeliveryPostalCode
                 FROM Sales.Customers""",
    "customer_categories": """SELECT CustomerCategoryID, CustomerCategoryName
                 FROM Sales.CustomerCategories""",
    "stock_items": """SELECT StockItemID, StockItemName, SupplierID, ColorID, Brand, Size,
                 UnitPackageID, TaxRate, UnitPrice, RecommendedRetailPrice,
                 TypicalWeightPerUnit
                 FROM Warehouse.StockItems""",
    "stock_groups": """SELECT StockGroupID, StockGroupName
                 FROM Warehouse.StockGroups""",
    "stock_item_stock_groups": """SELECT StockItemStockGroupID, StockItemID, StockGroupID
                 FROM Warehouse.StockItemStockGroups""",
    "cities": """SELECT CityID, CityName, StateProvinceID, LatestRecordedPopulation
                 FROM Application.Cities""",
    "state_provinces": """SELECT StateProvinceID, StateProvinceCode, StateProvinceName,
                 CountryID, SalesTerritory
                 FROM Application.StateProvinces""",
    "countries": """SELECT CountryID, CountryName, Continent, Region, Subregion
                 FROM Application.Countries""",
}


def make_engine(database: str):
    odbc = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={HOST},{PORT};DATABASE={database};"
        f"UID=sa;PWD={{{PASSWORD}}};TrustServerCertificate=yes"
    )
    url = URL.create("mssql+pyodbc", query={"odbc_connect": odbc})
    return create_engine(url, fast_executemany=True)


def text_dtypes(df):
    """Columnas de texto -> NVARCHAR(MAX) (conserva acentos). Fechas/numeros no se tocan."""
    cols = {}
    for c in df.columns:
        s = df[c]
        if (pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)
                or pd.api.types.is_datetime64_any_dtype(s)):
            continue
        vals = s.dropna()
        if len(vals) and vals.map(lambda v: isinstance(v, str)).all():
            cols[c] = NVARCHAR()
    return cols


def audit_start(dst, run_id, name, source_sql):
    with dst.begin() as c:
        c.execute(
            text("""INSERT INTO audit.etl_run
                    (execution_id, pipeline_name, source_object, target_object)
                    VALUES (:id, :p, :s, :t)"""),
            {"id": run_id, "p": PIPELINE,
             "s": source_sql.split("FROM")[-1].strip(), "t": f"raw.{name}"},
        )


def audit_end(dst, run_id, status, rows=None, error=None):
    with dst.begin() as c:
        c.execute(
            text("""UPDATE audit.etl_run
                    SET end_time = SYSDATETIME(), status = :st, rows_read = :r,
                        rows_inserted = :r, error_detail = :e
                    WHERE execution_id = :id"""),
            {"st": status, "r": rows, "e": error, "id": run_id},
        )


def load_table(src, dst, name, source_sql):
    run_id = str(uuid.uuid4())
    audit_start(dst, run_id, name, source_sql)
    try:
        df = pd.read_sql(text(source_sql), src)
        df["_execution_id"] = run_id          # linaje: qué ejecución trajo la fila
        df["_loaded_at"] = datetime.now()
        df.to_sql(name, dst, schema="raw", if_exists="replace",
                  index=False, chunksize=5000, dtype=text_dtypes(df))
        audit_end(dst, run_id, "SUCCESS", rows=len(df))
        print(f"  OK   raw.{name:<26} {len(df):>8} filas")
        return True
    except Exception as exc:  # noqa: BLE001
        audit_end(dst, run_id, "FAILED", error=str(exc)[:4000])
        print(f"  FAIL raw.{name}: {exc}")
        return False


def main():
    src = make_engine("WideWorldImporters")
    dst = make_engine("AnalyticsDW")
    print("Extrayendo WideWorldImporters -> AnalyticsDW.raw")
    results = [load_table(src, dst, n, q) for n, q in TABLES.items()]
    if not all(results):
        sys.exit(1)
    print("Extracción completa.")


if __name__ == "__main__":
    main()
