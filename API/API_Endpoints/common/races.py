from datetime import datetime

import httpx

from API_Endpoints.common.time import MT, UTC


NEXT_RACE_API_URL = "http://localhost:4463/f1/next_race/"


async def get_next_race_end():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(NEXT_RACE_API_URL)
            data = response.json()
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
