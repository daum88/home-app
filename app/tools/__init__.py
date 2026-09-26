"""Tool registry.

Maps a tool name to ``{name, description, parameters, handler}``. The LLM only
ever sees the schemas; Python executes handlers and validates the boundary.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from . import transmission, washer, search, fridge, ventilation, inventory, receipts, hon_inventory, files, email_receipts, recipes, weather, shopping, kodi, electricity, barcode, spending, jellyfin
from .. import letterboxd
from .base import ToolError, fail, ok

log = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[dict[str, Any]]]


def _tool(name: str, description: str, parameters: dict[str, Any], handler: Handler) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
    }


_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}}


TOOLS: dict[str, dict[str, Any]] = {
    # --- Torrents (Transmission) ---
    "list_torrents": _tool(
        "list_torrents",
        "List all torrents with name, progress %, ETA and status.",
        _NO_ARGS,
        transmission.list_torrents,
    ),
    "add_torrent": _tool(
        "add_torrent",
        "Add a torrent to Transmission from a magnet URI or http(s) torrent URL.",
        {
            "type": "object",
            "properties": {
                "magnet_uri": {"type": "string", "description": "The magnet link or torrent URL."}
            },
            "required": ["magnet_uri"],
        },
        transmission.add_torrent,
    ),
    "torrent_status": _tool(
        "torrent_status",
        "Get the status of a single torrent by name substring.",
        {
            "type": "object",
            "properties": {"name_substr": {"type": "string", "description": "Part of the torrent name."}},
            "required": ["name_substr"],
        },
        transmission.torrent_status,
    ),
    "torrent_remove": _tool(
        "torrent_remove",
        "Remove a torrent by name substring (optionally delete its data).",
        {
            "type": "object",
            "properties": {
                "name_substr": {"type": "string", "description": "Part of the torrent name."},
                "delete_data": {"type": "boolean", "description": "Also delete downloaded files."},
            },
            "required": ["name_substr"],
        },
        transmission.torrent_remove,
    ),
    "torrent_pause": _tool(
        "torrent_pause",
        "Pause a torrent by its numeric id.",
        {
            "type": "object",
            "properties": {"torrent_id": {"type": "integer", "description": "The torrent id from list_torrents."}},
            "required": ["torrent_id"],
        },
        transmission.torrent_pause,
    ),
    "torrent_resume": _tool(
        "torrent_resume",
        "Resume (start) a paused torrent by its numeric id.",
        {
            "type": "object",
            "properties": {"torrent_id": {"type": "integer", "description": "The torrent id from list_torrents."}},
            "required": ["torrent_id"],
        },
        transmission.torrent_resume,
    ),
    "torrent_delete": _tool(
        "torrent_delete",
        "Delete a torrent by its numeric id, optionally deleting the downloaded files too.",
        {
            "type": "object",
            "properties": {
                "torrent_id": {"type": "integer", "description": "The torrent id from list_torrents."},
                "delete_data": {"type": "boolean", "description": "Also delete the downloaded files."},
            },
            "required": ["torrent_id"],
        },
        transmission.torrent_delete,
    ),
    "search_torrents": _tool(
        "search_torrents",
        "Search torrent indexers (Prowlarr) for a title. Returns the top releases with magnet links.",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Movie/show title to search."}},
            "required": ["query"],
        },
        search.search_torrents,
    ),
    # --- Washer (SmartThings) ---
    "washer_status": _tool(
        "washer_status",
        "Get the Samsung washer state: running/stopped, progress, minutes remaining, cycle.",
        _NO_ARGS,
        washer.washer_status,
    ),
    "washer_start": _tool(
        "washer_start",
        "Start the washer. Only works after the Smart Control button was pressed on the machine.",
        _NO_ARGS,
        washer.washer_start,
    ),
    "washer_stop": _tool(
        "washer_stop",
        "Stop/cancel the current wash.",
        _NO_ARGS,
        washer.washer_stop,
    ),
    "washer_pause": _tool(
        "washer_pause",
        "Pause the current wash.",
        _NO_ARGS,
        washer.washer_pause,
    ),
    # --- Fridge (hOn) ---
    "fridge_status": _tool(
        "fridge_status",
        "Get the Haier fridge and freezer temperatures, door state, super cool/freeze.",
        _NO_ARGS,
        fridge.fridge_status,
    ),
    "fridge_set_temp": _tool(
        "fridge_set_temp",
        "Set the fridge or freezer target temperature.",
        {
            "type": "object",
            "properties": {
                "zone": {"type": "string", "description": "'fridge' or 'freezer'."},
                "celsius": {"type": "number", "description": "Target temperature in °C."},
            },
            "required": ["zone", "celsius"],
        },
        fridge.fridge_set_temp,
    ),
    # --- Ventilation (SaveConnect 2.0) ---
    "ventilation_status": _tool(
        "ventilation_status",
        "Get ventilation temperatures, humidity, CO2, fan speeds, mode and filter days left.",
        _NO_ARGS,
        ventilation.ventilation_status,
    ),
    "ventilation_set": _tool(
        "ventilation_set",
        "Set fan speed (off/low/normal/high) or user mode (auto/manual/crowded/refresh/fireplace/away/holiday).",
        {
            "type": "object",
            "properties": {"level": {"type": "string", "description": "Fan speed or mode keyword."}},
            "required": ["level"],
        },
        ventilation.ventilation_set,
    ),
    "ventilation_set_temp": _tool(
        "ventilation_set_temp",
        "Set the ventilation supply-air temperature setpoint (12.0–30.0 °C).",
        {
            "type": "object",
            "properties": {"celsius": {"type": "number", "description": "Setpoint in °C."}},
            "required": ["celsius"],
        },
        ventilation.ventilation_set_temp,
    ),
    # --- Inventory (Open Food Facts + SQLite) ---
    "inventory_add": _tool(
        "inventory_add",
        "Look up a barcode on Open Food Facts and store it in the inventory with an expiry date.",
        {
            "type": "object",
            "properties": {
                "barcode": {"type": "string", "description": "EAN/UPC barcode digits."},
                "expires": {"type": "string", "description": "Expiry as a date or 'friday' / 'in 5 days'."},
                "name": {"type": "string", "description": "Product name, if the barcode is unknown."},
            },
            "required": ["barcode"],
        },
        inventory.inventory_add,
    ),
    "inventory_list": _tool(
        "inventory_list",
        "List everything in the fridge inventory with expiry info.",
        _NO_ARGS,
        inventory.inventory_list,
    ),
    "inventory_expiring": _tool(
        "inventory_expiring",
        "List inventory items expiring within the next N days (default 3).",
        {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Look-ahead window in days."}},
        },
        inventory.inventory_expiring,
    ),
    "import_receipts": _tool(
        "import_receipts",
        "Scan the receipts folder and import any new Coop e-receipt PDFs into the fridge inventory.",
        _NO_ARGS,
        receipts.import_receipts,
    ),
    "fridge_inventory_list": _tool(
        "fridge_inventory_list",
        "List the items currently in the hOn fridge inventory (name, quantity, expiry, position).",
        _NO_ARGS,
        hon_inventory.list_items,
    ),
    "fridge_inventory_add": _tool(
        "fridge_inventory_add",
        "Add one item to the hOn fridge inventory (category is guessed from the name).",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Item name, e.g. 'Piim 2.5%'."},
                "qty": {"type": "number", "description": "Quantity (1 = one package; fractional = kg)."},
                "expires_on": {"type": "string", "description": "Expiry date as YYYY-MM-DD."},
                "position": {"type": "string", "enum": ["fridge", "freezer", "pantry"]},
            },
            "required": ["name"],
        },
        hon_inventory.add_item,
    ),
    "fridge_inventory_remove": _tool(
        "fridge_inventory_remove",
        "Remove one item from the hOn fridge inventory by its id.",
        {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
        },
        hon_inventory.remove_item,
    ),
    # --- Local filesystem (hard drive) ---
    "list_files": _tool(
        "list_files",
        "List the contents of a folder on this computer. Use '.' or a relative/absolute path.",
        {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Folder path, e.g. 'Documents' or '.'"}},
        },
        files.list_files,
    ),
    "read_file": _tool(
        "read_file",
        "Read the text of a file on this computer (size-capped).",
        {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        },
        files.read_file,
    ),
    "search_files": _tool(
        "search_files",
        "Search this computer for files by name or text content.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for in file names and contents"},
                "path": {"type": "string", "description": "Folder to search in (defaults to home)"},
            },
            "required": ["query"],
        },
        files.search_files,
    ),
    "disk_usage": _tool(
        "disk_usage",
        "Get free / used / total space on the media drive in GB.",
        _NO_ARGS,
        files.disk_usage,
    ),
    "check_email_receipts": _tool(
        "check_email_receipts",
        "Check the configured email inbox for new Coop receipt PDFs and import them.",
        _NO_ARGS,
        email_receipts.check_email_receipts,
    ),
    "suggest_recipes": _tool(
        "suggest_recipes",
        "Suggest real recipes to cook from what's currently in the fridge (with ingredients and steps).",
        _NO_ARGS,
        recipes.suggest_recipes,
    ),
    "recipe_search": _tool(
        "recipe_search",
        "Search real recipes by name.",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Recipe name or dish to search for."}},
            "required": ["query"],
        },
        recipes.recipe_search,
    ),
    "recipe_detail": _tool(
        "recipe_detail",
        "Get a recipe's full ingredients and step-by-step instructions by id.",
        {
            "type": "object",
            "properties": {"meal_id": {"type": "string", "description": "The recipe id from search or suggestions."}},
            "required": ["meal_id"],
        },
        recipes.recipe_detail,
    ),
    "save_recipe": _tool(
        "save_recipe",
        "Save a TheMealDB recipe to the user's saved recipes by its id.",
        {
            "type": "object",
            "properties": {"meal_id": {"type": "string", "description": "The recipe id."}},
            "required": ["meal_id"],
        },
        recipes.save_recipe,
    ),
    "import_recipe": _tool(
        "import_recipe",
        "Import a recipe from a web link and save it.",
        {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The recipe URL."}},
            "required": ["url"],
        },
        recipes.import_recipe,
    ),
    "saved_recipes": _tool(
        "saved_recipes",
        "List the user's saved recipes.",
        _NO_ARGS,
        recipes.saved_recipes,
    ),
    "remove_saved_recipe": _tool(
        "remove_saved_recipe",
        "Remove a saved recipe by id.",
        {
            "type": "object",
            "properties": {"recipe_id": {"type": "string", "description": "The saved recipe id."}},
            "required": ["recipe_id"],
        },
        recipes.remove_saved_recipe,
    ),
    "import_recipe_text": _tool(
        "import_recipe_text",
        "Import a recipe from pasted text and save it (parsed into name, ingredients and steps).",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The full recipe text."}},
            "required": ["text"],
        },
        recipes.import_recipe_text,
    ),
    "update_recipe": _tool(
        "update_recipe",
        "Edit a saved recipe's name, ingredients or instructions.",
        {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string", "description": "The saved recipe id."},
                "name": {"type": "string", "description": "New title."},
                "ingredients": {"type": "array", "items": {"type": "string"}, "description": "New ingredient lines."},
                "instructions": {"type": "string", "description": "New step-by-step text."},
            },
            "required": ["recipe_id"],
        },
        recipes.update_recipe,
    ),
    # --- Weather (Open-Meteo) ---
    "weather_now": _tool(
        "weather_now",
        "Get the current weather at home.",
        _NO_ARGS,
        weather.weather_now,
    ),
    "weather_forecast": _tool(
        "weather_forecast",
        "Get the weather forecast for the next N days.",
        {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Number of days (1–7)."}},
        },
        weather.weather_forecast,
    ),
    # --- Shopping list ---
    "shopping_add": _tool(
        "shopping_add",
        "Add an item to the shopping list.",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Item to add."}},
            "required": ["name"],
        },
        shopping.shopping_add,
    ),
    "shopping_list": _tool(
        "shopping_list",
        "Show the shopping list.",
        _NO_ARGS,
        shopping.shopping_list,
    ),
    "shopping_remove": _tool(
        "shopping_remove",
        "Remove an item from the shopping list by id.",
        {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
        },
        shopping.shopping_remove,
    ),
    "shopping_clear": _tool(
        "shopping_clear",
        "Clear the whole shopping list.",
        _NO_ARGS,
        shopping.shopping_clear,
    ),
    # --- Kodi control ---
    "kodi_status": _tool(
        "kodi_status",
        "What's currently playing on Kodi (the TV box).",
        _NO_ARGS,
        kodi.kodi_status,
    ),
    "kodi_playpause": _tool(
        "kodi_playpause",
        "Pause or resume Kodi playback.",
        _NO_ARGS,
        kodi.kodi_playpause,
    ),
    "kodi_stop": _tool(
        "kodi_stop",
        "Stop Kodi playback.",
        _NO_ARGS,
        kodi.kodi_stop,
    ),
    "kodi_set_volume": _tool(
        "kodi_set_volume",
        "Set Kodi volume (0–100).",
        {
            "type": "object",
            "properties": {"level": {"type": "integer"}},
            "required": ["level"],
        },
        kodi.kodi_set_volume,
    ),
    "kodi_notify": _tool(
        "kodi_notify",
        "Show a notification on the TV (Kodi).",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["title"],
        },
        kodi.kodi_notify,
    ),
    "kodi_play_movie": _tool(
        "kodi_play_movie",
        "Play a movie from the Kodi library by name.",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Movie name."}},
            "required": ["name"],
        },
        kodi.kodi_play_movie,
    ),
    "electricity_price": _tool(
        "electricity_price",
        "Get the current Estonian electricity price and today's cheapest hours (cents/kWh).",
        _NO_ARGS,
        electricity.electricity_price,
    ),
    "lookup_barcode": _tool(
        "lookup_barcode",
        "Look up a product barcode (EAN) in Open Food Facts: name, brand, category, shelf life.",
        {
            "type": "object",
            "properties": {"barcode": {"type": "string", "description": "The EAN barcode digits."}},
            "required": ["barcode"],
        },
        barcode.lookup_barcode,
    ),
    "add_barcode_item": _tool(
        "add_barcode_item",
        "Look up a barcode and add the product to the fridge inventory with an estimated expiry date.",
        {
            "type": "object",
            "properties": {"barcode": {"type": "string", "description": "The EAN barcode digits."}},
            "required": ["barcode"],
        },
        barcode.add_barcode_item,
    ),
    "spending_stats": _tool(
        "spending_stats",
        "Get grocery spending: monthly totals, totals per store, and recent receipts.",
        _NO_ARGS,
        spending.spending_stats,
    ),
    "jellyfin_status": _tool(
        "jellyfin_status",
        "Get the Jellyfin media server name and version.",
        _NO_ARGS,
        jellyfin.jellyfin_status,
    ),
    "jellyfin_search": _tool(
        "jellyfin_search",
        "Search the Jellyfin movie and TV library by name.",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Movie or series title."}},
            "required": ["query"],
        },
        jellyfin.jellyfin_search,
    ),
    "jellyfin_recent": _tool(
        "jellyfin_recent",
        "List recently added movies and episodes in Jellyfin.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many to list (default 10)."}},
        },
        jellyfin.jellyfin_recent,
    ),
    "jellyfin_resume": _tool(
        "jellyfin_resume",
        "List Jellyfin items the user is part-way through watching.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many to list (default 10)."}},
        },
        jellyfin.jellyfin_resume,
    ),
    "jellyfin_library": _tool(
        "jellyfin_library",
        "List the Jellyfin library ('movie' or 'series').",
        {
            "type": "object",
            "properties": {"media_type": {"type": "string", "description": "'movie' or 'series'/'tv'."}},
        },
        jellyfin.jellyfin_library,
    ),
    "jellyfin_delete": _tool(
        "jellyfin_delete",
        "Delete a movie or series from disk (and refresh Jellyfin) by its item id.",
        {
            "type": "object",
            "properties": {"item_id": {"type": "string", "description": "The Jellyfin item id."}},
            "required": ["item_id"],
        },
        jellyfin.jellyfin_delete,
    ),
    "jellyfin_item_detail": _tool(
        "jellyfin_item_detail",
        "Get full details for one Jellyfin item: overview, cast, director, genres, codec.",
        {
            "type": "object",
            "properties": {"item_id": {"type": "string", "description": "The Jellyfin item id."}},
            "required": ["item_id"],
        },
        jellyfin.jellyfin_item_detail,
    ),
    "jellyfin_refresh": _tool(
        "jellyfin_refresh",
        "Trigger a Jellyfin library rescan.",
        _NO_ARGS,
        jellyfin.jellyfin_refresh,
    ),
    "jellyfin_stream_url": _tool(
        "jellyfin_stream_url",
        "Get a playable HLS stream URL for a movie (for in-app playback).",
        {
            "type": "object",
            "properties": {"item_id": {"type": "string", "description": "The Jellyfin item id."}},
            "required": ["item_id"],
        },
        jellyfin.jellyfin_stream_url,
    ),
    "jellyfin_download_url": _tool(
        "jellyfin_download_url",
        "Get a direct download URL for a movie's original file.",
        {
            "type": "object",
            "properties": {"item_id": {"type": "string", "description": "The Jellyfin item id."}},
            "required": ["item_id"],
        },
        jellyfin.jellyfin_download_url,
    ),
    "local_movies": _tool(
        "local_movies",
        "List movies by scanning the drive directly (no Jellyfin needed).",
        _NO_ARGS,
        jellyfin.local_movies,
    ),
    "jellyfin_episodes": _tool(
        "jellyfin_episodes",
        "List all episodes of a TV series (with season/episode numbers and paths).",
        {
            "type": "object",
            "properties": {"series_id": {"type": "string", "description": "The Jellyfin series id."}},
            "required": ["series_id"],
        },
        jellyfin.jellyfin_episodes,
    ),
    "sync_letterboxd": _tool(
        "sync_letterboxd",
        "Sync the Letterboxd watchlist now: add any new movies to Radarr for automatic download.",
        _NO_ARGS,
        letterboxd.sync_watchlist,
    ),
    "price_trend": _tool(
        "price_trend",
        "Get the price history for a product (newest first) to see how its price changed over time.",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Product name (e.g. piim, kohv)."}},
            "required": ["name"],
        },
        receipts.price_trend,
    ),
}


def get_schemas() -> list[dict[str, Any]]:
    """Return the LLM-facing tool schemas (OpenAI-style)."""
    return [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in TOOLS.values()
    ]


async def run_tool(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Execute a tool by name with the given arguments. Never raises.

    Success → ``{"ok": True, "data": {...}}``; failure → ``{"ok": False, "error": "..."}``.
    """
    entry = TOOLS.get(name)
    if entry is None:
        return fail(f"unknown tool '{name}'")
    try:
        data = await entry["handler"](**(args or {}))
        return ok(data)
    except ToolError as err:
        return fail(err.message)
    except TypeError as err:
        return fail(f"bad arguments for {name}: {err}")
    except Exception as err:  # noqa: BLE001 — one dead tool must never kill the agent
        log.exception("tool %s crashed", name)
        return fail(f"the {name.replace('_', ' ')} tool failed unexpectedly")
