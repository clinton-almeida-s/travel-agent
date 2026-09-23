"""Conversational CLI: greets, collects the spec's required inputs
(only asking what's missing or outcome-changing), then runs the agent
and prints the final travel plan.
"""
from __future__ import annotations

from .agent import run_agent
from .config import is_configured, missing_services


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nBye!")
        raise SystemExit(0)
    return answer or default


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
        print("  Please enter a positive whole number.")


def collect_trip_brief() -> str:
    """Conversationally gather the required inputs; return a trip brief for the agent."""
    print("\n✈️  Great — let's plan your trip. I'll only ask what I need.\n")

    destination = _ask("Where are you going? (destination city/cities)")
    while not destination:
        print("  I need at least a destination to plan anything.")
        destination = _ask("Where are you going? (destination city/cities)")

    departure = _ask("Where are you flying from? (city or airport code, blank = I'll ask the agent to assume)")
    dates = _ask("Travel dates? (e.g. '2026-12-10 to 2026-12-17', or '5 days in March')")
    travelers = _ask_int("How many travelers?", 1)
    names = _ask("Traveler names? (comma-separated, blank = skip)")
    ages = _ask("Ages of travelers? (comma-separated, blank = assume adults)")
    interests = _ask("What do you enjoy? (culture, food, beaches, museums, nightlife, adventure…)")
    budget = _ask("Budget level? (budget / mid-range / luxury, or a hard cap like 'under $2000')", "mid-range")
    cabin = _ask("Cabin class? (economy / premium / business / first)", "economy").lower()
    nonstop = _ask("Nonstop flights only? (yes/no)", "no").lower().startswith("y")
    pace = _ask("Trip pace? (relaxed / balanced / packed)", "balanced")
    notes = _ask("Anything else? (dietary needs, accessibility, airline preference…)")

    lines = [
        "Plan a trip with the following details:",
        f"- Destination(s): {destination}",
        f"- Departure city/airport: {departure or 'not provided — assume from traveler location or ask in your reply'}",
        f"- Dates: {dates or 'not provided — propose sensible dates and state your assumption'}",
        f"- Travelers: {travelers}" + (f" ({names})" if names else ""),
        f"- Ages: {ages or 'assume all adults'}",
        f"- Interests: {interests or 'general sightseeing'}",
        f"- Budget: {budget}",
        f"- Cabin: {cabin}",
        f"- Nonstop only: {'yes' if nonstop else 'no'}",
        f"- Pace: {pace}",
    ]
    if notes:
        lines.append(f"- Other needs: {notes}")
    lines.append(
        "\nUse your tools for live flights, hotels, activities and weather. "
        "Follow your output format exactly (trip summary, flights table, day-by-day "
        "itinerary, accommodation, practical notes)."
    )
    return "\n".join(lines)


def main() -> None:
    print("=" * 60)
    print("🧳  AI Travel Agent — flights, stays & itineraries, planned live")
    print("=" * 60)

    if not is_configured("llm"):
        print(
            "\nI need an LLM backend to think with. Set one of these in your .env:\n"
            "  GEMINI_API_KEY=...   (free at https://aistudio.google.com)\n"
            "  GROQ_API_KEY=...     (free at https://console.groq.com)\n"
            "  LLM_PROVIDER=gemini  (or groq)\n"
            "\nCopy .env.example to .env and fill in at least one key, then rerun."
        )
        raise SystemExit(1)

    missing = [s for s in missing_services() if s != "llm"]
    if missing:
        print(
            "\n⚠️  Optional services not configured: " + ", ".join(missing) + ".\n"
            "   I'll still plan your trip but will mark those sections\n"
            "   'estimate — verify before booking'. See README for free API keys."
        )

    brief = collect_trip_brief()
    print("\n🔍 Planning your trip — this may take a minute while I check live data…\n")
    plan = run_agent(brief)
    print("\n" + "=" * 60)
    print("🗺️  YOUR TRAVEL PLAN")
    print("=" * 60 + "\n")
    print(plan)


if __name__ == "__main__":
    main()
