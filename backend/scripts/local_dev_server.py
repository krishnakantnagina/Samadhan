"""Run the real backend against a PRIVATE local Postgres instead of the live Supabase. For testing only; never touches the live server.

    # one-time: start the private database and load schema + seeds + migrations (see scripts/local_dev_db.py)
    python scripts/local_dev_db.py setup
    # then, from backend/:
    uv run --env-file ../.env --with "psycopg[binary]" python scripts/local_dev_server.py

How it stays away from the live database:
  1. SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY / SUPABASE_DB_URL are overwritten with dummy local values BEFORE the app is imported,
     so even code that bypassed get_client() could only reach localhost:1 (nothing listens there).
  2. app.db.get_client is replaced by a small adapter (LocalClient) that speaks the few supabase-py calls the backend uses
     (table().select/insert/update/delete + eq/gte/order/limit/maybe_single) straight to the local Postgres on LOCAL_PG_PORT (default 5544).
Everything else (LLM, Jev, speech) behaves as in production, so it still calls those providers with your keys (read-only text in, text out).
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
import sys
import uuid
from pathlib import Path
from typing import Any

PG_PORT = int(os.environ.get("LOCAL_PG_PORT", "5544"))
PG_DSN = f"host=127.0.0.1 port={PG_PORT} dbname=samadhan_scratch user=postgres"

# --- 1. never let this process see the live database -------------------------------------------------------------------------------------
for _name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_DB_URL"):
    os.environ[_name] = "http://127.0.0.1:1" if _name == "SUPABASE_URL" else "local-dev-dummy"

import psycopg
from postgrest.exceptions import APIError
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class _Result:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


def _plain(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def _param(v: Any) -> Any:
    return Jsonb(v) if isinstance(v, (dict, list)) and not _is_text_array(v) else v


def _is_text_array(v: Any) -> bool:
    return False  # text[] columns are only written by SQL seeds, never by the app


class _Query:
    def __init__(self, conn_factory, table: str) -> None:
        self._conn, self._table = conn_factory, table
        self._op = "select"
        self._cols = "*"
        self._count = False
        self._payload: Any = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._single = False

    # builders
    def select(self, cols: str = "*", count: str | None = None) -> _Query:
        self._op, self._cols, self._count = "select", cols, count == "exact"
        return self

    def insert(self, row: dict | list[dict]) -> _Query:
        self._op, self._payload = "insert", row
        return self

    def update(self, row: dict) -> _Query:
        self._op, self._payload = "update", row
        return self

    def delete(self) -> _Query:
        self._op = "delete"
        return self

    def _f(self, col: str, op: str, val: Any) -> _Query:
        self._filters.append((col, op, val))
        return self

    def eq(self, c, v): return self._f(c, "=", v)  # noqa: E704
    def neq(self, c, v): return self._f(c, "<>", v)  # noqa: E704
    def gte(self, c, v): return self._f(c, ">=", v)  # noqa: E704
    def gt(self, c, v): return self._f(c, ">", v)  # noqa: E704
    def lte(self, c, v): return self._f(c, "<=", v)  # noqa: E704
    def lt(self, c, v): return self._f(c, "<", v)  # noqa: E704
    def in_(self, c, v): return self._f(c, "= ANY", list(v))  # noqa: E704

    def order(self, col: str, desc: bool = False, **_kw) -> _Query:
        self._order.append((col, desc))
        return self

    def limit(self, n: int) -> _Query:
        self._limit = n
        return self

    def maybe_single(self) -> _Query:
        self._single = True
        return self

    # execution
    def _where(self) -> tuple[sql.Composable, list[Any]]:
        if not self._filters:
            return sql.SQL(""), []
        parts, params = [], []
        for col, op, val in self._filters:
            if op == "= ANY":
                parts.append(sql.SQL("{} = ANY(%s)").format(sql.Identifier(col)))
            else:
                parts.append(sql.SQL("{} " + op + " %s").format(sql.Identifier(col)))
            params.append(val)
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(parts), params

    def execute(self) -> _Result:
        t = sql.Identifier(self._table)
        where, wparams = self._where()
        try:
            with self._conn() as conn, conn.cursor(row_factory=dict_row) as cur:
                if self._op == "select":
                    cols = sql.SQL("*") if self._cols.strip() == "*" else sql.SQL(", ").join(sql.Identifier(c.strip()) for c in self._cols.split(","))
                    q = sql.SQL("SELECT {} FROM {}").format(cols, t) + where
                    if self._order:
                        q += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL("DESC" if d else "ASC")) for c, d in self._order)
                    if self._limit is not None:
                        q += sql.SQL(" LIMIT {}").format(sql.Literal(self._limit))
                    cur.execute(q, wparams)
                    rows = [{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()]
                    count = None
                    if self._count:
                        cur.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(t) + where, wparams)
                        count = cur.fetchone()["n"]
                    if self._single:
                        return _Result(rows[0] if rows else None, count)
                    return _Result(rows, count)
                if self._op == "insert":
                    rows_in = self._payload if isinstance(self._payload, list) else [self._payload]
                    out = []
                    for row in rows_in:
                        keys = list(row)
                        q = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(t, sql.SQL(", ").join(map(sql.Identifier, keys)), sql.SQL(", ").join(sql.Placeholder() * len(keys)))
                        cur.execute(q, [_param(row[k]) for k in keys])
                        out += [{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()]
                    return _Result(out)
                if self._op == "update":
                    keys = list(self._payload)
                    q = sql.SQL("UPDATE {} SET {}").format(t, sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in keys)) + where + sql.SQL(" RETURNING *")
                    cur.execute(q, [_param(self._payload[k]) for k in keys] + wparams)
                    return _Result([{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()])
                cur.execute(sql.SQL("DELETE FROM {}").format(t) + where + sql.SQL(" RETURNING *"), wparams)
                return _Result([{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()])
        except psycopg.errors.UniqueViolation as exc:
            raise APIError({"message": str(exc), "code": "23505", "hint": None, "details": None}) from exc
        except psycopg.Error as exc:
            raise APIError({"message": str(exc), "code": getattr(exc, "sqlstate", None) or "XX000", "hint": None, "details": None}) from exc


class _Storage:
    """Voice uploads are not kept in local mode (the audio is still transcribed in memory)."""

    def from_(self, _bucket: str) -> _Storage:
        return self

    def upload(self, *_a, **_k) -> None:
        return None


class LocalClient:
    storage = _Storage()

    def _conn(self) -> psycopg.Connection:
        return psycopg.connect(PG_DSN, autocommit=True)

    def table(self, name: str) -> _Query:
        return _Query(self._conn, name)


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import db

    client = LocalClient()
    db.get_client = lambda: client  # every `from app.db import get_client` after this point gets the local client
    with psycopg.connect(PG_DSN) as c:  # fail fast, with a clear message, if the private database is not running
        n = c.execute("select count(*) from offices").fetchone()[0]
    print(f"[local-dev] private Postgres on port {PG_PORT}: {n} offices. Live Supabase is NOT used (SUPABASE_* overwritten).", flush=True)

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
