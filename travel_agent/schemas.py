"""Provider-neutral JSON schemas for the 8 agent tools, plus converters.

The canonical definitions live in ``TOOLS`` as plain dicts
``{"name", "description", "parameters"}`` where ``parameters`` is a JSON
Schema object. :func:`to_gemini_tools` and :func:`to_groq_tools` convert
them to the function-declaration formats each LLM backend expects.
"""
from __future__ import annotations

import copy

TOOLS: list[dict] = [
    {
        "name": "search_flights",
        "description": (
            "Search for flight offers between two airports on given dates. "
            "Returns live offers with airline, times, duration, stops and price. "
            "Prices from the Amadeus test environment are indicative — tell the "
            "user to verify before booking."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Origin airport IATA code, e.g. BOM"},
                "destination": {"type": "string", "description": "Destination airport IATA code, e.g. DXB"},
                "departure_date": {"type": "string", "description": "Departure date YYYY-MM-DD"},
                "return_date": {"type": "string", "description": "Return date YYYY-MM-DD (omit for one-way)"},
                "passengers": {"type": "integer", "description": "Total number of travelers", "default": 1},
                "cabin": {
                    "type": "string",
                    "description": "Cabin class",
                    "enum": ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
                    "default": "ECONOMY",
                },
                "max_results": {"type": "integer", "description": "Max offers to return", "default": 5},
                "nonstop_only": {"type": "boolean", "description": "Only nonstop flights", "default": False},
            },
            "required": ["origin", "destination", "departure_date"],
        },
    },
    {
        "name": "get_flight_details",
        "description": (
            "Get live pricing, baggage rules and change/cancel policy for a flight "
            "offer returned by search_flights. Pass the offer's id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "flight_id": {
                    "type": "string",
                    "description": "Offer id from a search_flights result",
                }
            },
            "required": ["flight_id"],
        },
    },
    {
        "name": "search_hotels",
        "description": (
            "Search hotels near a location for given check-in/check-out dates. "
            "Returns live offers with price per night, rating and amenities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or place name, e.g. 'Dubai Marina'"},
                "check_in": {"type": "string", "description": "Check-in date YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "Check-out date YYYY-MM-DD"},
                "guests": {"type": "integer", "description": "Number of guests", "default": 1},
                "price_min": {"type": "number", "description": "Min price per night"},
                "price_max": {"type": "number", "description": "Max price per night"},
                "currency": {"type": "string", "description": "ISO currency code", "default": "USD"},
                "amenities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Desired amenities, e.g. ['SWIMMING_POOL','WIFI']",
                },
                "max_results": {"type": "integer", "description": "Max hotels to return", "default": 5},
            },
            "required": ["location", "check_in", "check_out"],
        },
    },
    {
        "name": "get_hotel_details",
        "description": (
            "Get full details for a hotel returned by search_hotels: description, "
            "amenities, policies and current room offers. Pass the hotel's id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hotel_id": {"type": "string", "description": "Hotel id from a search_hotels result"}
            },
            "required": ["hotel_id"],
        },
    },
    {
        "name": "search_activities",
        "description": (
            "Find sightseeing activities and points of interest near a location, "
            "ranked against the traveler's interests. Uses Wikipedia geosearch "
            "(+ OpenTripMap when configured)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or place name"},
                "interests": {
                    "type": "string",
                    "description": "Comma-separated interests, e.g. 'museums, food, beaches'",
                },
                "date": {"type": "string", "description": "Planned visit date YYYY-MM-DD (optional)"},
                "group_size": {"type": "integer", "description": "Number of travelers", "default": 1},
                "max_results": {"type": "integer", "description": "Max activities to return", "default": 10},
            },
            "required": ["location", "interests"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get the weather forecast for a location over a date range. "
            "Free tier covers ~5 days ahead; dates further out return an error."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name, e.g. 'Paris'"},
                "date_range": {
                    "type": "string",
                    "description": "Date range 'YYYY-MM-DD to YYYY-MM-DD' (single date allowed)",
                },
            },
            "required": ["location", "date_range"],
        },
    },
    {
        "name": "book_flight",
        "description": (
            "Book a flight offer. SAFETY: the booking is NOT made unless "
            "'confirmed' is true — without confirmation this only returns a "
            "summary for the user to review."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selected_flight": {
                    "type": "string",
                    "description": "Offer id from search_flights / get_flight_details",
                },
                "passenger_details": {
                    "type": "object",
                    "description": "Passenger names, DOBs, contact info",
                },
                "payment": {"type": "object", "description": "Payment details"},
                "confirmed": {
                    "type": "boolean",
                    "description": "User explicitly confirmed this exact booking",
                    "default": False,
                },
            },
            "required": ["selected_flight", "passenger_details", "payment"],
        },
    },
    {
        "name": "book_hotel",
        "description": (
            "Book a hotel offer. SAFETY: the booking is NOT made unless "
            "'confirmed' is true — without confirmation this only returns a "
            "summary for the user to review."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selected_hotel": {
                    "type": "string",
                    "description": "Hotel id from search_hotels / get_hotel_details",
                },
                "guest_details": {"type": "object", "description": "Guest names and contact info"},
                "payment": {"type": "object", "description": "Payment details"},
                "confirmed": {
                    "type": "boolean",
                    "description": "User explicitly confirmed this exact booking",
                    "default": False,
                },
            },
            "required": ["selected_hotel", "guest_details", "payment"],
        },
    },
]


def to_gemini_tools(tools: list[dict] | None = None) -> list[dict]:
    """Convert to google-genai function-declaration format.

    Returns ``[{"function_declarations": [...]}]`` which can be passed as the
    ``tools`` argument to ``GenerateContentConfig``.
    """
    tools = TOOLS if tools is None else tools
    declarations = [
        {
            "name": t["name"],
            "description": t["description"],
            "parameters": copy.deepcopy(t["parameters"]),
        }
        for t in tools
    ]
    return [{"function_declarations": declarations}]


def to_groq_tools(tools: list[dict] | None = None) -> list[dict]:
    """Convert to Groq (OpenAI-compatible) chat tools format."""
    tools = TOOLS if tools is None else tools
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": copy.deepcopy(t["parameters"]),
            },
        }
        for t in tools
    ]


def tool_names() -> list[str]:
    return [t["name"] for t in TOOLS]
