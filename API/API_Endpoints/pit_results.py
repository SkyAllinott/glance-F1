import fastf1
import requests
import pandas as pd
from datetime import datetime, timedelta
import json

year = datetime.now().year

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


session_info_query = 'https://api.openf1.org/v1/sessions?session_type=Race&year=' + str(year) + '&session_name=Race'
session_info = requests.get(session_info_query).json()

session_key = []
for event in range(0, len(session_info)):
    session_key.append(session_info[event].get('session_key'))




data = []
for session in session_key:
    # Race control to deal with drive through pit with safety car
    race_control_query = 'https://api.openf1.org/v1/race_control?session_key=' + str(session)
    race_control_data = requests.get(race_control_query).json()

    safety_through_pit = [x for x in race_control_data if x['message'] == 'SAFETY CAR THROUGH THE PIT LANE']
    safety_through_pit_done = [x for x in race_control_data if x['message'] == 'SAFETY CAR WILL USE START/FINISH STRAIGHT']

    lap_start_safety_through_pit = [entry['lap_number'] for entry in safety_through_pit if 'lap_number' in entry]
    lap_end_safety_through_pit = [entry['lap_number'] for entry in safety_through_pit_done if 'lap_number' in entry]

    through_pit_periods = [{'start': s, 'end': e} for s, e in zip(lap_start_safety_through_pit, lap_end_safety_through_pit)]

    sc_laps = set()
    for period in through_pit_periods:
        sc_laps.update(range(period['start'], period['end'] + 1))

    # Deal with red flags
    red_flags = [x for x in race_control_data if x['flag'] == 'RED']
    lap_red_flags = [entry['lap_number'] for entry in red_flags if 'lap_number' in entry]

    # Combine drive through and red flags 
    invalid_laps = sc_laps.union(set(lap_red_flags))

    pit_query = 'https://api.openf1.org/v1/pit?session_key=' + str(session)

    pit_stops = requests.get(pit_query).json()

    pit_stops_df = pd.DataFrame.from_dict(pit_stops)

    valid_pit_stops = pit_stops_df[~pit_stops_df['lap_number'].isin(invalid_laps)]

    


    average = valid_pit_stops.groupby('driver_number', as_index=False).agg(
        pitstop_mean = ('pit_duration', 'mean'), 
        pitstop_min = ('pit_duration', 'min')
    )


    average['race'] = [x for x in session_info if x["session_key"]== session][0]['circuit_short_name']

    cols = ['pitstop_mean', 'pitstop_min']
    average['rank'] = average.sort_values(cols, ascending=True).groupby(cols, sort=False).ngroup() + 1

    average['points'] = average['rank'].map(points).fillna(0)

    drivers_data = requests.get('https://api.openf1.org/v1/drivers?session_key=' + str(session)).json()
    drivernumber_name_dict = {drivers['driver_number']: drivers['last_name'] for drivers in drivers_data}
    drivernumber_team_dict = {drivers['driver_number']: drivers['team_name'] for drivers in drivers_data}

    average['name'] = average['driver_number'].map(drivernumber_name_dict)
    average['teamName'] = average['driver_number'].map(drivernumber_team_dict)

    average = average.sort_values(by='rank')
    data.append(average)

df = pd.concat(data, ignore_index=True)

team_results = df.groupby('teamName', as_index=False).agg(
    points = ('points', 'sum')
)

team_results.sort_values('points', ascending=False)