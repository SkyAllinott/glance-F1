import fastf1
import requests
import pandas as pd
from datetime import datetime, timedelta
import json

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

year = datetime.now().year


session_info_query = 'https://api.openf1.org/v1/sessions?session_type=Race&session_name=Race&Year=' + str(year)
session_info = requests.get(session_info_query).json()

session_key = []
for event in range(0, len(session_info)):
    session_key.append(session_info[event].get('session_key'))
session_key



data = []
for session in session_key:
    print(session)
    pit_query = 'https://api.openf1.org/v1/pit?session_key=' + str(session)

    pit_stops = requests.get(pit_query).json()

    pit_stops_df = pd.DataFrame.from_dict(pit_stops)

    # Calculate mean duration for pit time for a given lap. 
    # This helps sort out red flags or retirements. 
    pits = pit_stops_df.groupby('lap_number', as_index=False).agg(
        pitstop_mean = ('pit_duration', 'mean'),
        pitstop_min = ('pit_duration', 'min'),
        drivers_in = ('driver_number', 'count')
    )

    # Use a modified IQR to define outliers. We only use it to remove outliers that are too
    # fast. Outliers which are too slow generally aren't bad data but a bad pit stop. 

    # Use pretty close to median for low side of estimation range.
    # The pit stops are generally only 2-3 seconds, so if they're driving through they
    # are very close to median
    pitstops_low_quantile = pits['pitstop_mean'].quantile(0.5)

    # A very long pit stop generally isn't an issue
    pitstops_high_quantile = pits['pitstop_mean'].quantile(0.95)
    iqr = pitstops_high_quantile-pitstops_low_quantile

    lower_bound = pitstops_low_quantile - 1.5*iqr

    pit_stops_df_filtered = pit_stops_df[(pit_stops_df['pit_duration'] > lower_bound)]

    total_stops = len(pit_stops_df)
    valid_stops = len(pit_stops_df_filtered)
    laps_removed = total_stops-valid_stops

    drivers_data = requests.get('https://api.openf1.org/v1/drivers?session_key=' + str(session)).json()
    drivernumber_name_dict = {drivers['driver_number']: drivers['last_name'] for drivers in drivers_data}
    drivernumber_team_dict = {drivers['driver_number']: drivers['team_name'] for drivers in drivers_data}

    pit_stops_df_filtered['name'] = pit_stops_df_filtered['driver_number'].map(drivernumber_name_dict)
    pit_stops_df_filtered['teamName'] = pit_stops_df_filtered['driver_number'].map(drivernumber_team_dict)

    average = pit_stops_df_filtered.groupby(['driver_number', 'name', 'teamName'], as_index=False).agg(
        pitstop_mean = ('pit_duration', 'mean'), 
        pitstop_min = ('pit_duration', 'min')
    )


    average['race'] = [x for x in session_info if x["session_key"]== session][0]['circuit_short_name']

    cols = ['pitstop_mean', 'pitstop_min', 'name']
    average['rank'] = average.sort_values(cols, ascending=True).groupby(cols, sort=False).ngroup() + 1

    average['points'] = average['rank'].map(points).fillna(0)

    average = average.sort_values(by='rank')
    data.append(average)

df = pd.concat(data, ignore_index=True)

print(df.sort_values('race').to_string())

team_results = df.groupby('teamName', as_index=False).agg(
    points = ('points', 'sum')
)

# Testing
team_results.sort_values('points', ascending=False)