from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse
import fastf1
import httpx
import io
from datetime import datetime, timedelta
import pytz
import os
import hashlib
import json
from fastapi_cache import FastAPICache

from .map_generator import generate_track_map_svg, remove_accents
from ..helpers.global_vars import NEXT_RACE_API_URL
from ..helpers.time_functions import MT

router = APIRouter()

def make_signature(data):
    return hashlib.md5(json.dumps(data, 
        sort_keys=True).encode()).hexdigest()

def generate_historical_track_map(data):
    race = data.get("race", [{}])[0]
    circuit = race.get("circuit") or {}
    country = circuit.get("country")
    city = circuit.get("city")
    track = circuit.get("circuitName")
    race_name = race.get("raceName")
    current_year = int(data.get("season", datetime.now().year))

    errors = []
    for year in range(current_year - 1, 2017, -1):
        attempts = []

        try:
            schedule = fastf1.get_event_schedule(year)
            matching_events = [
                event for _, event in schedule.iterrows()
                if historical_event_matches(event, city, country, race_name)
            ]
        except Exception as e:
            errors.append(f"{year} schedule: {type(e).__name__}: {e}")
            matching_events = []

        for event in matching_events:
            attempts.append({
                "year": year,
                "race_name": event.get("EventName"),
                "track": track,
                "session_type": "Q",
            })

        if city and country and not attempts:
            attempts.append({
                "year": year,
                "city": city,
                "country": country,
                "track": track,
                "session_type": "Q",
            })
        if race_name and not attempts:
            attempts.append({
                "year": year,
                "race_name": race_name,
                "track": track,
                "session_type": "Q",
            })

        for kwargs in attempts:
            try:
                return generate_track_map_svg(**kwargs)
            except Exception as e:
                errors.append(f"{year}: {type(e).__name__}: {e}")

    raise ValueError("Could not fetch a historical track map. " + " | ".join(errors[-6:]))

def normalize_name(value):
    return remove_accents(str(value or "")).casefold().strip()

def historical_event_matches(event, city, country, race_name):
    location_matches = city and normalize_name(event.get("Location")) == normalize_name(city)
    country_matches = country and normalize_name(event.get("Country")) == normalize_name(country)
    event_name_matches = (
        race_name
        and normalize_name(event.get("EventName")) == normalize_name(race_name)
    )

    return (location_matches and country_matches) or event_name_matches

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
    race_dt_str = race.get("schedule", {}).get("race", {}).get("datetime_rfc3339")

    if not race_dt_str:
        return PlainTextResponse("Missing race datetime", status_code=500)
    race_dt = datetime.fromisoformat(race_dt_str).astimezone(MT)
    now = datetime.now(MT)
    
    if cached and old_signature == upstream_signature:
        return Response(content=cached["svg"], media_type="image/svg+xml")

    if not race_dt_str:
        raise ValueError("Missing race time in API response")

    try:
        svg_content = generate_historical_track_map(data)
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

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
