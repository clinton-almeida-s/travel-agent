"""Flights via the Duffel Offer Requests API.

Auth is a single API key; the mode is derived from the key prefix
(``duffel_test_`` / ``duffel_live_``) — there is no separate sandbox URL.
Test mode returns structurally realistic but *illustrative* inventory
(Duffel Airways): never present it as live market pricing.

Never invent prices or availability: on missing credentials or API errors
these functions return {"error", "hint"} dicts.
"""
from __future__ import annotations

import requests

from ..config import settings

_DUFFEL_URL = "https://api.duffel.com/air/offer_requests"

# In-process cache of raw offers from the latest search_flights call, so
# get_flight_details can pull baggage/policy details without re-searching.
_offer_cache: dict[str, dict] = {}

_CABIN_MAP = {
    "ECONOMY": "economy",
    "PREMIUM_ECONOMY": "premium_economy",
    "BUSINESS": "business",
    "FIRST": "first",
}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.duffel_api_key}",
        "Duffel-Version": "v2",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _duffel_error(resp: requests.Response, what: str) -> dict:
    if resp.status_code == 401:
        return {
            "error": "Duffel rejected the API key (401).",
            "hint": "Check DUFFEL_API_KEY in .env — test keys start with duffel_test_.",
        }
    detail = ""
    try:
        errors = resp.json().get("errors", [])
        detail = "; ".join(e.get("title", "") for e in errors) or resp.text[:200]
    except Exception:
        detail = resp.text[:200]
    return {
        "error": f"Duffel {what} failed (HTTP {resp.status_code}): {detail}",
        "hint": "Check airport codes/dates, or retry shortly.",
    }


def _summarize_offer(offer: dict) -> dict:
    legs = []
    carriers: list[str] = []
    for sl in offer.get("slices", []) or []:
        segments = []
        for seg in sl.get("segments", []) or []:
            op = seg.get("operating_carrier") or {}
            code = op.get("iata_code", "")
            num = seg.get("operating_carrier_flight_number") or seg.get(
                "marketing_carrier_flight_number", ""
            )
            if code and code not in carriers:
                carriers.append(code)
            segments.append(
                {
                    "airline": code,
                    "flight_number": f"{code}{num}",
                    "from": (seg.get("origin") or {}).get("iata_code"),
                    "to": (seg.get("destination") or {}).get("iata_code"),
                    "departure": seg.get("departing_at"),
                    "arrival": seg.get("arriving_at"),
                }
            )
        legs.append(
            {
                "duration": sl.get("duration"),
                "segments": segments,
                "stops": max(len(segments) - 1, 0),
            }
        )
    owner = (offer.get("owner") or {}).get("iata_code")
    summary = {
        "id": offer.get("id"),
        "price_total": offer.get("total_amount"),
        "currency": offer.get("total_currency"),
        "outbound": legs[0] if legs else None,
        "return": legs[1] if len(legs) > 1 else None,
        "validating_airlines": [owner] if owner else carriers,
    }
    if not offer.get("live_mode", False):
        summary["test_mode"] = True
    return summary


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    passengers: int = 1,
    cabin: str = "ECONOMY",
    max_results: int = 5,
    nonstop_only: bool = False,
) -> dict:
    """Search live flight offers. Never invents data."""
    if not settings.duffel_api_key:
        return {
            "error": "Flight search unavailable: DUFFEL_API_KEY not set.",
            "hint": "Sign up free at https://duffel.com (no card), create a test API key, and add it to .env.",
        }
    slices = [
        {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
        }
    ]
    if return_date:
        slices.append(
            {
                "origin": destination.upper(),
                "destination": origin.upper(),
                "departure_date": return_date,
            }
        )
    if nonstop_only:
        for sl in slices:
            sl["max_connections"] = 0
    body = {
        "data": {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(max(int(passengers), 1))],
            "cabin_class": _CABIN_MAP.get(cabin.upper(), "economy"),
        }
    }
    try:
        resp = requests.post(
            _DUFFEL_URL,
            params={"return_offers": "true", "supplier_timeout": 15000},
            json=body,
            headers=_headers(),
            timeout=60,
        )
    except Exception as exc:
        return {"error": f"Flight search failed: {exc}", "hint": "Check your connection and retry."}
    if resp.status_code >= 400:
        return _duffel_error(resp, "flight search")
    try:
        offers = resp.json()["data"].get("offers", []) or []
    except Exception as exc:
        return {"error": f"Could not parse Duffel response: {exc}", "hint": "Retry shortly."}
    _offer_cache.clear()
    summaries = []
    for offer in offers[: max(1, min(int(max_results), 20))]:
        summary = _summarize_offer(offer)
        _offer_cache[str(summary["id"])] = offer
        summaries.append(summary)
    out: dict = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_date": departure_date,
        "return_date": return_date,
        "offers": summaries,
    }
    if any(s.get("test_mode") for s in summaries):
        out["disclaimer"] = (
            "Duffel TEST mode: illustrative schedules and prices (Duffel Airways "
            "test inventory) — verify live pricing before booking."
        )
    if not summaries:
        out["note"] = "No offers returned for this search."
    return out


def get_flight_details(flight_id: str) -> dict:
    """Baggage and fare details for an offer from search_flights."""
    if not settings.duffel_api_key:
        return {
            "error": "Flight details unavailable: DUFFEL_API_KEY not set.",
            "hint": "Sign up free at https://duffel.com and add the test key to .env.",
        }
    raw = _offer_cache.get(str(flight_id))
    if raw is None:
        return {
            "error": f"Unknown flight_id '{flight_id}'.",
            "hint": "Use an offer id returned by search_flights in this session.",
        }
    baggage = []
    for sl in raw.get("slices", []) or []:
        for seg in sl.get("segments", []) or []:
            pax = (seg.get("passengers") or [{}])[0]
            checked = None
            for bag in pax.get("baggages", []) or []:
                if bag.get("type") == "checked":
                    checked = bag.get("quantity")
                    break
            origin = (seg.get("origin") or {}).get("iata_code")
            dest = (seg.get("destination") or {}).get("iata_code")
            baggage.append(
                {"segment": f"{origin}-{dest}", "checked_bags": checked}
            )
    out: dict = {
        "flight_id": str(flight_id),
        "price_total": raw.get("total_amount"),
        "currency": raw.get("total_currency"),
        "baggage": baggage,
    }
    if not raw.get("live_mode", False):
        out["disclaimer"] = (
            "Duffel TEST mode: illustrative pricing. Change/cancel rules are set by the "
            "validating airline at ticketing — verify before booking."
        )
    return out
