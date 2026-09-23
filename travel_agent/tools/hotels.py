"""Hotels via Amadeus Hotel Search v3 (hotel list by geocode + hotel offers).

Never invent prices or availability: on missing credentials or API errors
these functions return {"error", "hint"} dicts.
"""
from __future__ import annotations

from ..config import settings
from .geocode import geocode


def _client():
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        raise RuntimeError("Amadeus credentials missing")
    from amadeus import Client

    hostname = "production" if settings.amadeus_env == "prod" else "test"
    return Client(
        client_id=settings.amadeus_client_id,
        client_secret=settings.amadeus_client_secret,
        hostname=hostname,
    )


def _summarize_hotel(hotel: dict, offers: list[dict]) -> dict:
    best = None
    if offers:
        best = min(offers, key=lambda o: float(o.get("price", {}).get("total", "inf") or "inf"))
    best_price = (best or {}).get("price", {}) if best else {}
    return {
        "id": hotel.get("hotelId"),
        "name": hotel.get("name"),
        "rating": hotel.get("rating"),
        "city": (hotel.get("address") or {}).get("cityName"),
        "distance_km": (hotel.get("distance") or {}).get("value"),
        "amenities": hotel.get("amenities", []),
        "best_price_total": best_price.get("total"),
        "currency": best_price.get("currency"),
        "room_type": ((best or {}).get("room") or {}).get("typeEstimated", {}).get("category"),
    }


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
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        return {
            "error": "Hotel search unavailable: AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET not set.",
            "hint": "Get free test credentials at https://developers.amadeus.com and add them to .env.",
        }
    geo = geocode(location)
    if "error" in geo:
        return {"error": f"Hotel search failed: {geo['error']}", "hint": geo.get("hint", "")}
    try:
        from amadeus import ResponseError

        amadeus = _client()
        try:
            hotel_list = amadeus.reference_data.locations.hotels.by_geocode.get(
                latitude=geo["lat"], longitude=geo["lon"], radius=20, radiusUnit="KM"
            )
        except ResponseError as exc:
            return {"error": f"Hotel list lookup failed: {exc}", "hint": "Retry shortly."}
        hotels = (hotel_list.data or [])[: max(1, min(int(max_results), 20))]
        if not hotels:
            return {"location": location, "hotels": [], "note": "No hotels found near this location."}
        hotel_ids = ",".join(h["hotelId"] for h in hotels if h.get("hotelId"))
        offer_params: dict = {
            "hotelIds": hotel_ids,
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "adults": max(int(guests), 1),
            "currency": (currency or "USD").upper(),
        }
        if price_min is not None or price_max is not None:
            lo = f"{price_min}" if price_min is not None else ""
            hi = f"{price_max}" if price_max is not None else ""
            offer_params["priceRange"] = f"{lo}-{hi}"
        if amenities:
            offer_params["amenities"] = ",".join(a.upper() for a in amenities)
        try:
            offers_resp = amadeus.shopping.hotel_offers_search.get(**offer_params)
        except ResponseError as exc:
            return {"error": f"Hotel offers lookup failed: {exc}", "hint": "Retry shortly."}
        offers_by_hotel: dict[str, list[dict]] = {}
        for entry in offers_resp.data or []:
            hid = (entry.get("hotel") or {}).get("hotelId")
            if hid:
                offers_by_hotel.setdefault(hid, []).extend(entry.get("offers") or [])
        results = [_summarize_hotel(h, offers_by_hotel.get(h.get("hotelId"), [])) for h in hotels]
        out: dict = {
            "location": location,
            "check_in": check_in,
            "check_out": check_out,
            "hotels": results,
        }
        if settings.amadeus_env != "prod":
            out["disclaimer"] = (
                "Prices are from the Amadeus TEST environment and are indicative only — "
                "verify live pricing before booking."
            )
        return out
    except Exception as exc:
        return {"error": f"Hotel search failed: {exc}", "hint": "Retry, or check credentials."}


def get_hotel_details(hotel_id: str) -> dict:
    """Full details + current offers for one hotel."""
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        return {
            "error": "Hotel details unavailable: Amadeus credentials not set.",
            "hint": "Get free test credentials at https://developers.amadeus.com.",
        }
    try:
        from amadeus import ResponseError

        amadeus = _client()
        try:
            resp = amadeus.shopping.hotel_offers_search.get(hotelIds=hotel_id)
        except ResponseError as exc:
            return {"error": f"Hotel details lookup failed: {exc}", "hint": "Check the hotel id."}
        entries = resp.data or []
        if not entries:
            return {"error": f"No details found for hotel '{hotel_id}'.", "hint": "Use an id from search_hotels."}
        entry = entries[0]
        hotel = entry.get("hotel", {})
        offers = []
        for o in entry.get("offers", [])[:5]:
            offers.append(
                {
                    "id": o.get("id"),
                    "price_total": (o.get("price") or {}).get("total"),
                    "currency": (o.get("price") or {}).get("currency"),
                    "room": (o.get("room") or {}).get("description", {}).get("text"),
                    "policies": o.get("policies", {}),
                }
            )
        return {
            "id": hotel.get("hotelId"),
            "name": hotel.get("name"),
            "description": hotel.get("description", {}).get("text") if isinstance(hotel.get("description"), dict) else hotel.get("description"),
            "rating": hotel.get("rating"),
            "address": hotel.get("address"),
            "amenities": hotel.get("amenities", []),
            "offers": offers,
        }
    except Exception as exc:
        return {"error": f"Hotel details failed: {exc}", "hint": "Retry shortly."}
