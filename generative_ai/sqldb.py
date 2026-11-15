"""Adaptador minimo de base de datos para las herramientas (permite sustituirlo en las pruebas)."""
from sqlalchemy import text


class SqlDb:
    def __init__(self, engine):
        self.engine = engine

    def run(self, sql: str, params: dict | None = None) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]

    def one(self, sql: str, params: dict | None = None) -> dict:
        rows = self.run(sql, params)
        return rows[0] if rows else {}
