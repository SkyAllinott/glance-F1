import pytz
import os
from datetime import datetime, timedelta

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