"""Hotels via LiteAPI (free sandbox key, no card required).

Flow: geocode the location -> GET /data/hotels (static list by coordinates)
-> POST /hotels/rates (live rates for those hotel ids).

Never invent prices or availability: on missing credentials or API errors
these functions return {"error", "hint"} dicts.
"""
from __future__ import annotations

import math

import requests

from ..config import settings
from .geocode import geocode

_BASE = "https://api.liteapi.travel/v3.0"

# LiteAPI requires a guest nationality (ISO-2) for pricing. The agent does
# not collect nationality, so default to the docs' canonical example.
_GUEST_NATIONALITY = "US"


def _headers() -> dict:
    return {
        "X-API-Key": settings.liteapi_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _api_error(resp: requests.Response, what: str) -> dict:
    if resp.status_code == 401:
        return {
            "error": "LiteAPI rejected the API key (401).",
            "hint": "Check LITEAPI_API_KEY in .env — sandbox keys start with sand_.",
        }
    return {
        "error": f"LiteAPI {what} failed (HTTP {resp.status_code}): {resp.text[:200]}",
        "hint": "Retry shortly.",
    }


def _data_list(resp: requests.Response) -> list:
    """Unwrap LiteAPI's {"data": [...]} envelope (or a bare list)."""
    payload = resp.json()
    if isinstance(payload, dict):
        inner = payload.get("data", [])
        return inner if isinstance(inner, list) else []
    return payload if isinstance(payload, list) else []


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
    try:
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(2 * r * math.asin(math.sqrt(a)), 1)
    except (TypeError, ValueError):
        return None


def _cheapest_rate(entry: dict) -> dict | None:
    """Cheapest bookable rate across all room types in a rates entry."""
    best = None
    for room in entry.get("roomTypes", []) or []:
        for rate in room.get("rates", []) or []:
            try:
                price = float(rate.get("price"))
            except (TypeError, ValueError):
                continue
            if best is None or price < best["price"]:
                best = {
                    "price": price,
                    "room": room.get("name"),
                    "board": rate.get("boardType") or rate.get("boardCode"),
                    "offer_id": room.get("offerId"),
                }
    return best


def search_hotels(
    location: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
    price_min: float | None = None,
    price_max: float | None = None,
    currency: str = "USD",
    amenities: list[str] | None = None,
    max_results: int = 5,
) -> dict:
    """Search live hotel offers near a location."""
    if not settings.liteapi_api_key:
        return {
            "error": "Hotel search unavailable: LITEAPI_API_KEY not set.",
            "hint": (
                "Sign up free at https://dashboard.liteapi.travel (no card), "
                "copy the sandbox key from Profile, and add it to .env."
            ),
        }
    geo = geocode(location)
    if "error" in geo:
        return {"error": f"Hotel search failed: {geo['error']}", "hint": geo.get("hint", "")}

    # 1. Static hotel list around the coordinates (radius in meters).
    try:
        resp = requests.get(
            f"{_BASE}/data/hotels",
            params={
                "latitude": geo["lat"],
                "longitude": geo["lon"],
                "radius": 20000,
                "limit": max(1, min(int(max_results) * 4, 40)),
            },
            headers=_headers(),
            timeout=30,
        )
    except Exception as exc:
        return {"error": f"Hotel list lookup failed: {exc}", "hint": "Retry shortly."}
    if resp.status_code >= 400:
        return _api_error(resp, "hotel list")
    hotels = _data_list(resp)
    if not hotels:
        return {"location": location, "hotels": [], "note": "No hotels found near this location."}
    by_id = {h.get("id"): h for h in hotels if h.get("id")}
    hotel_ids = list(by_id)[:20]

    # 2. Live rates for those hotels.
    body = {
        "hotelIds": hotel_ids,
        "checkin": check_in,
        "checkout": check_out,
        "currency": (currency or "USD").upper(),
        "guestNationality": _GUEST_NATIONALITY,
        "occupancies": [{"adults": max(int(guests), 1)}],
    }
    try:
        resp = requests.post(
            f"{_BASE}/hotels/rates", json=body, headers=_headers(), timeout=45
        )
    except Exception as exc:
        return {"error": f"Hotel rates lookup failed: {exc}", "hint": "Retry shortly."}
    if resp.status_code >= 400:
        return _api_error(resp, "rates")

    results = []
    for entry in _data_list(resp):
        hid = entry.get("hotelId")
        static = by_id.get(hid, {})
        best = _cheapest_rate(entry)
        if best is None:
            continue
        if price_min is not None and best["price"] < price_min:
            continue
        if price_max is not None and best["price"] > price_max:
            continue
        results.append(
            {
                "id": hid,
                "name": entry.get("name") or static.get("name"),
                "rating": static.get("stars") or entry.get("stars"),
                "city": static.get("city") or entry.get("city"),
                "distance_km": _haversine_km(
                    geo["lat"], geo["lon"], static.get("latitude"), static.get("longitude")
                ),
                "amenities": static.get("facilities") or static.get("amenities") or [],
                "best_price_total": best["price"],
                "currency": (currency or "USD").upper(),
                "room_type": best["room"],
            }
        )
    results.sort(key=lambda h: (h["best_price_total"] is None, h["best_price_total"] or 0))
    results = results[: max(1, min(int(max_results), 20))]
    out: dict = {
        "location": location,
        "check_in": check_in,
        "check_out": check_out,
        "hotels": results,
    }
    out["disclaimer"] = (
        "LiteAPI SANDBOX: rates are illustrative test inventory — "
        "verify live pricing before booking."
    )
    if not results:
        out["note"] = "No bookable rates returned for these dates."
    return out


def get_hotel_details(hotel_id: str) -> dict:
    """Full static details for one hotel (description, amenities, location)."""
    if not settings.liteapi_api_key:
        return {
            "error": "Hotel details unavailable: LITEAPI_API_KEY not set.",
            "hint": "Sign up free at https://dashboard.liteapi.travel and add the sandbox key to .env.",
        }
    try:
        resp = requests.get(
            f"{_BASE}/data/hotels",
            params={"hotelIds": hotel_id},
            headers=_headers(),
            timeout=30,
        )
    except Exception as exc:
        return {"error": f"Hotel details lookup failed: {exc}", "hint": "Retry shortly."}
    if resp.status_code >= 400:
        return _api_error(resp, "hotel details")
    items = _data_list(resp)
    if not items:
        return {
            "error": f"No details found for hotel '{hotel_id}'.",
            "hint": "Use an id from search_hotels.",
        }
    h = items[0]
    return {
        "id": h.get("id"),
        "name": h.get("name"),
        "description": h.get("hotelDescription"),
        "rating": h.get("stars"),
        "address": ", ".join(
            x for x in [h.get("address"), h.get("city"), h.get("zip"), h.get("country")] if x
        ),
        "amenities": h.get("facilities") or h.get("amenities") or [],
        "photo": h.get("main_photo"),
    }
