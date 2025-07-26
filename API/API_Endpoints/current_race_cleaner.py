from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import httpx
from datetime import datetime, timedelta
import pytz
import os
import fastf1

router = APIRouter()

# Timezone information
TZ = os.environ.get("TIMEZONE").strip()
if TZ not in pytz.all_timezones:
    raise ValueError('Invalid time zone selection')
MT = pytz.timezone(TZ)
UTC = pytz.utc

@router.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend())

# Convert to timezone function
def convert_to_mt(date_str, time_str):
    if not date_str or not time_str:
        return None
    dt_utc = datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M:%SZ")
    dt_utc = UTC.localize(dt_utc)
    return dt_utc.astimezone(MT)

@router.get("/", summary="Fetch next race")
async def get_next_race():
    cache = FastAPICache.get_backend()
    cache_key = "f1:next_race"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        try:
            # Get data from current season
            response = await client.get("https://f1api.dev/api/" + str(datetime.now().year))
            if response.status_code != 200:
                return {"error": "Failed to fetch race schedule"}
            calendar_data = response.json()
        except Exception as e:
            return {"error": f"Exception while fetching: {e}"}

    races = sorted(calendar_data.get("races", []), key=lambda r: r.get("schedule", {}).get("race", {}).get("date", ""))

    # Loop through list in order until find first race with date past today. 
    next_race = None
    now = datetime.utcnow()
    for race in races:
        race_date_str = race.get("schedule", {}).get("race", {}).get("date")
        race_time_str = race.get("schedule", {}).get("race", {}).get("time")
        if not race_date_str or not race_time_str:
            continue
        race_datetime = datetime.strptime(f"{race_date_str}T{race_time_str}", "%Y-%m-%dT%H:%M:%SZ")
        if race_datetime >= now:
            next_race = race
            break

    if not next_race:
        return {"message": "No upcoming race found"}

    # Convert schedule times
    schedule = next_race.get("schedule", {})
    for session, val in schedule.items():
        if val["date"] and val["time"]:
            dt_mt = convert_to_mt(val["date"], val["time"])
            val["date"] = dt_mt.strftime("%Y-%m-%d")
            val["time"] = dt_mt.strftime("%I%p").replace('0', '')
            val["datetime_rfc3339"] = dt_mt.isoformat()

    # Clean up race name
    year = calendar_data.get("season")
    calendar_round = next_race.get("round")

    event_details = fastf1.get_event(year = year, gp = calendar_round)
    next_race["raceName"] = event_details.EventName

    # Circuit processing
    circuit = next_race.get("circuit", {})
    if "circuitLength" in circuit:
        try:
            raw_length = int(circuit["circuitLength"].replace("km", "").strip())
            circuit["circuitLengthKm"] = raw_length / 1000.0
        except Exception:
            circuit["circuitLengthKm"] = None

    # Fastest driver name formatting
    fastest_driver_id = circuit.get("fastestLapDriverId")
    if fastest_driver_id:
        name_parts = fastest_driver_id.replace("_", " ").split(" ")
        circuit["fastestLapDriverName"] = name_parts[-1].capitalize()

    # Correct laptime formatting 
    fastest_lap_time = circuit.get("lapRecord")
    if fastest_lap_time:
        circuit["lapRecord"] = ".".join(fastest_lap_time.rsplit(":", 1))

    # Compute total distance
    laps = next_race.get("laps")
    if laps and circuit.get("circuitLengthKm") is not None:
        next_race["totalDistanceKm"] = round(laps * circuit["circuitLengthKm"], 2)
    else:
        next_race["totalDistanceKm"] = None


    # Select next event
    def get_datetime(item):
        dt_str = item[1].get("datetime_rfc3339")
        try:
            return datetime.fromisoformat(dt_str) if dt_str else datetime.max.replace(tzinfo=MT)
        except Exception:
            return datetime.max.replace(tzinfo=MT)

    sorted_schedule = sorted(schedule.items(), key=get_datetime)

    session_name_readable = {
        "fp1": "Free Practice 1",
        "fp2": "Free Practice 2",
        "fp3": "Free Practice 3",
        "qualy": "Qualifying",
        "sprintQualy": "Sprint Qualifying",
        "sprintRace": "Sprint Race",
        "race": "Race"
    }

    next_event = None
    try:
        detail_level = os.environ.get("EVENT_DETAIL").strip()
    except Exception:
        detail_level = 'main'

    for session_name, session_data in sorted_schedule:
        event_datetime_str = session_data.get("datetime_rfc3339")
        event_date_str = session_data.get("date")
        event_time_str = session_data.get("time")
        if not event_datetime_str:
            continue

        if detail_level == "main":
            print("Showing Quali and Race Events Only")
            if session_name in ('fp1', 'fp2', 'fp3'):
                continue
        elif detail_level == "race":
            print("Showing Races Only")
            if session_name not in ('race', 'sprintRace'):
                continue
        elif detail_level == "detailed":
            print("Showing All Events")
        else:
            raise ValueError("Select one of: 'main', 'race', or 'detailed'. No selection defaults to main.")

        try:
            dt = datetime.fromisoformat(event_datetime_str)
            if dt > datetime.now(MT): 
                next_event = {
                    "session": session_name_readable.get(session_name, session_name.title()),
                    "date": event_date_str,
                    "time": event_time_str,
                    "datetime": event_datetime_str
                }
                break
        except Exception:
            continue


    # Cache expiry logic based on race time
    try:
        race_dt_str = next_event.get("datetime")
        if race_dt_str:
            race_dt = datetime.fromisoformat(race_dt_str).astimezone(MT)
            expiry_dt = race_dt + timedelta(hours=4.25)
            expire = int((race_dt + timedelta(hours=4.25) - datetime.now(MT)).total_seconds())
        else:
            expiry_dt = datetime.now(MT) + timedelta(hours=1)
            expire = 3600  # fallback
    except Exception as e:
        print("Cache expiry fallback due to error:", e)
        expiry_dt = datetime.now(MT) + timedelta(hours=1)
        expire = 3600

    # Output data
    response_data = {
        "season": calendar_data.get("season"),
        "round": next_race.get("round"),
        "timezone": TZ,
        "next_event": next_event,
        "cache_expires": expiry_dt.isoformat(),
        "race": [next_race]
    }

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
