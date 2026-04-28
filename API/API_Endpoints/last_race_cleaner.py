from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import pycountry
import httpx
import re
from datetime import datetime, timedelta
import pytz
import os
import fastf1
from API_Endpoints.functions import TZ, MT, UTC, country_to_code, get_next_race_end, NEXT_RACE_API_URL, country_correction_map

router = APIRouter()

def parse_dnf_laps(time_str: str):
    match = re.match(r"DNF\s*\((\d+)\)", time_str)
    if match:
        return int(match.group(1))
    return None

@router.get("/", summary="Fetch last race results")
async def get_last_race():
    cache = FastAPICache.get_backend()
    cache_key = "f1:last_race"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://f1api.dev/api/current/last/race", timeout=60)
            if response.status_code != 200:
                return {"error": "Failed to fetch last race"}
            data = response.json()
        except Exception as e:
            return {"error": f"Exception while fetching: {e}"}

    race = data.get("races", {})
    season = data.get("season")

    try:
        event_details = fastf1.get_event(year=season, gp=race.get("round"))
        race_name = event_details.EventName
    except Exception:
        race_name = race.get("raceName", "Unknown")

    results = []
    for entry in race.get("results", []):
        driver = entry.get("driver", {})
        team = entry.get("team", {})
        position = entry.get("position")
        time_str = entry.get("time", "")

        nationality = driver.get("nationality", "")
        if nationality in country_correction_map:
            nationality = country_correction_map[nationality]

        is_dnf = str(position) == "NC"
        dnf_laps = parse_dnf_laps(time_str) if is_dnf else None
        surname = driver.get("surname")
        if surname == "Kimi Antonelli":
            surname = "Antonelli"

        result = {
            "position": position,
            "surname": surname,
            "flag": country_to_code(nationality),
            "teamId": team.get("teamId"),
            "time": time_str,
            "dnf_laps": dnf_laps,
        }
        results.append(result)

    expire = 86400
    expiry_dt = datetime.now(MT) + timedelta(days=1)

    response_data = {
        "season": season,
        "round": race.get("round"),
        "raceName": race_name,
        "date": race.get("date"),
        "cache_expires": expiry_dt.isoformat(),
        "results": results,
    }

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
