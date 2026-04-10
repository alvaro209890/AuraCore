from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable
from uuid import UUID, uuid4

JSON_COLUMNS = {
    "structural_strengths",
    "structural_routines",
    "structural_preferences",
    "structural_open_questions",
    "key_learnings",
    "people_and_relationships",
    "routine_signals",
    "preferences",
    "open_questions",
    "salient_facts",
    "open_loops",
    "recent_topics",
    "next_steps",
    "evidence",
    "metadata",
    "objectives",
    "durable_facts",
    "constraints",
    "recurring_instructions",
    "creds",
    "value",
}

AUTO_ID_COLUMNS = {
    "important_messages": "id",
}


@dataclass(slots=True)
class SQLiteResponse:
    data: list[dict[str, Any]] | None = None


def _quote(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _serialize_value(column: str, value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True)
    return value


def _deserialize_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in JSON_COLUMNS and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [] if column != "metadata" else {}
    return value


class SQLiteClient:
    def __init__(self, db_path: str, *, schema_path: Path | None = None) -> None:
        path = Path(db_path).expanduser()
        parent = path.parent
        if not parent.is_dir():
            raise RuntimeError(f"AuraCore database directory does not exist: {parent}")
        if not os.access(parent, os.W_OK):
            raise RuntimeError(f"AuraCore database directory is not writable: {parent}")
        if path.exists() and not os.access(path, os.W_OK):
            raise RuntimeError(f"AuraCore database file is not writable: {path}")

        self.db_path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if schema_path is not None:
            self.initialize_schema(schema_path)

    def initialize_schema(self, schema_path: Path) -> None:
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self._lock:
            self._conn.executescript(schema_sql)
            self._conn.commit()

    def table(self, table_name: str) -> SQLiteQuery:
        return SQLiteQuery(self, table_name)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cursor

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.executemany(sql, rows)
            self._conn.commit()
            return cursor

    def execute_script(self, sql: str) -> None:
        with self._lock:
            self._conn.executescript(sql)
            self._conn.commit()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_columns(self, table_name: str) -> set[str]:
        with self._lock:
            cursor = self._conn.execute(f"PRAGMA table_info({_quote(table_name)})")
            rows = cursor.fetchall()
        columns: set[str] = set()
        for row in rows:
            name = row["name"] if isinstance(row, sqlite3.Row) else None
            if isinstance(name, str) and name.strip():
                columns.add(name.strip())
        return columns

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = _deserialize_value(key, row[key])
        return result


class SQLiteQuery:
    def __init__(self, client: SQLiteClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self._operation = "select"
        self._select_columns: list[str] | None = None
        self._rows: list[dict[str, Any]] = []
        self._update_payload: dict[str, Any] = {}
        self._conflict_columns: list[str] = []
        self._filters: list[tuple[str, str, Any]] = []
        self._in_filters: list[tuple[str, list[Any]]] = []
        self._or_filters: list[str] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._offset: int | None = None

    def select(self, columns: str) -> SQLiteQuery:
        self._operation = "select"
        raw = columns.strip()
        self._select_columns = None if raw == "*" else [part.strip() for part in raw.split(",") if part.strip()]
        return self

    def insert(self, rows: dict[str, Any] | list[dict[str, Any]]) -> SQLiteQuery:
        self._operation = "insert"
        self._rows = self._normalize_rows(rows)
        return self

    def upsert(self, rows: dict[str, Any] | list[dict[str, Any]], *, on_conflict: str) -> SQLiteQuery:
        self._operation = "upsert"
        self._rows = self._normalize_rows(rows)
        self._conflict_columns = [part.strip() for part in on_conflict.split(",") if part.strip()]
        return self

    def update(self, payload: dict[str, Any]) -> SQLiteQuery:
        self._operation = "update"
        self._update_payload = dict(payload)
        return self

    def delete(self) -> SQLiteQuery:
        self._operation = "delete"
        return self

    def eq(self, column: str, value: Any) -> SQLiteQuery:
        self._filters.append((column, "=", value))
        return self

    def gte(self, column: str, value: Any) -> SQLiteQuery:
        self._filters.append((column, ">=", value))
        return self

    def lte(self, column: str, value: Any) -> SQLiteQuery:
        self._filters.append((column, "<=", value))
        return self

    def lt(self, column: str, value: Any) -> SQLiteQuery:
        self._filters.append((column, "<", value))
        return self

    def gt(self, column: str, value: Any) -> SQLiteQuery:
        self._filters.append((column, ">", value))
        return self

    def in_(self, column: str, values: list[Any]) -> SQLiteQuery:
        self._in_filters.append((column, list(values)))
        return self

    def order(self, column: str, *, desc: bool = False) -> SQLiteQuery:
        self._orders.append((column, desc))
        return self

    def limit(self, value: int) -> SQLiteQuery:
        self._limit = max(0, int(value))
        return self

    def range(self, start: int, end: int) -> SQLiteQuery:
        start_value = max(0, int(start))
        end_value = max(start_value, int(end))
        self._offset = start_value
        self._limit = (end_value - start_value) + 1
        return self

    def or_(self, expression: str) -> SQLiteQuery:
        self._or_filters.append(expression)
        return self

    def execute(self) -> SQLiteResponse:
        if self._operation == "select":
            return self._execute_select()
        if self._operation == "insert":
            self._execute_insert(upsert=False)
            return SQLiteResponse(data=[])
        if self._operation == "upsert":
            self._execute_insert(upsert=True)
            return SQLiteResponse(data=[])
        if self._operation == "update":
            self._execute_update()
            return SQLiteResponse(data=[])
        if self._operation == "delete":
            self._execute_delete()
            return SQLiteResponse(data=[])
        raise RuntimeError(f"Unsupported SQLiteQuery operation: {self._operation}")

    def _normalize_rows(self, rows: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(rows, dict):
            normalized = [dict(rows)]
        else:
            normalized = [dict(row) for row in rows]
        auto_id_column = AUTO_ID_COLUMNS.get(self.table_name)
        if auto_id_column:
            for row in normalized:
                if not row.get(auto_id_column):
                    row[auto_id_column] = str(uuid4())
        return normalized

    def _execute_select(self) -> SQLiteResponse:
        columns_sql = "*" if self._select_columns is None else ", ".join(_quote(column) for column in self._select_columns)
        sql = [f"SELECT {columns_sql} FROM {_quote(self.table_name)}"]
        where_sql, params = self._build_where_clause()
        if where_sql:
            sql.append(where_sql)
        if self._orders:
            order_sql: list[str] = []
            for column, desc in self._orders:
                direction = "DESC" if desc else "ASC"
                quoted = _quote(column)
                order_sql.append(f"({quoted} IS NULL) ASC")
                order_sql.append(f"{quoted} {direction}")
            sql.append("ORDER BY " + ", ".join(order_sql))
        if self._limit is not None:
            sql.append(f"LIMIT {self._limit}")
        if self._offset is not None:
            sql.append(f"OFFSET {self._offset}")
        rows = self.client.fetchall(" ".join(sql), params)
        return SQLiteResponse(data=rows)

    def _execute_insert(self, *, upsert: bool) -> None:
        if not self._rows:
            return
        columns: list[str] = []
        for row in self._rows:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
        quoted_columns = ", ".join(_quote(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {_quote(self.table_name)} ({quoted_columns}) VALUES ({placeholders})"
        if upsert:
            conflict = ", ".join(_quote(column) for column in self._conflict_columns)
            update_columns = [column for column in columns if column not in self._conflict_columns]
            if update_columns:
                updates = ", ".join(f"{_quote(column)}=excluded.{_quote(column)}" for column in update_columns)
                sql += f" ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
            else:
                sql += f" ON CONFLICT ({conflict}) DO NOTHING"
        rows = [
            tuple(_serialize_value(column, row.get(column)) for column in columns)
            for row in self._rows
        ]
        self.client.executemany(sql, rows)

    def _execute_update(self) -> None:
        if not self._update_payload:
            return
        assignments = []
        params: list[Any] = []
        for column, value in self._update_payload.items():
            assignments.append(f"{_quote(column)} = ?")
            params.append(_serialize_value(column, value))
        sql = [f"UPDATE {_quote(self.table_name)} SET {', '.join(assignments)}"]
        where_sql, where_params = self._build_where_clause()
        if where_sql:
            sql.append(where_sql)
            params.extend(where_params)
        self.client.execute(" ".join(sql), params)

    def _execute_delete(self) -> None:
        sql = [f"DELETE FROM {_quote(self.table_name)}"]
        where_sql, params = self._build_where_clause()
        if where_sql:
            sql.append(where_sql)
        self.client.execute(" ".join(sql), params)

    def _build_where_clause(self) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, operator, value in self._filters:
            clauses.append(f"{_quote(column)} {operator} ?")
            params.append(_serialize_value(column, value))
        for column, values in self._in_filters:
            if not values:
                clauses.append("1 = 0")
                continue
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{_quote(column)} IN ({placeholders})")
            params.extend(_serialize_value(column, value) for value in values)
        for expression in self._or_filters:
            parsed_clause, parsed_params = self._parse_or_expression(expression)
            if parsed_clause:
                clauses.append(f"({parsed_clause})")
                params.extend(parsed_params)
        return ("WHERE " + " AND ".join(clauses), params) if clauses else ("", [])

    def _parse_or_expression(self, expression: str) -> tuple[str, list[Any]]:
        or_clauses: list[str] = []
        params: list[Any] = []
        for raw_clause in expression.split(","):
            clause = raw_clause.strip()
            if not clause:
                continue
            parts = clause.split(".", 2)
            if len(parts) != 3:
                raise RuntimeError(f"Unsupported SQLite OR clause: {clause}")
            column, operator, value = parts
            if operator == "ilike":
                or_clauses.append(f"LOWER({_quote(column)}) LIKE LOWER(?)")
                params.append(value)
                continue
            raise RuntimeError(f"Unsupported SQLite OR operator: {operator}")
        return " OR ".join(or_clauses), params
