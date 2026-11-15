"""
Crea el usuario de SOLO LECTURA que usa la API (principio de minimo privilegio).
Lee API_DB_USER y API_DB_PASSWORD del archivo .env.   Uso:  python etl/create_api_user.py
"""
import os
import re
import sys

from extract_to_raw import make_engine   # carga el .env

USER = os.getenv("API_DB_USER", "api_reader")
PASSWORD = os.getenv("API_DB_PASSWORD", "")

if not re.fullmatch(r"\w+", USER):
    sys.exit("API_DB_USER solo puede tener letras, numeros y guion bajo")
if not PASSWORD or "'" in PASSWORD:
    sys.exit("Define API_DB_PASSWORD en .env (sin comillas simples)")

STATEMENTS = [
    f"IF SUSER_ID('{USER}') IS NULL CREATE LOGIN [{USER}] WITH PASSWORD = N'{PASSWORD}'; "
    f"ELSE ALTER LOGIN [{USER}] WITH PASSWORD = N'{PASSWORD}';",
    f"IF DATABASE_PRINCIPAL_ID('{USER}') IS NULL CREATE USER [{USER}] FOR LOGIN [{USER}];",
    f"GRANT SELECT ON SCHEMA::dw TO [{USER}];",
    f"GRANT SELECT ON audit.etl_run TO [{USER}];",
    f"GRANT SELECT ON audit.etl_watermark TO [{USER}];",
    f"IF SCHEMA_ID('ml') IS NOT NULL GRANT SELECT ON SCHEMA::ml TO [{USER}];",
    f"IF OBJECT_ID('ai.assistant_log') IS NOT NULL GRANT INSERT ON ai.assistant_log TO [{USER}];",
    f"IF OBJECT_ID('alerts.alert') IS NOT NULL BEGIN GRANT SELECT ON SCHEMA::alerts TO [{USER}]; "
    f"GRANT UPDATE (status, updated_at, updated_by) ON alerts.alert TO [{USER}]; END",
]

if __name__ == "__main__":
    engine = make_engine("AnalyticsDW")
    with engine.begin() as conn:
        for s in STATEMENTS:
            conn.exec_driver_sql(s)
    print(f"Usuario '{USER}' listo: solo SELECT sobre dw.* y las tablas de monitoreo.")
