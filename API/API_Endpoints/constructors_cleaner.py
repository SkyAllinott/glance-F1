from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import pycountry
import httpx
from datetime import datetime, timedelta
import pytz
import os
import hashlib
import json

router = APIRouter()

LAST_RACE_API_URL = "http://localhost:4463/f1/next_race/"

TZ = os.environ.get("TIMEZONE").strip()
if TZ not in pytz.all_timezones:
    raise ValueError('Invalid time zone selection')
MT = pytz.timezone(TZ)
UTC = pytz.utc

# Initialize caching
@router.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend())

# The API uses some weird country names that don't match standard
def country_to_code(country_name: str) -> str:
    replacements = {
        "Great Britain": "GB",
        "United States": "US",
    }
    try:
        country_name = replacements.get(country_name, country_name)
        return pycountry.countries.lookup(country_name).alpha_2.lower()
    except Exception:
        return ""
    
def make_signature(results):
    return hashlib.md5(json.dumps(results, 
        sort_keys=True).encode()).hexdigest()

async def get_next_race_end():
    async with httpx.AsyncClient() as client:
        try:
	   # Use f1_latest API to fetch race time for smart caching
            r = await client.get(LAST_RACE_API_URL)
            data = r.json()
            next_event = data.get("next_event", {})
            race_dt_str = next_event.get("datetime")

            if not race_dt_str:
                return None
            
            race_dt = datetime.fromisoformat(race_dt_str)

            if race_dt.tzinfo is None:
                race_dt = UTC.localize(race_dt)

            return race_dt.astimezone(MT)
        
        except Exception as e:
            print("Error fetching race time:", e)
            print("Used URL:", LAST_RACE_API_URL)
    return None

@router.get("/", summary="Fetch current constructors championship")
async def get_constructors_championship():
    cache = FastAPICache.get_backend()
    cache_key = "constructors_championship"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        response = await client.get("https://f1api.dev/api/current/constructors-championship")
        if response.status_code != 200:
            return {"error": "Failed to fetch data"}

        data = response.json()

    constructors = data.get("constructors_championship", [])
    results = []
    for entry in constructors:

        # Clean up team names and get rid of standard boilerplate slop
        team = entry.get("team", {})
        team_name = team.get("teamName")
        for word in ['Formula 1', 'F1', 'Racing', 'Team', 'Scuderia']:
            team_name = team_name.replace(word, "").strip()
        country = team.get("country", "")
        results.append({
            "team": team_name,
            "position": entry.get("position"),
            "points": entry.get("points"),
            "wins": entry.get("wins") or 0,
            "country": country,
            "flag": country_to_code(country),
            "wiki": team.get("url")
        })

    # Cache until event ends or 1 hour (in case f1/last is down or something
    now = datetime.now(MT)
    race_dt = await get_next_race_end()

    cached = await cache.get(cache_key)
    old_signature = cached.get("result_signature") if cached else None
    new_signature = make_signature(results)
    if race_dt:
        if race_dt > now:
            expire = int((race_dt - now).total_seconds())
            expiry_dt = race_dt
        elif now < race_dt + timedelta(hours = 1):
            expiry_dt = race_dt + timedelta(hours=1)
            expire = int((expiry_dt - now).total_seconds())
        else:
            expire = 3600
            expiry_dt = now + timedelta(seconds=3600)

            if old_signature and old_signature != new_signature:
                async with httpx.AsyncClient() as client:
                    r = await client.get(LAST_RACE_API_URL)
                    data = r.json()

                    next_dt = data.get("next_event", {}).get("datetime")

                    if next_dt:
                        next_race_dt = datetime.fromisoformat(next_dt)

                        if next_race_dt.tzinfo is None:
                            next_race_dt = UTC.localize(next_race_dt)
                        next_race_dt = next_race_dt.astimezone(MT)

                        expire = int((next_race_dt - now).total_seconds())
                        expiry_dt = next_race_dt

    response_data = {
        "season": data.get("season"), 
        "cache_expires": expiry_dt.isoformat(),
        "constructors": results,
        "result_signature": new_signature}

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
