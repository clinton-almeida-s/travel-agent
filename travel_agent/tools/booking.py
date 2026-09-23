"""Booking guardrails.

book_flight / book_hotel NEVER complete a booking unless ``confirmed=True``.
Without confirmation they return a review summary for the user. Even with
confirmation, live ticketing only runs when AMADEUS_ENV=prod AND
ENABLE_LIVE_BOOKING=true; otherwise a prepared "ready to ticket" summary is
returned. Confirmation numbers are never fabricated.
"""
from __future__ import annotations

from ..config import settings


def _confirmation_summary(kind: str, selection: str, details: dict) -> dict:
    return {
        "status": "confirmation_required",
        "kind": kind,
        "selection": selection,
        "details": details,
        "message": (
            "No booking was made. Review the summary above with the traveler. "
            "To proceed, call this tool again with confirmed=true along with "
            "complete passenger/guest and payment details."
        ),
    }


def book_flight(
    selected_flight: str,
    passenger_details: dict,
    payment: dict,
    confirmed: bool = False,
) -> dict:
    """Book a flight offer. Requires confirmed=true; never fabricates tickets."""
    if not isinstance(passenger_details, dict) or not passenger_details:
        return {
            "error": "Passenger details are required before booking.",
            "hint": "Provide names, dates of birth and contact info for every traveler.",
        }
    if not isinstance(payment, dict) or not payment:
        return {
            "error": "Payment details are required before booking.",
            "hint": "Provide a valid payment method.",
        }
    if not confirmed:
        return _confirmation_summary(
            "flight", selected_flight, {"passengers": passenger_details, "payment_method_present": True}
        )
    if not (settings.amadeus_env == "prod" and settings.enable_live_booking):
        return {
            "status": "ready_to_ticket",
            "kind": "flight",
            "selection": selected_flight,
            "message": (
                "Live ticketing is disabled (requires AMADEUS_ENV=prod and "
                "ENABLE_LIVE_BOOKING=true). The booking was prepared but NOT issued. "
                "Complete ticketing with the airline or agency using this offer."
            ),
        }
    # Live ticketing path intentionally not implemented in v1: issuing real
    # tickets moves real money and needs agency credentials, PCC setup and
    # manual review. Fail closed rather than risk a bad charge.
    return {
        "status": "not_supported",
        "kind": "flight",
        "message": (
            "Live flight ticketing is not implemented in this version. "
            "Use the confirmed offer details to ticket via the airline or your agency."
        ),
    }


def book_hotel(
    selected_hotel: str,
    guest_details: dict,
    payment: dict,
    confirmed: bool = False,
) -> dict:
    """Book a hotel offer. Requires confirmed=true; never fabricates reservations."""
    if not isinstance(guest_details, dict) or not guest_details:
        return {
            "error": "Guest details are required before booking.",
            "hint": "Provide guest names and contact info.",
        }
    if not isinstance(payment, dict) or not payment:
        return {
            "error": "Payment details are required before booking.",
            "hint": "Provide a valid payment method.",
        }
    if not confirmed:
        return _confirmation_summary(
            "hotel", selected_hotel, {"guests": guest_details, "payment_method_present": True}
        )
    if not (settings.amadeus_env == "prod" and settings.enable_live_booking):
        return {
            "status": "ready_to_ticket",
            "kind": "hotel",
            "selection": selected_hotel,
            "message": (
                "Live booking is disabled (requires AMADEUS_ENV=prod and "
                "ENABLE_LIVE_BOOKING=true). The reservation was prepared but NOT made. "
                "Complete it with the hotel or booking platform using these details."
            ),
        }
    return {
        "status": "not_supported",
        "kind": "hotel",
        "message": (
            "Live hotel booking is not implemented in this version. "
            "Use the confirmed offer details to book via the hotel or your platform."
        ),
    }
