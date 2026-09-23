# 🧳 AI Travel Agent

A conversational CLI agent that builds complete, live-updated travel plans —
flights, hotels, day-by-day itineraries, and practical notes — optimized for
your interests and budget.

You describe the trip; the agent calls **real APIs through function calling**
and reasons over live data. It never invents prices, flight times, or
availability — if live data is unavailable, that section is labeled
**"estimate — verify before booking."**

## Architecture

```
┌─────────┐   trip brief    ┌──────────┐  tool calls   ┌───────────────┐
│   CLI   │ ─────────────▶ │  Agent   │ ─────────────▶ │  LLM backend  │
│(cli.py) │                │(agent.py)│ ◀───────────── │ gemini | groq │
└─────────┘                └────┬─────┘  tool results  └───────────────┘
                                │ executes
                    ┌───────────┴────────────┐
                    ▼           ▼            ▼
              ┌──────────┐ ┌────────┐ ┌────────────┐
              │ Flights  │ │ Hotels │ │ Activities │
              │ Amadeus  │ │Amadeus │ │ Wikipedia  │
              │  test ✓  │ │ test ✓ │ │  +OTM opt. │
              └──────────┘ └────────┘ └────────────┘
                    ▼           ▼
              ┌──────────┐ ┌────────────┐  ┌──────────┐
              │ Weather  │ │ Geocode    │  │ Booking  │
              │OpenWeath.│ │ Nominatim  │  │guardrails│
              └──────────┘ └────────────┘  └──────────┘
```

- **LLM backends** (`llm.py`): Gemini via `google-genai`, Groq via `groq` SDK —
  both with function calling, behind one `chat(messages, tools)` interface.
- **Flights** (`tools/flights.py`): Amadeus Flight Offers Search v2 + re-pricing
  via Flight Offers Price. Test environment by default (`AMADEUS_ENV=test`).
- **Hotels** (`tools/hotels.py`): Amadeus Hotel Search v3 (geocode → hotel list → offers).
- **Activities** (`tools/activities.py`): Wikipedia geosearch (no key) as primary
  POI source, OpenTripMap as optional enhancement.
- **Weather** (`tools/weather.py`): OpenWeather 5-day forecast (free tier).
- **Geocoding** (`tools/geocode.py`): Nominatim, proper User-Agent, 1 req/sec,
  in-memory cache.
- **Booking guardrails** (`tools/booking.py`): `book_flight`/`book_hotel` require
  `confirmed=true`; without it they return a confirmation summary and **do not book**.
  Live ticketing additionally requires `AMADEUS_ENV=prod` + `ENABLE_LIVE_BOOKING=true`.

## Setup

```bash
git clone https://github.com/clinton-almeida-s/travel-agent
cd travel-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in keys (see below)
python -m travel_agent
```

## Where to get free API keys

| Key | Where | Free tier |
|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | Generous free quota |
| `GROQ_API_KEY` | https://console.groq.com/keys | Free tier, tool-calling models |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | https://developers.amadeus.com/register | Test API free, no card |
| `OPENWEATHER_API_KEY` | https://openweathermap.org/api | 1,000 calls/day |
| `OPENTRIPMAP_API_KEY` | https://opentripmap.io | Free (optional) |

Nominatim (geocoding) and Wikipedia (activities) need no keys.

## Example session

```
$ python -m travel_agent
============================================================
🧳  AI Travel Agent — flights, stays & itineraries, planned live
============================================================

✈️  Great — let's plan your trip. I'll only ask what I need.

Where are you going? (destination city/cities): Tokyo
Where are you flying from? …: Mumbai
Travel dates? …: 2026-12-10 to 2026-12-17
How many travelers? [1]: 2
Traveler names? …: Clinton, Priya
Ages of travelers? …: 29, 27
What do you enjoy? …: food, temples, nightlife
Budget level? … [mid-range]: mid-range
...

🔍 Planning your trip — this may take a minute while I check live data…

  🔧 search_flights({"origin": "BOM", "destination": "TYO", ...})
  …round 1 done, thinking…
  🔧 search_hotels({"location": "Tokyo", ...})
  …

🗺️  YOUR TRAVEL PLAN
1. Trip summary …  2. Flights …  3. Day-by-day itinerary …
4. Accommodation …  5. Practical notes …
```

## Limitations (read this)

- **Free flight APIs are indicative, not Google-Flights-live.** Amadeus test
  prices are estimates — always verify before booking. The agent says this
  itself whenever relevant.
- OpenWeather free tier only forecasts ~5 days ahead.
- v1 does **not** issue real tickets or hotel reservations. `book_*` tools
  prepare and confirm, but live ticketing is intentionally not implemented —
  complete payment with the airline/hotel. This is a safety decision, not a bug.
- No web UI, no database — CLI v1. Conversation history lives only in the session.

## Project layout

```
travel_agent/
├── __init__.py        package version
├── __main__.py        python -m travel_agent entry point
├── cli.py             conversational CLI + required-input collection
├── agent.py           agentic loop (LLM → tools → LLM, max 12 rounds)
├── llm.py             Gemini / Groq backend abstraction (function calling)
├── prompts.py         system prompt (spec, adapted)
├── schemas.py         8 tool JSON schemas + Gemini/Groq converters
├── config.py          .env loading, settings, is_configured()
└── tools/
    ├── flights.py     Amadeus Flight Offers Search v2
    ├── hotels.py      Amadeus Hotel Search v3
    ├── activities.py  Wikipedia geosearch (+ OpenTripMap)
    ├── weather.py     OpenWeather 5-day forecast
    ├── geocode.py     Nominatim (1 req/sec, cached)
    └── booking.py     confirmation guardrails
```
