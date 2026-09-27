"""hOn "Smart Inventory" — the fridge food list in the Haier hOn app.

Reverse-engineered from the hOn iOS app (traffic captured 2026-09). This is a
**separate cloud feature** from the fridge's control attributes, which is why it
is not in pyhOn. Auth reuses pyhOn's login — the same ``cognito-token`` /
``id-token`` headers the app sends.

Endpoints (verified live):
- GET    {INV}/{mac}/items?orderBy=recentlyAdded   → list items
- POST   {INV}/{mac}/item                          → add item
- DELETE {INV}/item/{itemId}                       → remove item
- GET    {INV}/user-categories / positions / tags / macro-category → lookups

Category mapping: hOn's item types are numeric ids behind translation keys
(e.g. ``REF.SMART_INVENTORY.MILK`` → id 493). We fetch the taxonomy at runtime
and match receipt names to specific categories via Estonian keyword rules; the
hardcoded ids below are only a fallback if that fetch fails.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from .. import config
from .base import ToolError

log = logging.getLogger(__name__)

# Auth token cache — pyhOn's login is slow (~5-15s); tokens last ~8h, so reuse them.
_auth_cache: dict[str, Any] = {"mac": None, "tokens": None}


def invalidate_cache() -> None:
    _auth_cache["mac"] = None
    _auth_cache["tokens"] = None


API = "https://api-iot.he.services"
INV = f"{API}/inventory/v1/smart-inventory"

USER_AGENT = "hOn/2 (HomeVoiceAssistant)"

_DIACRITICS = str.maketrans("äöüõšž", "aouosz")


def _norm(text: str) -> str:
    return text.lower().translate(_DIACRITICS)


# Verified position ids from GET /positions.
POSITIONS = {"fridge": 2024687, "freezer": 2024686, "pantry": 2024688}
POSITION_NAMES = {v: k for k, v in POSITIONS.items()}

# Where each shelf-life category usually lives.
CATEGORY_POSITION: dict[str, str] = {
    "dairy": "fridge",
    "eggs": "fridge",
    "bakery": "fridge",
    "meat & fish": "fridge",
    "fruit & veg": "fridge",
    "pantry": "pantry",
    "drinks": "pantry",
    "snacks": "pantry",
}

# ---------------------------------------------------------------------------
# Fine-grained item-type rules: Estonian keyword → hOn category NAME (translation
# key suffix, e.g. "MILK"). Order matters — specific/ambiguous words come first.
# Names that don't resolve as a leaf are looked up as a macro-category instead.
# ---------------------------------------------------------------------------
_KEYWORD_RULES: list[tuple[str, str]] = [
    # snacks & desserts first (so "popcorn … juustu" is a snack, not cheese)
    ("popcorn", "COOKIES"),
    ("krõps", "COOKIES"), ("krops", "COOKIES"),
    ("küpsis", "COOKIES"), ("kupsis", "COOKIES"),
    ("šokolaad", "CHOCOLATE"), ("sokolaad", "CHOCOLATE"),
    ("jäätis", "ICE_CREAM"), ("jaatis", "ICE_CREAM"),
    ("komm", "CHOCOLATE"),
    # bakery
    ("sepik", "BREAD"), ("kukkel", "BREAD"), ("sai", "BREAD"), ("leib", "BREAD"),
    # eggs
    ("muna", "EGGS"),
    # meat & fish
    ("kana", "CHICKEN"), ("kalkun", "CHICKEN"),
    ("lõhe", "FISH"), ("lohe", "FISH"), ("kala", "FISH"), ("krevett", "FISH"),
    ("viiner", "SAUSAGES"), ("vorst", "SAUSAGES"), ("salaami", "SALAMI"),
    ("peekon", "BACON"), ("sink", "HAM"),
    ("hakkliha", "MEAT"), ("liha", "MEAT"),
    # fruit & veg (specific first)
    ("õun", "APPLES"), ("oun", "APPLES"),
    ("kartul", "POTATOES"), ("porgand", "CARROTS"),
    ("sibul", "ONIONS"), ("küüslauk", "GARLIC"), ("kuuslauk", "GARLIC"),
    ("arbuus", "FRUITS"), ("laim", "FRUITS"), ("banaan", "FRUITS"),
    ("apelsin", "FRUITS"), ("sidrun", "FRUITS"), ("pirn", "FRUITS"),
    ("viinamari", "FRUITS"), ("melon", "FRUITS"),
    ("tomat", "VEGETABLES"), ("kurk", "VEGETABLES"), ("kapsas", "VEGETABLES"),
    ("salat", "VEGETABLES"), ("paprika", "VEGETABLES"), ("brokoli", "VEGETABLES"),
    # pantry
    ("jahu", "FLOURS"), ("suhkur", "SUGAR"), ("riis", "RICE"),
    ("makaron", "PASTA"), ("pasta", "PASTA"),
    ("kaerahelbed", "OATS"), ("helbed", "OATS"), ("helvest", "OATS"),
    ("kaer", "OATS"), ("müsli", "OATS"), ("musli", "OATS"),
    ("õli", "OIL"), ("oli", "OIL"), ("sool", "SALT"), ("mesi", "HONEY"),
    # dairy
    ("kohupiim", "CHEESE"), ("kodujuust", "CHEESE"), ("juust", "CHEESE"),
    ("hapukoor", "CREAMS"), ("keefir", "YOGURT"), ("jogurt", "YOGURT"),
    ("või", "BUTTER"), ("voi", "BUTTER"),
    ("koor", "CREAMS"), ("piim", "MILK"),
    # drinks
    ("õlu", "BEERS"), ("olu", "BEERS"), ("vein", "WINES"),
    ("kohv", "COFFEE"), ("vesi", "WATER"), ("mahl", "WATER"), ("limonaad", "WATER"),
]

# shelf-life category → fallback hOn category NAME.
_CATEGORY_FALLBACK: dict[str, str] = {
    "dairy": "MILK",
    "eggs": "EGGS",
    "bakery": "BREAD",
    "meat & fish": "MEAT",
    "fruit & veg": "VEGETABLES",
    "pantry": "PASTA",
    "drinks": "WATER",
    "snacks": "COOKIES",
}

# Hardcoded ids used only if the runtime taxonomy fetch fails.
CATEGORY_IDS: dict[str, int] = {
    "dairy": 493,
    "eggs": 116,
    "bakery": 43,
    "meat & fish": 96,
    "fruit & veg": 338,
    "pantry": 218,
    "drinks": 346,
    "snacks": 93,
}


def _category_id_fallback(category: str) -> int:
    return CATEGORY_IDS.get(category, 381)  # 381 = OTHER


def _position_for(name: str, category: str) -> str:
    n = _norm(name)
    if "jäätis" in n or "jaatis" in n:
        return "freezer"
    return CATEGORY_POSITION.get(category, "fridge")


def _unit_and_quantity(qty: float | None) -> tuple[str, float]:
    """Guess a sensible unit/quantity from the receipt line.

    Weighed produce has a fractional quantity (0.238 kg of apples). hOn stores
    integer quantities only (verified), so we convert weighed amounts to grams:
    0.238 kg → 238 g. Packaged goods keep an integer count (1 carton of milk).
    """
    q = float(qty or 1)
    if q < 1 or (q % 1) != 0:  # fractional → weighed
        return "g", round(q * 1000)
    return "pz", float(int(q))


def _fmt_expiry(expires_on: str | None) -> str | None:
    """ISO 'YYYY-MM-DD' → hOn's 'YYYY/MM/DD'."""
    if not expires_on:
        return None
    try:
        return date.fromisoformat(expires_on).strftime("%Y/%m/%d")
    except ValueError:
        return None


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {
        "cognito-token": tokens["cognito-token"],
        "id-token": tokens["id-token"],
        "user-agent": USER_AGENT,
        "accept": "application/json",
        "content-type": "application/json",
    }


def _fridge_mac(hon: Any) -> str:
    for appliance in hon.appliances:
        if appliance.appliance_type == "REF":
            return appliance.mac_address
    if hon.appliances:
        return hon.appliances[0].mac_address
    raise ToolError("no fridge found on your hOn account")


async def _authenticate() -> tuple[str, dict[str, str]]:
    """Return (mac, auth headers), reusing cached tokens when possible."""
    if _auth_cache["tokens"]:
        return _auth_cache["mac"], _auth_cache["tokens"]

    if not (config.HON_USER and config.HON_PASS):
        raise ToolError("the hOn fridge inventory isn't configured — add HON_USER and HON_PASS")
    from pyhon import Hon  # noqa: PLC0415 — lazy, isolated
    from pyhon.exceptions import NoAuthenticationException  # noqa: PLC0415

    try:
        async with Hon(config.HON_USER, config.HON_PASS) as hon:
            mac = _fridge_mac(hon)
            tokens = {
                "cognito-token": hon.api.auth.cognito_token,
                "id-token": hon.api.auth.id_token,
            }
    except NoAuthenticationException:
        raise ToolError("the hOn fridge inventory is offline — hOn login failed") from None
    except ToolError:
        raise
    except Exception as err:  # noqa: BLE001 — fragile cloud API
        raise ToolError(f"the hOn fridge inventory is offline ({err})") from err

    _auth_cache["mac"] = mac
    _auth_cache["tokens"] = tokens
    return mac, tokens


# ---------------------------------------------------------------------------
# Category taxonomy
# ---------------------------------------------------------------------------

async def _fetch_categories(tokens: dict[str, str]) -> list[dict[str, Any]]:
    url = f"{INV}/user-categories"
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
        resp = await client.get(url, headers=_headers(tokens))
    resp.raise_for_status()
    return (resp.json().get("payload") or {}).get("items") or []


def _build_maps(items: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (leaf name → id, macro name → id) from the taxonomy."""
    leaf: dict[str, int] = {}
    macro: dict[str, int] = {}
    for it in items:
        leaf_name = str(it.get("category", "")).replace("REF.SMART_INVENTORY.", "")
        macro_name = str(it.get("macrocategory", "")).replace("REF.SMART_INVENTORY.", "")
        if leaf_name and leaf_name not in leaf:
            leaf[leaf_name] = int(it["id"])
        if macro_name and macro_name not in macro:
            macro[macro_name] = int(it["id"])
    return leaf, macro


def _lookup(name: str, leaf: dict[str, int], macro: dict[str, int]) -> int | None:
    if name in leaf:
        return leaf[name]
    if name in macro:
        return macro[name]
    return None


def _resolve_category_id(
    name: str, category: str, leaf: dict[str, int], macro: dict[str, int]
) -> int:
    """Map a receipt line to a hOn category id via keyword rules."""
    n = _norm(name)
    for keyword, hon_name in _KEYWORD_RULES:
        if keyword in n:
            if (cid := _lookup(hon_name, leaf, macro)) is not None:
                return cid
            break  # keyword matched but name unknown → fall through to fallback
    if (cid := _lookup(_CATEGORY_FALLBACK.get(category, ""), leaf, macro)) is not None:
        return cid
    return _category_id_fallback(category)


# ---------------------------------------------------------------------------
# HTTP primitives (tokens injected so they can be tested without pyhOn)
# ---------------------------------------------------------------------------

async def _list_items(mac: str, tokens: dict[str, str]) -> list[dict[str, Any]]:
    url = f"{INV}/{mac}/items?orderBy=recentlyAdded"
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
        resp = await client.get(url, headers=_headers(tokens))
    if resp.status_code == 401:
        invalidate_cache()
        raise ToolError("hOn session expired — try again")
    resp.raise_for_status()
    return (resp.json().get("payload") or {}).get("items") or []


async def _add_item(mac: str, tokens: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{INV}/{mac}/item"
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
        resp = await client.post(url, headers=_headers(tokens), json=payload)
    if resp.status_code == 401:
        invalidate_cache()
        raise ToolError("hOn session expired — try again")
    resp.raise_for_status()
    return resp.json().get("payload") or {}


async def _remove_item(tokens: dict[str, str], item_id: int) -> None:
    url = f"{INV}/item/{item_id}"
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
        resp = await client.delete(url, headers=_headers(tokens))
    if resp.status_code == 401:
        invalidate_cache()
        raise ToolError("hOn session expired — try again")
    resp.raise_for_status()


def _build_payload(
    name: str,
    category_id: int,
    qty: float | None,
    expires_on: str | None,
    note: str = "",
    position: str | None = None,
) -> dict[str, Any]:
    unit, quantity = _unit_and_quantity(qty)
    return {
        "name": name,
        "category": category_id,
        "unit": unit,
        "quantity": quantity,
        "unitQuantity": 1,
        "expirationDate": _fmt_expiry(expires_on) or date.today().strftime("%Y/%m/%d"),
        "note": note,
        "preservationType": position,
        "tags": [],
        "positionId": POSITIONS[position],
    }


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------

async def list_items() -> dict[str, Any]:
    """List everything currently in the hOn fridge inventory."""
    mac, tokens = await _authenticate()
    items = await _list_items(mac, tokens)
    return {
        "items": [
            {
                "id": it.get("id"),
                "name": it.get("name"),
                "quantity": it.get("quantity"),
                "unit": it.get("unit"),
                "expires_on": (it.get("expirationDate") or "")[:10],
                "position": POSITION_NAMES.get(it.get("positionId"), "fridge"),
            }
            for it in items
        ]
    }


async def add_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Add a batch of items. Each item:
    {name, category, qty, expires_on, note?, position?} — category is one of
    our shelf-life categories (dairy, eggs, …). Authenticates once."""
    mac, tokens = await _authenticate()

    leaf: dict[str, int] = {}
    macro: dict[str, int] = {}
    try:
        leaf, macro = _build_maps(await _fetch_categories(tokens))
    except Exception as err:  # noqa: BLE001 — fall back to hardcoded ids
        log.warning("couldn't fetch hOn categories, using fallback ids: %s", err)

    results: list[dict[str, Any]] = []
    for item in items:
        name = item["name"]
        category = item["category"]
        category_id = _resolve_category_id(name, category, leaf, macro)
        position = item.get("position") or _position_for(name, category)
        payload = _build_payload(
            name=name,
            category_id=category_id,
            qty=item.get("qty"),
            expires_on=item.get("expires_on"),
            note=item.get("note", ""),
            position=position,
        )
        try:
            result = await _add_item(mac, tokens, payload)
            results.append({"name": name, "ok": True, "item_id": result.get("itemId")})
        except ToolError as err:
            results.append({"name": name, "ok": False, "error": err.message})
    return {"added": results}


async def add_item(
    name: str,
    qty: float = 1,
    expires_on: str | None = None,
    note: str = "",
    position: str | None = None,
) -> dict[str, Any]:
    """Add a single item. Its hOn category is derived from the name."""
    result = await add_items(
        [{"name": name, "category": "other", "qty": qty, "expires_on": expires_on, "note": note, "position": position}]
    )
    added = result.get("added") or []
    if not added:
        return {"ok": False, "error": "nothing added"}
    first = added[0]
    if not first.get("ok"):
        raise ToolError(first.get("error") or "couldn't add item")
    return first


async def remove_item(item_id: int) -> dict[str, Any]:
    """Remove one item from the hOn fridge inventory by id."""
    _mac_unused, tokens = await _authenticate()
    await _remove_item(tokens, int(item_id))
    return {"removed": True, "item_id": int(item_id)}
