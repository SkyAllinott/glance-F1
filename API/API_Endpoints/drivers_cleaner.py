from fastapi import APIRouter
from fastapi_cache import FastAPICache
import httpx
from datetime import datetime, timedelta
import hashlib
import json

from .helpers.functions import country_to_code, get_next_race_end, format_team_name
from .helpers.global_vars import NEXT_RACE_API_URL, country_correction_map, default_expire
from .helpers.time_functions import MT, UTC

router = APIRouter()

def make_signature(results):
    return hashlib.md5(json.dumps(results, 
        sort_keys=True).encode()).hexdigest()

@router.get("/", summary="Fetch current drivers championship")
async def get_drivers_championship():
    cache = FastAPICache.get_backend()
    cache_key = "drivers_championship"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        response = await client.get("https://f1api.dev/api/current/drivers-championship", timeout=60)
        if response.status_code != 200:
            return {"error": "Failed to fetch data"}

        data = response.json()

    drivers = data.get("drivers_championship", [])
    results = []
    for entry in drivers:
        driver = entry.get("driver", {})
        team = entry.get("team", {})
        country = driver.get("nationality", "")
        if country in country_correction_map:
            country = country_correction_map[country]
        results.append({
            "surname": driver.get("surname"),
            "position": entry.get("position"),
            "points": entry.get("points"),
	        "teamId": format_team_name(team.get("teamId")),
            "country": country,
            "flag": country_to_code(country)
        })

    # Cache until race ends or 1 hour (in case f1/last is down or something)
    now = datetime.now(MT)
    race_dt = await get_next_race_end()

    cached = await cache.get(cache_key)
    old_signature = cached.get("result_signature") if cached else None
    new_signature = make_signature(results)
    if race_dt:
        if race_dt > now:
            expire = int((race_dt - now).total_seconds())
            expiry_dt = race_dt
        elif now < race_dt + timedelta(seconds=default_expire):
            expiry_dt = race_dt + timedelta(seconds=default_expire)
            expire = int((expiry_dt - now).total_seconds())
        else:
            expire = default_expire
            expiry_dt = now + timedelta(seconds=expire)

            if old_signature and old_signature != new_signature:
                async with httpx.AsyncClient() as client:
                    r = await client.get(NEXT_RACE_API_URL)
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
        "drivers": results,
        "result_signature": new_signature}

    await cache.set(cache_key, response_data, expire=expire)
    return response_data