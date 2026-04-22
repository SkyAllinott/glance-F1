from fastapi import APIRouter
from fastapi_cache import FastAPICache
import httpx
from datetime import datetime, timedelta

from API_Endpoints.common.countries import country_to_code, normalize_country
from API_Endpoints.common.formatting import format_team_name
from API_Endpoints.common.races import get_next_race_end, NEXT_RACE_API_URL
from API_Endpoints.common.signatures import make_signature
from API_Endpoints.common.time import MT, UTC

router = APIRouter()

@router.get("/", summary="Fetch current drivers championship")
async def get_drivers_championship():
    cache = FastAPICache.get_backend()
    cache_key = "drivers_championship"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        response = await client.get("https://f1api.dev/api/current/drivers-championship")
        if response.status_code != 200:
            return {"error": "Failed to fetch data"}

        data = response.json()

    drivers = data.get("drivers_championship", [])
    results = []
    for entry in drivers:
        driver = entry.get("driver", {})
        team = entry.get("team", {})
        country = normalize_country(driver.get("nationality", ""))
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
        elif now < race_dt + timedelta(hours = 1):
            expiry_dt = race_dt + timedelta(hours=1)
            expire = int((expiry_dt - now).total_seconds())
        else:
            expire = 3600
            expiry_dt = now + timedelta(seconds=3600)

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
