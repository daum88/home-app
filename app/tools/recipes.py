"""Real recipes from TheMealDB (free, no API key) — no hOn dependency.

suggest_recipes() maps the current fridge inventory to English ingredients,
finds real recipes and returns full ingredient lists + step-by-step steps.
recipe_search() / recipe_detail() are exposed as standalone tools too.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from html import unescape
from typing import Any

import httpx

from .. import config, db
from . import local_inventory
from .base import ToolError

MEALDB = "https://www.themealdb.com/api/json/v1/1"

_DIACRITICS = str.maketrans("äöüõšž", "aouosz")


def _norm(text: str) -> str:
    return text.lower().translate(_DIACRITICS)


# Estonian receipt keyword → English ingredient for TheMealDB.
_INGREDIENT_MAP: list[tuple[str, str]] = [
    ("kohupiim", "cheese"), ("juust", "cheese"), ("kodujuust", "cheese"),
    ("hapukoor", "cream"), ("jogurt", "yogurt"), ("keefir", "yogurt"),
    ("või", "butter"), ("koor", "cream"), ("piim", "milk"), ("muna", "egg"),
    ("kana", "chicken"), ("kalkun", "turkey"), ("hakkliha", "beef"), ("liha", "beef"),
    ("lõhe", "salmon"), ("lohe", "salmon"), ("kala", "fish"), ("krevett", "shrimp"),
    ("õun", "apple"), ("oun", "apple"), ("arbuus", "watermelon"), ("laim", "lime"),
    ("banaan", "banana"), ("apelsin", "orange"), ("sidrun", "lemon"), ("pirn", "pear"),
    ("melon", "melon"), ("viinamari", "grape"), ("maasikas", "strawberry"),
    ("kartul", "potato"), ("porgand", "carrot"), ("sibul", "onion"),
    ("küüslauk", "garlic"), ("kuuslauk", "garlic"), ("tomat", "tomato"),
    ("kurk", "cucumber"), ("kapsas", "cabbage"), ("paprika", "pepper"),
    ("jahu", "flour"), ("suhkur", "sugar"), ("riis", "rice"), ("pasta", "pasta"),
    ("makaron", "pasta"), ("kaerahelbed", "oats"), ("helbed", "oats"), ("kaer", "oats"),
    ("müsli", "oats"), ("musli", "oats"), ("õli", "oil"), ("oli", "oil"),
    ("sool", "salt"), ("mesi", "honey"), ("mais", "corn"), ("popcorn", "corn"),
    ("kook", "cake"), ("leib", "bread"), ("sai", "bread"),
]


def _to_english(name: str) -> str | None:
    n = _norm(name)
    for keyword, english in _INGREDIENT_MAP:
        if keyword in n:
            return english
    return None


async def _get(path: str, params: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(MEALDB + path, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as err:
        raise ToolError(f"recipe service is unreachable ({err})") from err


def _summary(meal: dict) -> dict[str, Any]:
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "thumb": meal.get("strMealThumb"),
    }


def _detail(meal: dict) -> dict[str, Any]:
    ingredients: list[str] = []
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        if ing:
            ingredients.append(f"{measure} {ing}".strip())
    instructions = (meal.get("strInstructions") or "").replace("\r", "\n").replace("▢", "• ")
    instructions = "\n".join(line.strip() for line in instructions.split("\n") if line.strip())
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "thumb": meal.get("strMealThumb"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "ingredients": ingredients,
        "instructions": instructions,
    }


async def suggest_recipes() -> dict[str, Any]:
    """Suggest real recipes matching what's in the fridge."""
    inv = await local_inventory.list_items()
    items = inv.get("items") or []
    if not items:
        raise ToolError("your fridge is empty — add some items first")

    ingredients: list[str] = []
    for it in items:
        english = _to_english(it.get("name", ""))
        if english and english not in ingredients:
            ingredients.append(english)
    if not ingredients:
        raise ToolError("couldn't match any fridge items to recipe ingredients")

    # Collect recipe ideas for up to 5 ingredients (in parallel).
    ideas: dict[str, dict] = {}
    results = await asyncio.gather(
        *(_get("/filter.php", {"i": english}) for english in ingredients[:5]),
        return_exceptions=True,
    )
    for data in results:
        if isinstance(data, Exception):
            continue
        for meal in (data.get("meals") or [])[:4]:
            ideas[meal["idMeal"]] = meal
    if not ideas:
        raise ToolError("no recipes found")

    # Fetch full details for the top 3 (in parallel).
    async def detail(idea: dict) -> dict | None:
        try:
            data = await _get("/lookup.php", {"i": idea["idMeal"]})
            meals = data.get("meals") or []
            if meals:
                d = _detail(meals[0])
                d["instructions"] = d["instructions"][:900]
                return d
        except ToolError:
            return None
        return None

    details = [d for d in await asyncio.gather(*(detail(i) for i in list(ideas.values())[:3])) if d]

    return {"recipes": details, "matched_ingredients": ingredients}


async def recipe_search(query: str) -> dict[str, Any]:
    """Search recipes by name."""
    q = (query or "").strip()
    if not q:
        raise ToolError("what recipe should I search for?")
    data = await _get("/search.php", {"s": q})
    meals = data.get("meals") or []
    return {"results": [_summary(m) for m in meals[:10]]}


async def recipe_detail(meal_id: str) -> dict[str, Any]:
    """Get a recipe's full ingredients and step-by-step instructions."""
    meal_id = (meal_id or "").strip()
    if not meal_id:
        raise ToolError("give me a recipe id")
    data = await _get("/lookup.php", {"i": meal_id})
    meals = data.get("meals") or []
    if not meals:
        raise ToolError("recipe not found")
    d = _detail(meals[0])
    d["instructions"] = d["instructions"][:1500]
    return {"recipe": d}


# ---------------------------------------------------------------------------
# Saving + importing
# ---------------------------------------------------------------------------

async def save_recipe(meal_id: str) -> dict[str, Any]:
    """Save a TheMealDB recipe by id to your saved recipes."""
    data = await _get("/lookup.php", {"i": (meal_id or "").strip()})
    meals = data.get("meals") or []
    if not meals:
        raise ToolError("recipe not found")
    d = _detail(meals[0])
    await asyncio.to_thread(
        db.recipe_save,
        id=d["id"], name=d["name"], ingredients=d["ingredients"],
        instructions=d["instructions"], url="", thumb=d.get("thumb") or "", source="mealdb",
    )
    return {"saved": d["name"], "id": d["id"]}


async def saved_recipes() -> dict[str, Any]:
    """List your saved recipes."""
    items = await asyncio.to_thread(db.recipe_list)
    return {"recipes": items}


async def remove_saved_recipe(recipe_id: str) -> dict[str, Any]:
    """Remove a saved recipe by id."""
    await asyncio.to_thread(db.recipe_delete, (recipe_id or "").strip())
    return {"removed": True}


def _is_recipe(item: Any) -> bool:
    t = item.get("@type") if isinstance(item, dict) else None
    return t == "Recipe" or (isinstance(t, list) and "Recipe" in t)


def _parse_jsonld(recipe: dict) -> dict[str, Any]:
    name = recipe.get("name") or recipe.get("headline") or "Untitled recipe"
    ingredients = recipe.get("recipeIngredient") or []
    raw = recipe.get("recipeInstructions") or []
    if isinstance(raw, str):
        instructions = raw
    else:
        steps = []
        for s in raw:
            if isinstance(s, dict):
                steps.append(s.get("text") or s.get("name") or "")
            else:
                steps.append(str(s))
        instructions = "\n".join(steps)
    thumb = ""
    image = recipe.get("image")
    if isinstance(image, list) and image:
        thumb = image[0].get("url") if isinstance(image[0], dict) else str(image[0])
    elif isinstance(image, dict):
        thumb = image.get("url") or ""
    return {"name": name, "ingredients": ingredients, "instructions": instructions, "thumb": thumb}


def _extract_jsonld(html: str) -> dict[str, Any] | None:
    for m in re.finditer(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                if _is_recipe(item):
                    return _parse_jsonld(item)
                for g in item.get("@graph") or []:
                    if _is_recipe(g):
                        return _parse_jsonld(g)
    return None


def _extract_naminami(page: str) -> dict[str, Any] | None:
    """Parse nami-nami.ee-style recipe pages: ingredients and steps are plain <p> blocks."""
    koostis = re.search(r"<h3[^>]*>\s*Koostisosad\s*</h3>", page)
    valm = re.search(r"<h3[^>]*>\s*Valmistamine\s*</h3>", page)
    if not koostis or not valm:
        return None

    def paragraphs(start: int, end: int) -> list[str]:
        out: list[str] = []
        for m in re.finditer(r"<(?:p|strong|h4)\b[^>]*>(.*?)</(?:p|strong|h4)>", page[start:end], re.S):
            text = re.sub(r"<[^>]+>", "", m.group(1))
            text = unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                out.append(text)
        return out

    ingredients = paragraphs(koostis.end(), valm.start())
    # Merge "Section:" header lines with the following ingredient.
    merged: list[str] = []
    for ing in ingredients:
        if merged and merged[-1].endswith(":"):
            merged[-1] = f"{merged[-1]} {ing}"
        else:
            merged.append(ing)
    ingredients = merged
    next_h3 = re.search(r"<h3[^>]*>", page[valm.end():])
    instr_end = valm.end() + next_h3.start() if next_h3 else len(page)
    steps = paragraphs(valm.end(), instr_end)

    if not ingredients or not steps:
        return None

    name = ""
    og = re.search(r"""<meta[^>]*property=["']og:title["'][^>]*content=["']([^"']+)""", page)
    if og:
        name = unescape(og.group(1)).strip()
    if not name:
        tm = re.search(r"<title[^>]*>(.*?)</title>", page, re.S)
        if tm:
            name = unescape(re.sub(r"<[^>]+>", "", tm.group(1))).strip()
    name = re.split(r"\s*[|–—]\s*", name)[0]
    name = re.sub(r"^Nami-Nami\s*[-:–]?\s*", "", name).strip()
    if not name:
        name = "Nami-Nami retsept"

    return {"name": name, "ingredients": ingredients, "instructions": "\n".join(steps), "thumb": ""}


def _norm_instructions(data: dict) -> str:
    """Accept instructions as either a list of steps or a single string."""
    instr = data.get("instructions") or ""
    if isinstance(instr, list):
        return "\n".join(str(s).strip() for s in instr if str(s).strip())
    return str(instr)


async def _extract_with_llm(html: str) -> dict[str, Any] | None:
    from .. import llm  # noqa: PLC0415 — lazy, avoid circular import

    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)[:6000]
    prompt = (
        "Extract the recipe from this web page text. Reply with JSON only: "
        '{"name": "...", "ingredients": ["..."], "instructions": ["step 1", "step 2"]}. '
        "Put each cooking step as its own array item, in order. "
        'If there is no recipe, reply {"error": "no recipe"}.\n\n' + text
    )
    reply = await llm.chat([{"role": "user", "content": prompt}], tools=[])
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not data.get("name") or data.get("error"):
        return None
    return {
        "name": data["name"],
        "ingredients": data.get("ingredients") or [],
        "instructions": _norm_instructions(data),
        "thumb": "",
    }


async def import_recipe(url: str) -> dict[str, Any]:
    """Import a recipe from a URL and save it."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ToolError("that doesn't look like a link")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            })
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as err:
        raise ToolError(f"couldn't open that link ({err})") from err

    recipe = _extract_jsonld(html) or _extract_naminami(html) or await _extract_with_llm(html)
    if recipe is None:
        raise ToolError("I couldn't find a recipe on that page")

    rid = "url:" + hashlib.sha1(url.encode()).hexdigest()[:12]
    await asyncio.to_thread(
        db.recipe_save,
        id=rid, name=recipe["name"], ingredients=recipe["ingredients"],
        instructions=recipe["instructions"], url=url, thumb=recipe.get("thumb", ""), source="url",
    )
    return {"saved": recipe["name"], "id": rid, "url": url}


async def _parse_text_with_llm(text: str) -> dict[str, Any]:
    from .. import llm  # noqa: PLC0415 — lazy, avoid circular import

    prompt = (
        "Extract the recipe from this text. Reply with JSON only: "
        '{"name": "...", "ingredients": ["..."], "instructions": ["step 1", "step 2"]}. '
        "Put each cooking step as its own array item, in order. "
        'If there is no recipe, reply {"error": "no recipe"}.\n\n' + text[:6000]
    )
    reply = await llm.chat([{"role": "user", "content": prompt}], tools=[])
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        raise ToolError("couldn't parse that text into a recipe")
    try:
        data = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        raise ToolError("couldn't parse that text into a recipe")
    if not data.get("name") or data.get("error"):
        raise ToolError("that text doesn't look like a recipe")
    return {
        "name": data["name"],
        "ingredients": data.get("ingredients") or [],
        "instructions": _norm_instructions(data),
    }


async def import_recipe_text(text: str) -> dict[str, Any]:
    """Import a recipe from pasted text (parsed by the LLM) and save it."""
    text = (text or "").strip()
    if not text:
        raise ToolError("paste the recipe text first")
    recipe = await _parse_text_with_llm(text)
    rid = "text:" + hashlib.sha1(text.encode()).hexdigest()[:12]
    await asyncio.to_thread(
        db.recipe_save,
        id=rid, name=recipe["name"], ingredients=recipe["ingredients"],
        instructions=recipe["instructions"], url="", thumb="", source="text",
    )
    return {"saved": recipe["name"], "id": rid, "recipe": recipe}


async def update_recipe(
    recipe_id: str,
    name: str | None = None,
    ingredients: list[str] | None = None,
    instructions: str | None = None,
) -> dict[str, Any]:
    """Edit a saved recipe's name, ingredients and/or instructions."""
    rid = (recipe_id or "").strip()
    if not rid:
        raise ToolError("which recipe?")
    existing = await asyncio.to_thread(db.recipe_get, rid)
    if existing is None:
        raise ToolError("recipe not found")
    new_name = (name or "").strip() or existing.get("name") or "Untitled"
    new_ingredients = ingredients if ingredients is not None else existing.get("ingredients") or []
    new_instructions = instructions if instructions is not None else existing.get("instructions") or ""
    await asyncio.to_thread(
        db.recipe_save,
        id=rid, name=new_name, ingredients=new_ingredients,
        instructions=new_instructions,
        url=existing.get("url") or "", thumb=existing.get("thumb") or "",
        source=existing.get("source") or "",
    )
    return {"updated": True, "id": rid, "name": new_name}
