"""Conexion de SOLO LECTURA al Data Warehouse (usuario api_reader, nunca 'sa')."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@lru_cache(maxsize=1)
def get_engine():
    host = os.getenv("MSSQL_HOST", "localhost")
    port = os.getenv("MSSQL_PORT", "1434")
    user = os.getenv("API_DB_USER", "api_reader")
    password = os.environ["API_DB_PASSWORD"]
    odbc = ("DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={host},{port};DATABASE=AnalyticsDW;UID={user};PWD={{{password}}};"
            "TrustServerCertificate=yes")
    return create_engine(URL.create("mssql+pyodbc", query={"odbc_connect": odbc}),
                         pool_pre_ping=True, pool_size=5)
