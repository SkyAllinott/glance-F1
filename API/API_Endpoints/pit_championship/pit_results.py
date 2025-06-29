import fastf1
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import io
import os 
import re
import time

def pit_constructor_calculator(year, points):
    session_info_query = 'https://api.openf1.org/v1/sessions?session_type=Race&year=' + str(year) + '&session_name=Race'
    session_info = requests.get(session_info_query).json()

    session_key = []
    for event in range(0, len(session_info)):
        session_key.append(session_info[event].get('session_key'))


    data = []
    for session in session_key:
        # Race control to deal with drive through pit with safety car
        race_control_query = f'https://api.openf1.org/v1/race_control?session_key={session}'

        try:
            race_control_data = requests.get(race_control_query).json()
            time.sleep(0.2)
            if not isinstance(race_control_data, list):
                print(f"[WARN] Unexpected race_control_data format for session {session}: {race_control_data}")
                race_control_data = []
        except Exception as e:
            print(f"[ERROR] Failed to fetch race control data for session {session}: {e}")
            race_control_data = []

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

        pit_query = f'https://api.openf1.org/v1/pit?session_key={session}'
        try:
            pit_stops = requests.get(pit_query).json()
            time.sleep(0.2)
            if isinstance(pit_stops, list):
                pit_stops_df = pd.DataFrame.from_dict(pit_stops)
            else:
                print(f"[WARN] Unexpected pit_stops format for session {session}: {pit_stops}")
                pit_stops_df = pd.DataFrame()
        except Exception as e:
            print(f"[ERROR] Failed to fetch pit stops for session {session}: {e}")
            pit_stops_df = pd.DataFrame()

        # Skip if no valid data
        if pit_stops_df.empty:
            continue

        valid_pit_stops = pit_stops_df[~pit_stops_df['lap_number'].isin(invalid_laps)]

        


        average = valid_pit_stops.groupby('driver_number', as_index=False).agg(
            pitstop_mean = ('pit_duration', 'mean'), 
            pitstop_min = ('pit_duration', 'min')
        )


        average['race'] = [x for x in session_info if x["session_key"]== session][0]['circuit_short_name']

        cols = ['pitstop_mean', 'pitstop_min']
        average['rank'] = average.sort_values(cols, ascending=True).groupby(cols, sort=False).ngroup() + 1

        average['points'] = average['rank'].map(points).fillna(0)

        try:
            drivers_data = requests.get(f'https://api.openf1.org/v1/drivers?session_key={session}').json()
            if isinstance(drivers_data, list) and all(isinstance(d, dict) for d in drivers_data):
                drivernumber_name_dict = {
                    d['driver_number']: d['last_name']
                    for d in drivers_data
                    if 'driver_number' in d and 'last_name' in d
                }
                drivernumber_team_dict = {
                    d['driver_number']: d['team_name']
                    for d in drivers_data
                    if 'driver_number' in d and 'team_name' in d
                }
            else:
                print(f"[WARN] Unexpected format in drivers_data for session {session}: {drivers_data}")
                drivernumber_name_dict = {}
                drivernumber_team_dict = {}
        except Exception as e:
            print(f"[ERROR] Failed to fetch drivers data for session {session}: {e}")
            drivernumber_name_dict = {}
            drivernumber_team_dict = {}

        average['name'] = average['driver_number'].map(drivernumber_name_dict)
        average['teamName'] = average['driver_number'].map(drivernumber_team_dict)

        average = average.sort_values(by='rank')
        data.append(average)

    if not data:
        return pd.DataFrame(columns=["teamName", "points"])
    
    df = pd.concat(data, ignore_index=True)

    team_results = df.groupby('teamName', as_index=False).agg(
        points = ('points', 'sum')
    )

    results = team_results.sort_values('points', ascending=False)
    return results 