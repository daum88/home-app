"""SQLite storage: fridge inventory, device-state cache, conversation history.

These helpers are synchronous on purpose — callers that run inside the async
event loop wrap them with ``asyncio.to_thread`` (see the inventory tool).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta
from typing import Any

from . import config

_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    directory = os.path.dirname(config.DB_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if missing. Safe to call repeatedly."""
    global _initialized
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    barcode    TEXT UNIQUE,
                    name       TEXT NOT NULL,
                    brands     TEXT,
                    category   TEXT,
                    expires_on TEXT,
                    added_on   TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS device_cache (
                    key        TEXT PRIMARY KEY,
                    value      TEXT,
                    updated_on TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_on TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_no   TEXT PRIMARY KEY,
                    item_count   INTEGER,
                    imported_on  TEXT DEFAULT (datetime('now')),
                    store        TEXT,
                    receipt_date TEXT,
                    total        REAL
                );

                CREATE TABLE IF NOT EXISTS recipes (
                    id           TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    ingredients  TEXT,
                    instructions TEXT,
                    url          TEXT,
                    thumb        TEXT,
                    source       TEXT,
                    saved_on     TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS shopping (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    name     TEXT NOT NULL,
                    added_on TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    barcode   TEXT,
                    name      TEXT NOT NULL,
                    price     REAL NOT NULL,
                    bought_on TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_price_unique
                    ON price_history(barcode, name, bought_on);
                """
            )
            # Migrate existing DBs that predate the spending columns.
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(receipts)").fetchall()}
            if "store" not in cols:
                conn.execute("ALTER TABLE receipts ADD COLUMN store TEXT")
            if "receipt_date" not in cols:
                conn.execute("ALTER TABLE receipts ADD COLUMN receipt_date TEXT")
            if "total" not in cols:
                conn.execute("ALTER TABLE receipts ADD COLUMN total REAL")
            conn.commit()
        finally:
            conn.close()
        _initialized = True


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    if item.get("expires_on"):
        try:
            expires = date.fromisoformat(item["expires_on"])
            item["days_left"] = (expires - date.today()).days
        except ValueError:
            item["days_left"] = None
    return item


def inventory_add(
    *, name: str, barcode: str, brands: str = "", category: str = "", expires_on: str | None = None
) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO inventory (barcode, name, brands, category, expires_on)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(barcode) DO UPDATE SET
                    name = excluded.name,
                    brands = excluded.brands,
                    category = excluded.category,
                    expires_on = excluded.expires_on
                """,
                (barcode, name, brands, category, expires_on),
            )
            conn.commit()
        finally:
            conn.close()


def inventory_list() -> list[dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT barcode, name, brands, category, expires_on, added_on "
                "FROM inventory ORDER BY (expires_on IS NULL), expires_on ASC"
            ).fetchall()
            return [_row_to_item(r) for r in rows]
        finally:
            conn.close()


def inventory_expiring(days: int = 3) -> list[dict[str, Any]]:
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT barcode, name, brands, category, expires_on, added_on "
                "FROM inventory WHERE expires_on IS NOT NULL AND expires_on <= ? "
                "ORDER BY expires_on ASC",
                (cutoff,),
            ).fetchall()
            return [_row_to_item(r) for r in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Device-state cache (last-known readings, for graceful answers when offline)
# ---------------------------------------------------------------------------

def cache_get(key: str) -> Any | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT value FROM device_cache WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            return json.loads(row["value"])
        finally:
            conn.close()


def cache_set(key: str, value: Any) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO device_cache (key, value, updated_on) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_on = datetime('now')",
                (key, json.dumps(value)),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Receipts (dedupe imported Coop e-receipts)
# ---------------------------------------------------------------------------

def receipt_seen(receipt_no: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT 1 FROM receipts WHERE receipt_no = ?", (receipt_no,)).fetchone()
            return row is not None
        finally:
            conn.close()


def receipt_mark(receipt_no: str, item_count: int, store: str = "", receipt_date: str = "",
                 total: float | None = None) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO receipts (receipt_no, item_count, store, receipt_date, total) "
                "VALUES (?, ?, ?, ?, ?)",
                (receipt_no, item_count, store or None, receipt_date or None, total),
            )
            conn.commit()
        finally:
            conn.close()


def receipt_update_meta(receipt_no: str, store: str, receipt_date: str, total: float) -> None:
    """Backfill spending metadata for a receipt imported before it was tracked."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE receipts SET store = ?, receipt_date = ?, total = ? "
                "WHERE receipt_no = ? AND (store IS NULL OR store = '')",
                (store, receipt_date, total, receipt_no),
            )
            conn.commit()
        finally:
            conn.close()


def spending_monthly(months: int = 6) -> list[dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT substr(receipt_date, 1, 7) AS month, SUM(total) AS total, COUNT(*) AS count "
                "FROM receipts WHERE receipt_date IS NOT NULL AND total IS NOT NULL "
                "AND receipt_date >= date('now', ?) "
                "GROUP BY month ORDER BY month ASC",
                (f"-{months} months",),
            ).fetchall()
            return [{"month": r["month"], "total": round(r["total"] or 0, 2), "count": r["count"]} for r in rows]
        finally:
            conn.close()


def spending_by_store(months: int = 6) -> list[dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT store, SUM(total) AS total, COUNT(*) AS count "
                "FROM receipts WHERE store IS NOT NULL AND store != '' AND total IS NOT NULL "
                "AND receipt_date >= date('now', ?) "
                "GROUP BY store ORDER BY total DESC",
                (f"-{months} months",),
            ).fetchall()
            return [{"store": r["store"], "total": round(r["total"] or 0, 2), "count": r["count"]} for r in rows]
        finally:
            conn.close()


def recent_receipts(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT receipt_no, store, receipt_date, total, item_count, imported_on "
                "FROM receipts ORDER BY COALESCE(receipt_date, imported_on) DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def price_add(*, barcode: str, name: str, price: float, bought_on: str) -> None:
    """Record one product's price for a shopping trip (idempotent per barcode+name+day)."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO price_history (barcode, name, price, bought_on) VALUES (?, ?, ?, ?)",
                (barcode, name, price, bought_on),
            )
            conn.commit()
        finally:
            conn.close()


def price_trend(name: str, limit: int = 20) -> list[dict[str, Any]]:
    """Price history for a product, newest first."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT barcode, name, price, bought_on FROM price_history "
                "WHERE instr(lower(name), lower(?)) > 0 ORDER BY bought_on DESC LIMIT ?",
                (name, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Saved recipes
# ---------------------------------------------------------------------------

def recipe_save(*, id: str, name: str, ingredients: list[str], instructions: str,
                url: str = "", thumb: str = "", source: str = "") -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO recipes (id, name, ingredients, instructions, url, thumb, source) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, ingredients=excluded.ingredients, "
                "instructions=excluded.instructions, url=excluded.url, thumb=excluded.thumb, source=excluded.source",
                (id, name, json.dumps(ingredients), instructions, url, thumb, source),
            )
            conn.commit()
        finally:
            conn.close()


def recipe_list() -> list[dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT * FROM recipes ORDER BY saved_on DESC").fetchall()
            out = []
            for r in rows:
                item = dict(r)
                try:
                    item["ingredients"] = json.loads(item.get("ingredients") or "[]")
                except json.JSONDecodeError:
                    item["ingredients"] = []
                out.append(item)
            return out
        finally:
            conn.close()


def recipe_get(id: str) -> dict[str, Any] | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            try:
                item["ingredients"] = json.loads(item.get("ingredients") or "[]")
            except json.JSONDecodeError:
                item["ingredients"] = []
            return item
        finally:
            conn.close()


def recipe_delete(id: str) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute("DELETE FROM recipes WHERE id = ?", (id,))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------

def shopping_add(name: str) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute("INSERT INTO shopping (name) VALUES (?)", (name,))
            conn.commit()
        finally:
            conn.close()


def shopping_list() -> list[dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT * FROM shopping ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def shopping_remove(item_id: int) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute("DELETE FROM shopping WHERE id = ?", (item_id,))
            conn.commit()
        finally:
            conn.close()


def shopping_clear() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute("DELETE FROM shopping")
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

def history_append(role: str, content: str) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, content))
            # Prune to the newest 500 messages so the table never grows unbounded.
            conn.execute(
                "DELETE FROM history WHERE id NOT IN "
                "(SELECT id FROM history ORDER BY id DESC LIMIT 500)"
            )
            conn.commit()
        finally:
            conn.close()


def history_recent(limit: int = 20) -> list[dict[str, str]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT role, content FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        finally:
            conn.close()
