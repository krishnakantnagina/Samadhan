"""A Supabase-shaped client that talks to the PRIVATE local Postgres (devdb, port 5544) instead of the live Supabase.

TEST ONLY. Mirrors backend/scripts/local_dev_server.py's LocalClient, but adds the one thing the dashboard needs that the
backend never does: PostgREST embedded selects like `offices(office_name,level)` -> a LEFT JOIN nested as a JSON object, so
`list_tickets()` and friends get `{..., "offices": {"office_name": ..., "level": ...}}` exactly as supabase-py would return.

Supported surface is only what dashboard/ actually calls: table().select/insert/update/delete + eq/neq/gte/gt/lte/lt/in_/
order/limit/maybe_single + select(count="exact"), one-level embeds, and a no-op storage. Anything else raises, on purpose.
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import uuid
from typing import Any

import psycopg
from postgrest.exceptions import APIError
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PG_PORT = int(os.environ.get("LOCAL_PG_PORT", "5544"))
PG_DSN = f"host=127.0.0.1 port={PG_PORT} dbname=samadhan_scratch user=postgres"

# How an embedded table is joined to its parent: (parent, embed) -> (local column on parent, column on embed).
# PostgREST infers this from foreign keys; here the few the dashboard uses are spelled out.
FK_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("tickets", "offices"): ("office_id", "id"),
    ("tickets", "users"): ("user_id", "id"),
}

_EMBED_RE = re.compile(r"^(\w+)\((.*)\)$", re.DOTALL)


def _split_top(cols: str) -> list[str]:
    """Split a PostgREST column list on top-level commas only (commas inside `name(...)` stay put)."""
    parts, depth, cur = [], 0, ""
    for ch in cols:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _plain(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def _param(v: Any) -> Any:
    return Jsonb(v) if isinstance(v, (dict, list)) else v


class _Result:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


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

    # builders -------------------------------------------------------------
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

    # execution ------------------------------------------------------------
    def _parse_cols(self) -> tuple[list[str], list[tuple[str, list[str]]]]:
        """-> (base column names, [(embed table, its column names)])."""
        base: list[str] = []
        embeds: list[tuple[str, list[str]]] = []
        for part in _split_top(self._cols):
            m = _EMBED_RE.match(part)
            if m:
                embeds.append((m.group(1), _split_top(m.group(2))))
            else:
                base.append(part)
        return base, embeds

    def _col(self, name: str, joined: bool) -> sql.Composable:
        return sql.SQL("t.{}").format(sql.Identifier(name)) if joined else sql.Identifier(name)

    def _where(self, joined: bool) -> tuple[sql.Composable, list[Any]]:
        if not self._filters:
            return sql.SQL(""), []
        parts, params = [], []
        for col, op, val in self._filters:
            if op == "= ANY":
                parts.append(sql.SQL("{} = ANY(%s)").format(self._col(col, joined)))
            else:
                parts.append(sql.SQL("{} " + op + " %s").format(self._col(col, joined)))
            params.append(val)
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(parts), params

    def _select_sql(self) -> tuple[sql.Composable, list[Any]]:
        base, embeds = self._parse_cols()
        t = sql.Identifier(self._table)
        joined = bool(embeds)
        if self._cols.strip() == "*":
            items: list[sql.Composable] = [sql.SQL("t.*") if joined else sql.SQL("*")]
        else:
            items = [self._col(c, joined) for c in base]
        joins: list[sql.Composable] = []
        for etab, ecols in embeds:
            key = (self._table, etab)
            if key not in FK_MAP:
                raise APIError({"message": f"no embed mapping for {key}", "code": "PGRST200", "hint": None, "details": None})
            lcol, fcol = FK_MAP[key]
            alias = f"emb_{etab}"
            joins.append(
                sql.SQL(" LEFT JOIN {} AS {} ON {}.{} = t.{}").format(
                    sql.Identifier(etab), sql.Identifier(alias), sql.Identifier(alias), sql.Identifier(fcol), sql.Identifier(lcol)
                )
            )
            obj = sql.SQL("json_build_object({}) AS {}").format(
                sql.SQL(", ").join(
                    sql.SQL("{}, {}.{}").format(sql.Literal(c), sql.Identifier(alias), sql.Identifier(c)) for c in ecols
                ),
                sql.Identifier(etab),
            )
            items.append(obj)
        from_clause = sql.SQL(" FROM {} t").format(t) if joined else sql.SQL(" FROM {}").format(t)
        q = sql.SQL("SELECT ") + sql.SQL(", ").join(items) + from_clause + sql.SQL("").join(joins)
        where, params = self._where(joined)
        q += where
        if self._order:
            q += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(
                sql.SQL("{} {}").format(self._col(c, joined), sql.SQL("DESC" if d else "ASC")) for c, d in self._order
            )
        if self._limit is not None:
            q += sql.SQL(" LIMIT {}").format(sql.Literal(self._limit))
        return q, params

    def execute(self) -> _Result:
        t = sql.Identifier(self._table)
        try:
            with self._conn() as conn, conn.cursor(row_factory=dict_row) as cur:
                if self._op == "select":
                    q, params = self._select_sql()
                    cur.execute(q, params)
                    rows = [{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()]
                    count = None
                    if self._count:
                        where, wparams = self._where(False)
                        cur.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(t) + where, wparams)
                        count = cur.fetchone()["n"]
                    if self._single:
                        return _Result(rows[0] if rows else None, count)
                    return _Result(rows, count)
                where, wparams = self._where(False)
                if self._op == "insert":
                    rows_in = self._payload if isinstance(self._payload, list) else [self._payload]
                    out = []
                    for row in rows_in:
                        keys = list(row)
                        q = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                            t, sql.SQL(", ").join(map(sql.Identifier, keys)), sql.SQL(", ").join(sql.Placeholder() * len(keys))
                        )
                        cur.execute(q, [_param(row[k]) for k in keys])
                        out += [{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()]
                    return _Result(out)
                if self._op == "update":
                    keys = list(self._payload)
                    q = sql.SQL("UPDATE {} SET {}").format(
                        t, sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in keys)
                    ) + where + sql.SQL(" RETURNING *")
                    cur.execute(q, [_param(self._payload[k]) for k in keys] + wparams)
                    return _Result([{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()])
                cur.execute(sql.SQL("DELETE FROM {}").format(t) + where + sql.SQL(" RETURNING *"), wparams)
                return _Result([{k: _plain(v) for k, v in r.items()} for r in cur.fetchall()])
        except psycopg.errors.UniqueViolation as exc:
            raise APIError({"message": str(exc), "code": "23505", "hint": None, "details": None}) from exc
        except psycopg.Error as exc:
            raise APIError({"message": str(exc), "code": getattr(exc, "sqlstate", None) or "XX000", "hint": None, "details": None}) from exc


class _Storage:
    """No audio storage in local mode: uploads are dropped and no signed URL exists (the detail panel handles the failure)."""

    def from_(self, _bucket: str) -> _Storage:
        return self

    def upload(self, *_a, **_k) -> None:
        return None

    def create_signed_url(self, *_a, **_k) -> dict[str, Any]:
        return {"signedURL": None, "error": "no audio storage in local mode"}


class LocalClient:
    storage = _Storage()

    def _conn(self) -> psycopg.Connection:
        return psycopg.connect(PG_DSN, autocommit=True)

    def table(self, name: str) -> _Query:
        return _Query(self._conn, name)
