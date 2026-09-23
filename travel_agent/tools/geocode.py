"""Nominatim geocoding (no key). Proper User-Agent, 1 req/sec, in-memory cache."""
from __future__ import annotations

import time

import requests

_USER_AGENT = "travel-agent/1.0 (https://github.com/clinton-almeida-s/travel-agent)"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

_cache: dict[str, dict] = {}
_last_call: float = 0.0


def geocode(query: str) -> dict:
    """Resolve a place name to lat/lon. Returns {"error","hint"} on failure."""
    key = query.strip().lower()
    if key in _cache:
        return _cache[key]

    global _last_call
    wait = 1.0 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        _last_call = time.time()
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:  # network or HTTP error
        return {"error": f"Geocoding failed for '{query}': {exc}", "hint": "Check the place name and try again."}
    if not results:
        return {"error": f"No location found for '{query}'.", "hint": "Try a more specific place name."}
    top = results[0]
    out = {
        "query": query,
        "display_name": top.get("display_name", ""),
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
    }
    _cache[key] = out
    return out


def clear_cache() -> None:
    _cache.clear()
