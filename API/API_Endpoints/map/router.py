from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse
import httpx
from datetime import datetime, timedelta

from fastapi_cache import FastAPICache
from API_Endpoints.common.races import NEXT_RACE_API_URL
from API_Endpoints.common.signatures import make_signature
from API_Endpoints.common.time import MT, UTC
from .map_generator import generate_track_map_svg

router = APIRouter()

@router.get("/", summary="Fetch next track map")
async def get_dynamic_track_map():
    cache_key = "track_map_svg"
    cache = FastAPICache.get_backend()

    # Try cached version
    cached = await cache.get(cache_key)
    old_signature = cached.get("signature") if cached else None

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(NEXT_RACE_API_URL, timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return PlainTextResponse(f"Failed to fetch race info: {str(e)}", status_code=502)
        
    upstream_signature = make_signature({
        "race": data.get("race"),
        "next_event": data.get("next_event")
    })


    race = data.get("race", [{}])[0]
    year = int(data.get("season", 2024)) - 1
    circuit = race.get("circuit")
    if not circuit:
        return PlainTextResponse("Missing circuit info", status_code=500)

    country = circuit.get("country")
    city = circuit.get("city")
    if not city or not country:
        return PlainTextResponse("Missing circuit location", status_code=500)

    gp = city + " " + country
    race_name = race.get("raceName")
    race_dt_str = race.get("schedule", {}).get("race", {}).get("datetime_rfc3339")

    if not race_dt_str:
        return PlainTextResponse("Missing race datetime", status_code=500)
    race_dt = datetime.fromisoformat(race_dt_str).astimezone(MT)
    now = datetime.now(MT)
    
    if cached and old_signature == upstream_signature:
        return Response(content=cached["svg"], media_type="image/svg+xml")

    if not gp or not race_dt_str:
        raise ValueError("Missing circuitId or race time in API response")

    try:
        svg_content = generate_track_map_svg(year, city, country, circuit.get("circuitName"), "Q")
    except Exception as e:
        try:
            svg_content = generate_track_map_svg(year = year, race_name = race_name, track = circuit.get("circuitName"), session_type = "Q")
        except Exception as fallback_error:
            return PlainTextResponse(
                f"Could not generate map: {repr(fallback_error)}",
                status_code=500,
            )

    if race_dt > now:
        expire = int((race_dt - now).total_seconds())
        expiry_dt = race_dt
    elif now < race_dt + timedelta(hours = 1):
        expiry_dt = race_dt + timedelta(hours=1)
        expire = int((expiry_dt - now).total_seconds())
    else:
        expire = 3600
        expiry_dt = now + timedelta(seconds=3600)

        if old_signature and old_signature != upstream_signature:
            print("Race changed, cache invalid, fetching new map")

            next_dt = data.get("next_event", {}).get("datetime")
            if next_dt:
                next_race_dt = datetime.fromisoformat(next_dt)

                if next_race_dt.tzinfo is None:
                    next_race_dt = UTC.localize(next_race_dt)

                next_race_dt = next_race_dt.astimezone(MT)

                expire = int((next_race_dt - now).total_seconds())
                expiry_dt = next_race_dt

    expire_seconds = max(int((expiry_dt - now).total_seconds()), 60)

    await cache.set(cache_key, {
        "svg": svg_content,
        "signature": upstream_signature
        }, expire=expire_seconds)

    return Response(content=svg_content, media_type="image/svg+xml")
