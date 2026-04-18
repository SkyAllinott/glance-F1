from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import httpx
from datetime import datetime, timedelta
import pytz
import os
import fastf1
import hashlib 
import json

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

def make_signature(race):
    relevant = {
        "winner": race.get("winner")
    }
    return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()

@router.get("/", summary="Fetch next race")
async def get_next_race():
    cache = FastAPICache.get_backend()
    cache_key = "f1:next_race"

    cached = await cache.get(cache_key)
    old_signature = None

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
    now = datetime.now(MT)
    for i, race in enumerate(races, start = 1):
        if datetime.now().year == 2026 and i in (4, 5):
            continue
        race_date_str = race.get("schedule", {}).get("race", {}).get("date")
        race_time_str = race.get("schedule", {}).get("race", {}).get("time")
        if not race_date_str or not race_time_str:
            continue
        
        race_datetime_utc = datetime.strptime(f"{race_date_str}T{race_time_str}", "%Y-%m-%dT%H:%M:%SZ")
        race_datetime_utc = UTC.localize(race_datetime_utc)

        race_datetime_local = race_datetime_utc.astimezone(MT)
        if race_datetime_local >= now:
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
            val["time"] = dt_mt.strftime("%-I:%M%p")
            val["datetime_rfc3339"] = dt_mt.isoformat()

    # Clean up race name
    year = calendar_data.get("season")
    calendar_round = next_race.get("round")

    if year == 2026 and calendar_round >= 6:
        calendar_round = calendar_round - 2

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

    new_signature = make_signature(next_race)

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
    now = datetime.now(MT)

    # Race time for post race caching logic
    race_session = next_race.get("schedule", {}).get("race")
    race_dt = None
    if race_session and race_session.get("datetime_rfc3339"):
        race_dt = datetime.fromisoformat(race_session["datetime_rfc3339"])

    if next_event and next_event.get("datetime"):
        try:
            next_event_dt = datetime.fromisoformat(next_event["datetime"])
            if next_event_dt > now:
                # Cache until next session starts
                expire = max(1, int((next_event_dt - now).total_seconds()))
                expiry_dt = next_event_dt
            else:
                expire = 3600
                expiry_dt = now + timedelta(seconds=expire)
        except Exception:
            expire = 3600
            expiry_dt = now + timedelta(seconds=expire)

    elif race_dt:
        if now < race_dt + timedelta(hours=1):
            # Race just ended, wait minimum of 1 hour
            expiry_dt = race_dt + timedelta(hours=1)
            expire = int((expiry_dt - now).total_seconds())
        else:
            # 1 hour after race, poll every hour
            expire = 3600
            expiry_dt = now + timedelta(seconds=expire)

            if old_signature and old_signature != new_signature:
                print("Results updated, polling stopped")
                try:
                    next_race_dt = None 

                    for race in races:
                        r_date = race.get("schedule", {}).get("race", {}).get("date")
                        r_time = race.get("schedule", {}).get("race", {}).get("time")

                        if not r_date or not r_time:
                            continue

                        dt_utc = datetime.strptime(f"{r_date}T{r_time}", "%Y-%m-%dT%H:%M:%SZ")
                        dt_utc = UTC.localize(dt_utc)
                        dt_local = dt_utc.astimezone(MT)

                        if dt_local > race_dt:
                            next_race_dt = dt_local
                            break

                    if next_race_dt:
                        expire = int((next_race_dt - now).total_seconds())
                        expiry_dt = next_race_dt
                    else:
                        expire = 86400
                        expiry_dt = now + timedelta(seconds = expire)
                except Exception as e:
                    print("Next race cache fallback:", e)
                    expire = 86400
                    expiry_dt = now + timedelta(seconds=expire)
    else:
        expire = 3600
        expiry_dt = now + timedelta(seconds=expire)


    # Output data
    response_data = {
        "season": calendar_data.get("season"),
        "round": calendar_round,
        "timezone": TZ,
        "next_event": next_event,
        "cache_expires": expiry_dt.isoformat(),
        "race": [next_race]
    }

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
