from fastapi import APIRouter
from fastapi_cache import FastAPICache
import httpx
import re
from datetime import datetime, timedelta
import fastf1

from API_Endpoints.common.countries import country_to_code, normalize_country
from API_Endpoints.common.formatting import format_team_name
from API_Endpoints.common.time import MT, UTC

router = APIRouter()

LAST_RACE_API_URL = "https://f1api.dev/api/current/last/race"
CURRENT_SEASON_API_URL = "https://f1api.dev/api/{year}"
RACE_RESULT_API_URL = "https://f1api.dev/api/{year}/{round}/race"


def parse_dnf_laps(time_str: str):
    match = re.match(r"DNF\s*\((\d+)\)", time_str)
    if match:
        return int(match.group(1))
    return None


def extract_race(data):
    race = data.get("races") or data.get("race") or {}
    if isinstance(race, list):
        return race[0] if race else {}
    return race


async def fetch_last_race_data(client):
    try:
        response = await client.get(LAST_RACE_API_URL, timeout=20.0)
        response.raise_for_status()
        return response.json()
    except Exception as primary_error:
        print("Primary last race fetch failed:", repr(primary_error))

    season = datetime.now(MT).year
    response = await client.get(CURRENT_SEASON_API_URL.format(year=season), timeout=20.0)
    response.raise_for_status()
    calendar_data = response.json()

    now = datetime.now(MT)
    completed_rounds = []
    for race in sorted(calendar_data.get("races", []), key=lambda r: r.get("round", 0)):
        race_schedule = race.get("schedule", {}).get("race", {})
        race_date = race_schedule.get("date")
        race_time = race_schedule.get("time")
        if not race_date or not race_time:
            continue

        race_dt = datetime.strptime(f"{race_date}T{race_time}", "%Y-%m-%dT%H:%M:%SZ")
        race_dt = UTC.localize(race_dt).astimezone(MT)
        if race_dt < now:
            completed_rounds.append(race.get("round"))

    if not completed_rounds:
        raise ValueError("No completed race found in current season calendar")

    last_error = None
    for race_round in reversed(completed_rounds):
        try:
            response = await client.get(
                RACE_RESULT_API_URL.format(year=season, round=race_round),
                timeout=20.0,
            )
            response.raise_for_status()
            return response.json()
        except Exception as fallback_error:
            last_error = fallback_error
            print(f"Race result fetch failed for round {race_round}:", repr(fallback_error))

    raise last_error


@router.get("/", summary="Fetch last race results")
async def get_last_race():
    cache = FastAPICache.get_backend()
    cache_key = "f1:last_race"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        try:
            data = await fetch_last_race_data(client)
        except Exception as e:
            return {"error": f"Exception while fetching last race: {repr(e)}"}

    race = extract_race(data)
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

        nationality = normalize_country(driver.get("nationality", ""))

        is_dnf = str(position) == "NC"
        dnf_laps = parse_dnf_laps(time_str) if is_dnf else None
        surname = driver.get("surname")
        if surname == "Kimi Antonelli":
            surname = "Antonelli"

        result = {
            "position": position,
            "surname": surname,
            "flag": country_to_code(nationality),
            "teamId": format_team_name(team.get("teamId")),
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
