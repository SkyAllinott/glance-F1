import pycountry
import httpx
from .global_vars import NEXT_RACE_API_URL
from .time_functions import MT, UTC
from datetime import datetime 

# Format team name for nice display
def format_team_name(team_id: str) -> str:
    if not team_id:
        return ""
    exceptions = {
        "rb": "RB"
    }
    if team_id in exceptions:
        return exceptions[team_id]
    return team_id.replace("_", " ").title()
    
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