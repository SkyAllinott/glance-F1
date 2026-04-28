import pytz
import os
from datetime import datetime, timedelta
import pycountry
import httpx

# Global Variables
NEXT_RACE_API_URL = "http://localhost:4463/f1/next_race/"

# Where API outputs don't match nice values
country_correction_map = {
        "New Zealander": "New Zealand",
        "Italian": "Italy",
        "Argentine": "Argentina"
    }

# For caching, the default polling time is 1 hour
default_expire = 3600

# Timezone information
TZ = os.environ.get("TIMEZONE").strip()
if TZ not in pytz.all_timezones:
    raise ValueError('Invalid time zone selection')
MT = pytz.timezone(TZ)
UTC = pytz.utc

# Convert to timezone function
def convert_to_mt(date_str, time_str):
    if not date_str or not time_str:
        return None
    dt_utc = datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M:%SZ")
    dt_utc = UTC.localize(dt_utc)
    return dt_utc.astimezone(MT)

# Use to sort season schedule to find next event
def get_datetime(item):
    dt_str = item[1].get("datetime_rfc3339")
    try:
        return datetime.fromisoformat(dt_str) if dt_str else datetime.max.replace(tzinfo=MT)
    except Exception:
        return datetime.max.replace(tzinfo=MT)
    
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

# Fetch race end results from NEXT_RACE_API_URL and use it for caching and event timing information
async def get_next_race_end():
    async with httpx.AsyncClient() as client:
        try:
	   # Use f1_latest API to fetch race time for smart caching
            r = await client.get(NEXT_RACE_API_URL)
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
            print("Used URL:", NEXT_RACE_API_URL)
    return None