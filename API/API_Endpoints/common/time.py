from datetime import datetime
import os

import pytz


TZ = os.environ.get("TIMEZONE").strip()
if TZ not in pytz.all_timezones:
    raise ValueError("Invalid time zone selection")

MT = pytz.timezone(TZ)
UTC = pytz.utc


def convert_to_mt(date_str, time_str):
    if not date_str or not time_str:
        return None

    dt_utc = datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M:%SZ")
    dt_utc = UTC.localize(dt_utc)
    return dt_utc.astimezone(MT)
