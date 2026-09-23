"""Activities: Wikipedia geosearch (no key) as primary POI source,
with OpenTripMap as an optional enhancement when OPENTRIPMAP_API_KEY is set.
"""
from __future__ import annotations

import math

import requests

from ..config import settings
from .geocode import geocode

_WIKI_API = "https://en.wikipedia.org/w/api.php"
_OTM_API = "https://api.opentripmap.com/0.1/en/places/radius"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _wiki_pois(lat: float, lon: float, limit: int) -> list[dict]:
    """Nearby notable places via Wikipedia geosearch + extracts."""
    try:
        gs = requests.get(
            _WIKI_API,
            params={
                "action": "query",
                "list": "geosearch",
                "gscoord": f"{lat}|{lon}",
                "gsradius": 10000,
                "gslimit": max(limit * 2, 20),
                "format": "json",
            },
            headers={"User-Agent": "travel-agent/1.0"},
            timeout=15,
        )
        gs.raise_for_status()
        pages = gs.json().get("query", {}).get("geosearch", [])
    except Exception:
        return []
    if not pages:
        return []
    pageids = "|".join(str(p["pageid"]) for p in pages[:40])
    try:
        ex = requests.get(
            _WIKI_API,
            params={
                "action": "query",
                "pageids": pageids,
                "prop": "extracts|info",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 400,
                "inprop": "url",
                "format": "json",
            },
            headers={"User-Agent": "travel-agent/1.0"},
            timeout=15,
        )
        ex.raise_for_status()
        details = ex.json().get("query", {}).get("pages", {})
    except Exception:
        details = {}
    pois = []
    for p in pages:
        d = details.get(str(p["pageid"]), {})
        pois.append(
            {
                "name": p["title"],
                "description": (d.get("extract") or "").strip(),
                "url": d.get("fullurl") or f"https://en.wikipedia.org/?curid={p['pageid']}",
                "distance_km": round(p.get("dist", 0) / 1000, 1),
                "source": "wikipedia",
            }
        )
    return pois


def _otm_pois(lat: float, lon: float, interests: str, limit: int) -> list[dict]:
    """OpenTripMap radius search (only when API key configured)."""
    key = settings.opentripmap_api_key
    if not key:
        return []
    try:
        resp = requests.get(
            _OTM_API,
            params={
                "apikey": key,
                "lat": lat,
                "lon": lon,
                "radius": 10000,
                "limit": limit * 2,
                "rate": 2,
                "format": "json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception:
        return []
    pois = []
    for it in items if isinstance(items, list) else []:
        kinds = it.get("kinds", "")
        pois.append(
            {
                "name": it.get("name") or kinds.split(",")[0].replace("_", " ").title(),
                "description": f"Tags: {kinds}",
                "url": f"https://www.opentripmap.com/?xid={it.get('xid', '')}",
                "distance_km": round(_haversine_km(lat, lon, it.get("point", {}).get("lat", lat), it.get("point", {}).get("lon", lon)), 1),
                "source": "opentripmap",
                "kinds": kinds,
            }
        )
    return [p for p in pois if p["name"]]


def _interest_score(poi: dict, keywords: list[str]) -> int:
    text = f"{poi.get('name', '')} {poi.get('description', '')} {poi.get('kinds', '')}".lower()
    return sum(1 for kw in keywords if kw and kw in text)


def search_activities(
    location: str,
    interests: str,
    date: str | None = None,
    group_size: int = 1,
    max_results: int = 10,
) -> dict:
    """Find points of interest near a location, ranked by interests."""
    geo = geocode(location)
    if "error" in geo:
        return {"error": f"Activity search failed: {geo['error']}", "hint": geo.get("hint", "")}
    lat, lon = geo["lat"], geo["lon"]
    keywords = [k.strip().lower() for k in interests.replace("/", ",").split(",") if k.strip()]

    pois = _wiki_pois(lat, lon, max_results)
    pois += _otm_pois(lat, lon, interests, max_results)
    if not pois:
        return {
            "location": location,
            "activities": [],
            "note": "No notable places found nearby. Try a broader location name.",
        }
    for poi in pois:
        poi["match_score"] = _interest_score(poi, keywords)
    pois.sort(key=lambda p: (-p["match_score"], p["distance_km"]))
    return {
        "location": geo["display_name"],
        "date": date,
        "group_size": group_size,
        "activities": pois[: max(1, int(max_results))],
        "sources": sorted({p["source"] for p in pois}),
    }
