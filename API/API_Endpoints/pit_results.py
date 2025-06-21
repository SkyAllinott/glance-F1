import fastf1
import requests
import pandas as pd
from datetime import datetime, timedelta
import json

year = datetime.now().year
request = requests.get("https://f1api.dev/api/" + str(year))

data = request.json()

races = sorted(data.get("races", []), key=lambda r: r.get("schedule", {}).get("race", {}).get("date", ""))

past_events = []
now = datetime.utcnow()
for race in races:
    race_date_str = race.get("schedule", {}).get("race", {}).get("date")
    race_time_str = race.get("schedule", {}).get("race", {}).get("time")
    race_datetime = datetime.strptime(f"{race_date_str}T{race_time_str}", "%Y-%m-%dT%H:%M:%SZ")
    if not race_date_str or not race_time_str:
        continue
    if race_datetime > now:
        break
    past_events.append(race.get("circuit"))

country = []
for event in range(0, len(past_events)):
    country.append(past_events[event].get('country'))

city = []
for event in range(0, len(past_events)):
    city.append(past_events[event].get('city'))

points = {
        1: 25,
        2: 18,
        3: 15,
        4: 12,
        5: 10,
        6: 8,
        7: 6,
        8: 4,
        9: 2,
        10: 1
    }

race_locations = [{'country': country, 'city': city} for country, city in zip(country, city)]
race_locations


session_info_query = 'https://api.openf1.org/v1/sessions?session_type=Race&year=2025&session_name=Race'
session_info = requests.get(session_info_query).json()

session_key = []
for event in range(0, len(session_info)):
    session_key.append(session_info[event].get('session_key'))
session_key



data = []
for session in session_key:
    pit_query = 'https://api.openf1.org/v1/pit?session_key=' + str(session)

    pit_stops = requests.get(pit_query).json()

    pit_stops_df = pd.DataFrame.from_dict(pit_stops)


    average = pit_stops_df.groupby('driver_number', as_index=False).agg(
        pitstop_mean = ('pit_duration', 'mean'), 
        pitstop_min = ('pit_duration', 'min')
    )


    race = [x for x in session_info if x["session_key"]== session][0]['circuit_short_name']

    cols = ['pitstop_mean', 'pitstop_min']
    average['rank'] = average.sort_values(cols, ascending=True).groupby(cols, sort=False).ngroup() + 1

    average['points'] = average['rank'].map(points).fillna(0)

    drivers_data = requests.get('https://api.openf1.org/v1/drivers?session_key=' + str(session)).json()
    drivernumber_name_dict = {drivers['driver_number']: drivers['last_name'] for drivers in drivers_data}
    drivernumber_team_dict = {drivers['driver_number']: drivers['team_name'] for drivers in drivers_data}

    average['name'] = average['driver_number'].map(drivernumber_name_dict)
    average['teamName'] = average['driver_number'].map(drivernumber_team_dict)

    average = average.sort_values(by='rank')

    data.append({
        "year": year,
        "race": race,
        "session_key": session,
        "pit_stops": average.to_dict(orient='records')
    })

data