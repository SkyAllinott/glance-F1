from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse
import httpx
import io
from datetime import datetime, timedelta
import pytz
import os
import hashlib
import json
from fastapi_cache import FastAPICache

from .map_generator import generate_track_map_svg
from ..helpers.global_vars import NEXT_RACE_API_URL
from ..helpers.time_functions import MT

router = APIRouter()

def make_signature(data):
    return hashlib.md5(json.dumps(data, 
        sort_keys=True).encode()).hexdigest()

@router.get("/", summary="Fetch next track map")
async def get_dynamic_track_map():
    cache_key = "track_map_svg"
    cache = FastAPICache.get_backend()

    # Try cached version
    cached = await cache.get(cache_key)
    old_signature = cached.get("signature") if cached else None

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(NEXT_RACE_API_URL)
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
    country = circuit.get("country")
    city = circuit.get("city")
    gp = city + " " + country
    race_name = race.get("raceName")
    race_dt_str = race.get("schedule", {}).get("race", {}).get("datetime_rfc3339")

    if not race_dt_str:
        return PlainTextResponse("Missing race datetime", status_code=500)
    race_dt = datetime.fromisoformat(race_dt_str).astimezone(MT)
    now = datetime.now(MT)
    
    if cached:
        return Response(content=cached["svg"], media_type="image/svg+xml")

    if not gp or not race_dt_str:
        raise ValueError("Missing circuitId or race time in API response")

    try:
        svg_content = generate_track_map_svg(year, city, country, circuit.get("circuitName"), "Q")
    except Exception as e:
        try:
            svg_content = generate_track_map_svg(year = year, race_name = race_name, track = circuit.get("circuitName"), session_type = "Q")
        except:
            raise ValueError("Could not print map. Likely catching FastF1 pulling wrong track.")
    svg_bytes = svg_content.encode("utf-8")

    if now > race_dt:
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
                    next_race_dt = pytz.utc.localize(next_race_dt)

                next_race_dt = next_race_dt.astimezone(MT)

                expire = int((next_race_dt - now).total_seconds())
                expiry_dt = next_race_dt

    expire_seconds = max(int((expiry_dt - now).total_seconds()), 60)

    await cache.set(cache_key, {
        "svg": svg_content,
        "signature": upstream_signature
        }, expire=expire_seconds)

    return Response(content=svg_content, media_type="image/svg+xml")
