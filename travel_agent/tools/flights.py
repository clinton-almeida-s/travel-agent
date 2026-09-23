"""Flights via Amadeus Flight Offers Search v2 (test env by default).

Never invent prices or availability: on missing credentials or API errors
these functions return {"error", "hint"} dicts.
"""
from __future__ import annotations

from ..config import settings

# In-process cache of raw offers from the latest search_flights call, so
# get_flight_details can re-price a specific offer via Flight Offers Price.
_offer_cache: dict[str, dict] = {}


def _client():
    """Build an Amadeus client. Import is lazy so the package imports offline."""
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        raise RuntimeError("Amadeus credentials missing")
    from amadeus import Client

    hostname = "production" if settings.amadeus_env == "prod" else "test"
    return Client(
        client_id=settings.amadeus_client_id,
        client_secret=settings.amadeus_client_secret,
        hostname=hostname,
    )


def _summarize_offer(offer: dict) -> dict:
    itineraries = offer.get("itineraries", [])
    legs = []
    for itin in itineraries:
        segments = itin.get("segments", [])
        legs.append(
            {
                "duration": itin.get("duration"),
                "segments": [
                    {
                        "airline": seg.get("carrierCode"),
                        "flight_number": f"{seg.get('carrierCode')}{seg.get('number')}",
                        "from": seg["departure"]["iataCode"],
                        "to": seg["arrival"]["iataCode"],
                        "departure": seg["departure"]["at"],
                        "arrival": seg["arrival"]["at"],
                    }
                    for seg in segments
                ],
                "stops": max(len(segments) - 1, 0),
            }
        )
    price = offer.get("price", {})
    return {
        "id": offer.get("id"),
        "price_total": price.get("total"),
        "currency": price.get("currency"),
        "outbound": legs[0] if legs else None,
        "return": legs[1] if len(legs) > 1 else None,
        "validating_airlines": offer.get("validatingAirlineCodes", []),
    }


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
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        return {
            "error": "Flight search unavailable: AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET not set.",
            "hint": "Get free test credentials at https://developers.amadeus.com and add them to .env.",
        }
    try:
        amadeus = _client()
        params: dict = {
            "originLocationCode": origin.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": departure_date,
            "adults": max(int(passengers), 1),
            "travelClass": cabin.upper(),
            "max": max(1, min(int(max_results), 20)),
        }
        if return_date:
            params["returnDate"] = return_date
        if nonstop_only:
            params["nonStop"] = "true"
        from amadeus import ResponseError

        try:
            response = amadeus.shopping.flight_offers_search.get(**params)
        except ResponseError as exc:
            return {
                "error": f"Amadeus flight search failed: {exc}",
                "hint": "Check airport codes/dates, or retry shortly.",
            }
        raw_offers = response.data or []
        offers = []
        _offer_cache.clear()
        for offer in raw_offers:
            summary = _summarize_offer(offer)
            _offer_cache[str(summary["id"])] = offer
            offers.append(summary)
        out: dict = {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "return_date": return_date,
            "offers": offers,
        }
        if settings.amadeus_env != "prod":
            out["disclaimer"] = (
                "Prices are from the Amadeus TEST environment and are indicative only — "
                "verify live pricing before booking."
            )
        if not offers:
            out["note"] = "No offers returned for this search."
        return out
    except Exception as exc:
        return {"error": f"Flight search failed: {exc}", "hint": "Retry, or check credentials."}


def get_flight_details(flight_id: str) -> dict:
    """Re-price an offer and return baggage / change-policy details."""
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        return {
            "error": "Flight details unavailable: Amadeus credentials not set.",
            "hint": "Get free test credentials at https://developers.amadeus.com.",
        }
    raw = _offer_cache.get(str(flight_id))
    if raw is None:
        return {
            "error": f"Unknown flight_id '{flight_id}'.",
            "hint": "Use an offer id returned by search_flights in this session.",
        }
    try:
        from amadeus import ResponseError

        amadeus = _client()
        try:
            priced = amadeus.shopping.flight_offers.pricing.post(raw)
        except ResponseError as exc:
            return {"error": f"Could not re-price offer: {exc}", "hint": "The fare may have expired; search again."}
        data = priced.data or {}
        price = data.get("price", {})
        traveler_pricings = data.get("travelerPricings", [])
        baggage = []
        for tp in traveler_pricings:
            for fd in tp.get("fareDetailsBySegment", []):
                baggage.append(
                    {
                        "segment": fd.get("segmentId"),
                        "cabin": fd.get("cabin"),
                        "checked_bags": (fd.get("includedCheckedBags") or {}).get("quantity"),
                    }
                )
        return {
            "flight_id": str(flight_id),
            "price_total": price.get("total"),
            "currency": price.get("currency"),
            "baggage": baggage,
            "disclaimer": (
                "Indicative test-environment pricing. Change/cancel rules are set by the "
                "validating airline at ticketing — verify before booking."
            ),
        }
    except Exception as exc:
        return {"error": f"Flight details failed: {exc}", "hint": "Retry shortly."}
