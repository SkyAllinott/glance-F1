from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
import httpx
import io
from datetime import datetime, timedelta
import pytz
import os
import requests

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from .pit_results import pit_constructor_calculator

router = APIRouter()


current_year = datetime.now().year

points = {
        1: 25,
        2: 18,
        3: 15,
        4: 12,
        5: 10,
        6: 8,
        7: 6,
        8: 4,
        9: 2,
        10: 1
    }

LAST_RACE_API_URL = "http://localhost:4463/f1/next_race/"

TZ = os.environ.get("TIMEZONE").strip()
if TZ not in pytz.all_timezones:
    raise ValueError('Invalid time zone selection')
MT = pytz.timezone(TZ)

@router.on_event("startup")
# Initialize caching
async def startup():
    FastAPICache.init(InMemoryBackend())

async def get_next_race_end():
    async with httpx.AsyncClient() as client:
        try:
	   # Use f1_latest API to fetch race time for smart caching
            r = await client.get(LAST_RACE_API_URL)
            data = r.json()
            next_event = data.get("next_event", {})
            race_dt_str = next_event.get("datetime")

            if race_dt_str:
                race_dt = datetime.fromisoformat(race_dt_str)
                race_dt = race_dt.astimezone(MT)
            return race_dt
        except Exception as e:
            print("Error fetching race time:", e)
            print("Used URL:", LAST_RACE_API_URL)
    return None

@router.get("/", summary="Fetch next track map")
async def get_dynamic_track_map():
    cache_key = "track_map_svg"
    cache = FastAPICache.get_backend()

    # Try cached version
    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(LAST_RACE_API_URL)
            resp.raise_for_status()
        except Exception as e:
            print("Fetch error:", e)
            print("URL:", LAST_RACE_API_URL)
            return PlainTextResponse(f"Failed to fetch race info: {str(e)}", status_code=502)
        

    try:
        data = resp.json()
        race = data.get("race", [{}])[0]
        year = int(data.get("season", 2024)) - 1
        circuit = race.get("circuit")
        country = circuit.get("country")
        city = circuit.get("city")
        gp = city + " " + country
        race_dt_str = race.get("schedule", {}).get("race", {}).get("datetime_rfc3339")

        if not gp or not race_dt_str:
            raise ValueError("Missing circuitId or race time in API response")

        # Cacge logic.
        # Doesn't use same logic as current/drivers/constructors due to not needing to
        # reload the track map between weekend events 
        event_end = await get_next_race_end()
        if event_end:
            expire = int((event_end - datetime.now(MT)).total_seconds()) 
            expiry_dt = event_end + timedelta(hours=4)
        else: 
            expire = 3600
            expiry_dt = datetime.now(MT) + timedelta(hours=1)


        try:
            pit_stops = pit_constructor_calculator(current_year, points)
        except Exception as e:
            raise ValueError("Could not generate pit constructors.")
        await cache.set(cache_key, pit_stops, expire=expire)

        return pit_stops

    except Exception as e:
        return PlainTextResponse(f"Failed to generate pit stop constructors: {str(e)}", status_code=500)
