"""Coop e-receipt pipeline: PDF → parsed items → enriched names → inventory.

Flow per receipt:
  1. ``parse_receipt`` extracts item lines (name + EAN barcode + qty + price).
  2. Each item is enriched: the receipt's Estonian name is humanised and used as
     the **primary name** (it is specific and in the user's language; Open Food
     Facts names are often generic or in a foreign language). Open Food Facts is
     used to fill in **brand** and, when the local keyword rules don't match, the
     **category**.
  3. Expiry is **estimated** from a category → shelf-life table, based on the
     receipt's purchase date (receipts never contain expiry dates).
  4. Items are written to SQLite, deduped by receipt number.

hOn has no food-inventory API (verified — pyhOn exposes only fridge control),
so the fridge inventory lives in this project's SQLite store and is surfaced
via the web UI and the voice assistant.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from .. import config, db
from . import hon_inventory
from .base import ToolError

OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"

_BARCODE_RE = re.compile(r"^\d{8,14}$")
_DIACRITICS = str.maketrans("äöüõšž", "aouosz")

# Units kept uppercase when humanising (receipt names are ALL CAPS).
_KEEP_UPPER = {"KG", "G", "L", "ML", "DL", "CL", "TK", "PK", "GR", "MM", "CM", "M"}
# "400G" / "2KG" / "1.5L" / "10TK" → "400 G" / "2 KG" ...
_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KG|G|L|ML|DL|CL|TK|PK|GR|MM|CM|M)\b", re.IGNORECASE)

# category → (days, keywords). Order matters: first match wins, so specific /
# unambiguous keywords (snacks, eggs, bakery, drinks, pantry) come before generic
# ones (dairy's "juust", meat's "kana") that also appear inside compound words
# (e.g. "popcorn … juustu" is a snack, not dairy).
# days=None → non-food / unknown, no expiry.
_RULES: list[tuple[str, int | None, list[str]]] = [
    ("non-food", None, ["paber", "kott", "salvratik", "kile", "rinnafil", "rinnahoidja",
                        "kuunal", "patarei", "pesu", "nõudepesu"]),
    ("snacks", 90, ["kupsis", "sokolaad", "komm", "krops", "popcorn", "jaatis",
                    "snakk", "kupsise", "šokolaad", "küpsis", "krõps", "jäätis"]),
    ("eggs", 21, ["muna"]),
    ("bakery", 4, ["leib", "sai", "sepik", "kukkel", "baguette", "croissant", "röst"]),
    ("drinks", 90, ["mahl", "limonaad", "karastus", "vesi", "olu", "vein", "siider",
                    "kohv", "nektar", "cola", "pepsi", "fanta", "sprite"]),
    ("pantry", 180, ["jahu", "suhkur", "riis", "makaron", "pasta", "helbed", "helvest",
                     "musli", "oli", "sool", "konserv", "tatar", "oder", "manna",
                     "kaerahelbed", "kaer", "maitseaine"]),
    ("dairy", 7, ["piim", "koor", "jogurt", "keefir", "hapukoor", "voi", "juust",
                  "kohupiim", "kodujuust", "või"]),
    ("meat & fish", 3, ["kana", "liha", "hakkliha", "kala", "lohe", "vorst", "viiner",
                        "sink", "peekon", "kalkun", "krevett", "mereand"]),
    ("fruit & veg", 7, ["õun", "oun", "arbuus", "laim", "banaan", "apelsin", "sidrun",
                        "pirn", "viinamari", "maasikas", "puuvili", "melon", "kiivi",
                        "ploom", "kirss", "kartul", "porgand", "sibul", "kuuslauk",
                        "kapsas", "kurk", "tomat", "salat", "paprika", "koogivili",
                        "brokoli", "lillkapsas", "suvikorvits"]),
]

_OFF_CAT: list[tuple[str, str, int]] = [
    ("dair", "dairy", 7), ("milk", "dairy", 7), ("yogurt", "dairy", 7),
    ("chees", "dairy", 14), ("egg", "eggs", 21), ("bread", "bakery", 4),
    ("meat", "meat & fish", 3), ("fish", "meat & fish", 3), ("poultr", "meat & fish", 3),
    ("seafood", "meat & fish", 3), ("fruit", "fruit & veg", 7), ("vegetable", "fruit & veg", 14),
    ("potato", "fruit & veg", 21), ("cereal", "pantry", 180), ("pasta", "pantry", 180),
    ("rice", "pantry", 180), ("sugar", "pantry", 180), ("sweetener", "pantry", 180),
    ("flour", "pantry", 180), ("beverage", "drinks", 90), ("juice", "drinks", 90),
    ("soda", "drinks", 90), ("water", "drinks", 90), ("wine", "drinks", 180),
    ("beer", "drinks", 90), ("alcohol", "drinks", 180), ("snack", "snacks", 90),
    ("chocolate", "snacks", 90), ("confection", "snacks", 90), ("ice-cream", "snacks", 90),
    ("popcorn", "snacks", 90),
]


# ---------------------------------------------------------------------------
# Name / category helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase + strip diacritics, for keyword matching."""
    return text.lower().translate(_DIACRITICS)


def _humanize(name: str) -> str:
    """Turn a receipt's SHOUTY name into a readable one, keeping units."""
    s = " ".join(name.split())
    if not s:
        return s
    # "BR.RINNAFIL" → "BR. RINNAFIL"
    s = re.sub(r"([A-Za-zÄÖÜÕäöüõ])\.([A-Za-zÄÖÜÕäöüõ])", r"\1. \2", s)
    # "SISETÜKK400G" → "SISETÜKK 400G"
    s = re.sub(r"([A-Za-zÄÖÜÕäöüõ])(\d)", r"\1 \2", s)
    # "400G" → "400 G", "1.5L" → "1.5 L"
    s = _UNIT_RE.sub(lambda m: f"{m.group(1)} {m.group(2).upper()}", s)
    s = s.replace("+", " + ")
    s = " ".join(s.split())

    if s.isupper() or not any(c.islower() for c in s):
        words: list[str] = []
        for w in s.split():
            if re.fullmatch(r"[\d.,%+-]+", w) or w.upper() in _KEEP_UPPER:
                words.append(w)
            else:
                words.append(w.capitalize())
        s = " ".join(words)
    return s


def _rule_for(name: str) -> tuple[str, int | None]:
    n = _norm(name)
    for category, days, keywords in _RULES:
        for kw in keywords:
            if kw in n:
                return category, days
    return "other", None


def _off_category(tags: list[str]) -> tuple[str, int | None]:
    for tag in tags or []:
        t = _norm(tag.replace("en:", ""))
        for key, label, days in _OFF_CAT:
            if key in t:
                return label, days
    return "other", None


async def _off_lookup(barcode: str) -> dict[str, Any] | None:
    url = OFF_PRODUCT.format(barcode=barcode)
    headers = {"User-Agent": config.OFF_USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError:
        return None
    if body.get("status") != 1 or not body.get("product"):
        return None
    p = body["product"]
    return {
        "name": p.get("product_name") or p.get("generic_name") or "",
        "brands": p.get("brands") or "",
        "categories_tags": p.get("categories_tags") or [],
    }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _extract_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader  # noqa: PLC0415 — pure-Python, lazy

    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _after_colon(line: str) -> str:
    return line.split(":", 1)[-1].strip() if ":" in line else ""


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_receipt_date(text: str | None) -> date | None:
    if not text:
        return None
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_receipt(pdf_bytes: bytes) -> dict[str, Any]:
    """Parse a Coop e-receipt PDF into metadata + item lines."""
    text = _extract_text(pdf_bytes)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    store = ""
    for ln in lines[:5]:
        if _norm(ln).startswith(("summa", "kokku", "toode", "tsekk", "tsek", "ost", "kuupaev")):
            continue
        store = ln
        break
    meta: dict[str, Any] = {
        "store": store or (lines[0] if lines else ""),
        "receipt_no": None,
        "date": None,
    }
    _receipt_keys = (
        "ost nr", "ost nr.", "ostunumber", "ostu nr", "ostu number",
        "arve nr", "kviitungi nr", "kviitung nr", "tšekk nr", "tsekk nr",
        "tšekinr", "tsekinr", "receipt no", "receipt number",
    )
    for ln in lines:
        low = ln.lower()
        if low.startswith(_receipt_keys):
            value = _after_colon(ln)
            m = re.search(r"(\d{8,14})", value or ln)
            meta["receipt_no"] = m.group(1) if m else value
        elif low.startswith(("kuupäev", "kuupaev")):
            d = _parse_receipt_date(ln)
            meta["date"] = d.isoformat() if d else _after_colon(ln)

    items: list[dict[str, Any]] = []
    for idx, ln in enumerate(lines):
        if not _BARCODE_RE.match(ln):
            continue
        name = lines[idx - 1] if idx > 0 else ""
        qty_raw = lines[idx + 1] if idx + 1 < len(lines) else None
        price_raw = lines[idx + 2] if idx + 2 < len(lines) else None
        if not name or _norm(name).startswith(("kokku", "boonus", "makseviis", "nimetus")):
            continue
        if "pant" in _norm(name):
            continue
        items.append(
            {
                "name": name,
                "barcode": ln,
                "qty": _to_float(qty_raw),
                "price": _to_float(price_raw),
            }
        )

    # Newer Coop receipts have no barcodes — every item is "NAME QTY PRICE" inline.
    if not items:
        items = _parse_inline_items(lines)

    meta["items"] = items
    return meta


# ---------------------------------------------------------------------------
# Enrich + import
# ---------------------------------------------------------------------------

_INLINE_SKIP = (
    "toode", "kokku", "km ", "kaibemaks", "kaart", "tsekk", "tsek",
    "kuupaev", "kliendikaart", "makseviis", "summa", "nimetus",
    "muursepa", "kesk tn", "coop polva", "rg-kood", "pant", "boonus",
)


def _parse_inline_items(lines: list[str]) -> list[dict[str, Any]]:
    """Parse 'NAME QTY PRICE' item lines from barcode-less Coop receipts."""
    items: list[dict[str, Any]] = []
    for ln in lines:
        low = _norm(ln)
        if any(low.startswith(p) for p in _INLINE_SKIP):
            continue
        tokens = ln.split()
        if len(tokens) < 3:
            continue
        price = _to_float(tokens[-1])
        qty = _to_float(tokens[-2])
        if price is None or qty is None:
            continue
        name = " ".join(tokens[:-2]).strip()
        if not name:
            continue
        items.append({"name": name, "barcode": "", "qty": qty, "price": price})
    return items


async def _enrich(name: str, barcode: str) -> dict[str, Any]:
    """Return {name, brands, category, source, days} for one receipt line."""
    human = _humanize(name)
    category, days = _rule_for(name)

    off: dict[str, Any] | None = None
    is_real_ean = len(barcode) >= 8 and not barcode.startswith("2")
    if is_real_ean:
        off = await _off_lookup(barcode)

    if off:
        brands = off.get("brands", "") or ""
        if category == "other" and off.get("categories_tags"):
            category, off_days = _off_category(off["categories_tags"])
            if days is None:
                days = off_days
        source = "openfoodfacts"
    else:
        brands = ""
        source = "receipt"

    return {
        "name": human,
        "brands": brands,
        "category": category,
        "source": source,
        "days": days,
    }


def _save_failed(pdf_bytes: bytes, filename: str = "") -> None:
    """Keep a copy of unparseable PDFs so they can be inspected later."""
    try:
        dest = receipts_dir() / "failed"
        dest.mkdir(parents=True, exist_ok=True)
        name = filename or f"failed-{int(time.time())}.pdf"
        (dest / name).write_bytes(pdf_bytes)
    except OSError:
        pass


async def import_receipt(pdf_bytes: bytes, filename: str = "") -> dict[str, Any]:
    """Import one receipt PDF into the inventory (idempotent by receipt number)."""
    parsed = parse_receipt(pdf_bytes)
    receipt_no = parsed.get("receipt_no")
    if not receipt_no and filename:
        m = re.search(r"(\d{8,14})", filename)
        if m:
            receipt_no = m.group(1)
            parsed["receipt_no"] = receipt_no
    if not receipt_no:
        _save_failed(pdf_bytes, filename)
        raise ToolError("couldn't find a receipt number in this PDF")

    if await asyncio.to_thread(db.receipt_seen, receipt_no):
        # Backfill spending metadata + price history for receipts imported before tracking existed.
        existing_items = parsed.get("items") or []
        backfill_total = round(sum(i["price"] for i in existing_items if i["price"]), 2)
        backfill_date = (_parse_receipt_date(parsed.get("date")) or date.today()).isoformat()
        await asyncio.to_thread(
            db.receipt_update_meta,
            receipt_no,
            parsed.get("store") or "",
            backfill_date,
            backfill_total,
        )
        for i in existing_items:
            if i["price"]:
                await asyncio.to_thread(
                    db.price_add,
                    barcode=i["barcode"],
                    name=_humanize(i["name"]),
                    price=i["price"],
                    bought_on=backfill_date,
                )
        return {"already_imported": True, "receipt_no": receipt_no, "items": []}

    items = parsed.get("items") or []
    if not items:
        raise ToolError("no item lines found in this receipt")

    bought_on = _parse_receipt_date(parsed.get("date")) or date.today()

    added: list[dict[str, Any]] = []
    for item in items:
        enriched = await _enrich(item["name"], item["barcode"])
        expiry = None
        if enriched["days"] is not None:
            expiry = (bought_on + timedelta(days=enriched["days"])).isoformat()

        await asyncio.to_thread(
            db.inventory_add,
            name=enriched["name"],
            barcode=item["barcode"],
            brands=enriched["brands"],
            category=enriched["category"],
            expires_on=expiry,
        )
        if item["price"]:
            await asyncio.to_thread(
                db.price_add,
                barcode=item["barcode"],
                name=enriched["name"],
                price=item["price"],
                bought_on=bought_on.isoformat(),
            )
        added.append(
            {
                "name": enriched["name"],
                "brands": enriched["brands"],
                "category": enriched["category"],
                "barcode": item["barcode"],
                "qty": item["qty"],
                "price": item["price"],
                "expires_on": expiry,
                "source": enriched["source"],
            }
        )

    # Push food items to the hOn fridge inventory (best-effort — never blocks import).
    hon_result: dict[str, Any] | None = None
    if config.HON_USER and config.HON_PASS:
        hon_items = [
            {
                "name": it["name"],
                "category": it["category"],
                "qty": it["qty"],
                "expires_on": it["expires_on"],
                "note": f"Coop {receipt_no}",
            }
            for it in added
            if it["category"] in hon_inventory.CATEGORY_IDS and it["expires_on"]
        ]
        if hon_items:
            try:
                hon_result = await hon_inventory.add_items(hon_items)
            except ToolError as err:
                hon_result = {"error": err.message}
            except Exception as err:  # noqa: BLE001
                hon_result = {"error": str(err)}

    total = round(sum(it["price"] for it in added if it["price"]), 2)
    await asyncio.to_thread(
        db.receipt_mark,
        receipt_no,
        len(added),
        parsed.get("store") or "",
        bought_on.isoformat(),
        total,
    )
    return {
        "already_imported": False,
        "receipt_no": receipt_no,
        "store": parsed.get("store"),
        "date": parsed.get("date"),
        "items": added,
        "hon": hon_result,
    }


async def price_trend(name: str) -> dict[str, Any]:
    """Price history for a product (newest first) — track price changes over time."""
    q = (name or "").strip()
    if not q:
        raise ToolError("which product?")
    rows = await asyncio.to_thread(db.price_trend, q, 20)
    if not rows:
        raise ToolError(f"no price history found for '{q}'")
    prices = [r["price"] for r in rows]
    return {
        "name": q,
        "latest": rows[0]["price"],
        "latest_date": rows[0]["bought_on"],
        "min": min(prices),
        "max": max(prices),
        "avg": round(sum(prices) / len(prices), 2),
        "history": rows,
    }


# ---------------------------------------------------------------------------
# Folder watcher
# ---------------------------------------------------------------------------

def receipts_dir() -> Path:
    return Path(config.DB_PATH).resolve().parent / "receipts"


async def scan_receipts_folder() -> dict[str, Any]:
    """Import every new PDF in data/receipts/, moving results to processed/ or failed/."""
    inbox = receipts_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    processed = inbox / "processed"
    failed = inbox / "failed"
    processed.mkdir(exist_ok=True)
    failed.mkdir(exist_ok=True)

    results: list[dict[str, Any]] = []
    for pdf in sorted(inbox.glob("*.pdf")):
        try:
            result = await import_receipt(pdf.read_bytes(), filename=pdf.name)
            results.append({"file": pdf.name, **result})
            pdf.rename(processed / pdf.name)
        except ToolError as err:
            results.append({"file": pdf.name, "error": err.message})
            pdf.rename(failed / pdf.name)
        except Exception as err:  # noqa: BLE001 — never let one bad PDF stop the batch
            results.append({"file": pdf.name, "error": str(err)})
            pdf.rename(failed / pdf.name)

    return {"processed": results}


async def import_receipts() -> dict[str, Any]:
    """Voice tool: scan the receipts folder and import any new Coop receipts."""
    return await scan_receipts_folder()
