from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import pycountry
import httpx
from datetime import datetime, timedelta
import pytz
import os

router = APIRouter()

LAST_RACE_API_URL = "http://localhost:4463/f1/next_race/"

TZ = os.environ.get("TIMEZONE").strip()
if TZ not in pytz.all_timezones:
    raise ValueError('Invalid time zone selection')
MT = pytz.timezone(TZ)

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
    event_end = await get_next_race_end()
    if event_end:
        expire = int(((event_end + timedelta(hours = 4)) - datetime.now(MT)).total_seconds()) 
        expiry_dt = event_end + timedelta(hours=4)
    else: 
        expire = 3600
        expiry_dt = datetime.now(MT) + timedelta(hours=1)

    response_data = {
        "season": data.get("season"), 
        "cache_expires": expiry_dt.isoformat(),
        "constructors": results}

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
