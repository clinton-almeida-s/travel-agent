"""Tool implementations. Each returns a JSON-serializable dict.

On missing credentials or API errors every tool returns
``{"error": ..., "hint": ...}`` — the agent must then label that section
"estimate — verify before booking" instead of inventing data.
"""
from .activities import search_activities
from .booking import book_flight, book_hotel
from .flights import get_flight_details, search_flights
from .geocode import geocode
from .hotels import get_hotel_details, search_hotels
from .weather import get_weather

TOOL_REGISTRY: dict[str, object] = {
    "search_flights": search_flights,
    "get_flight_details": get_flight_details,
    "search_hotels": search_hotels,
    "get_hotel_details": get_hotel_details,
    "search_activities": search_activities,
    "get_weather": get_weather,
    "book_flight": book_flight,
    "book_hotel": book_hotel,
}

__all__ = ["TOOL_REGISTRY"]
