import fastf1
from fastf1 import _api as f1_api
from fastf1.mvapi.api import get_circuit
import numpy as np
import pandas as pd
import svgwrite
from svgwrite.base import Title
import io
import os 
import re
import unicodedata 

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

def load_track_outline(session):
    """Return (x, y, rotation) for the circuit without a full session load.

    Session.load(telemetry=True) parses car and position data for every
    driver just to draw one lap, peaking at several hundred MiB. MultiViewer
    (FastF1's own circuit info source) already ships a track outline, so use
    that; otherwise stream the position feed keeping only the fastest lap.
    """
    circuit_info = f1_api.session_info(session.api_path)['Meeting']['Circuit']
    circuit_key = circuit_info['Key']
    # FastF1 applies the same correction in Session.get_circuit_info().
    if circuit_key == 149 and circuit_info['ShortName'] == 'Mugello':
        circuit_key = 146

    circuit = get_circuit(year=session.event.year, circuit_key=circuit_key) or {}
    if circuit.get('x') and circuit.get('y'):
        x, y = np.asarray(circuit['x'], float), np.asarray(circuit['y'], float)
        return np.append(x, x[0]), np.append(y, y[0]), float(circuit.get('rotation', 0.0))

    return (*fastest_lap_positions(session), float(circuit.get('rotation', 0.0)))


def fastest_lap_positions(session):
    """Decode only the fastest lap's samples from the raw position stream."""
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    lap = session.laps.pick_fastest()
    driver = str(lap['DriverNumber'])
    start, end = lap['LapStartTime'], lap['Time']

    x, y = [], []
    for record in f1_api.fetch_page(session.api_path, 'position') or []:
        # Stream timestamps are session-relative, like LapStartTime.
        if not start <= pd.to_timedelta(record[:12]) <= end:
            continue
        for sample in f1_api.parse(record[12:], zipped=True)['Position']:
            entry = sample['Entries'].get(driver)
            if entry and entry.get('Status') == 'OnTrack':
                x.append(entry['X'])
                y.append(entry['Y'])

    if len(x) < 2:
        raise ValueError("No position data for the fastest lap")
    return np.append(x, x[0]), np.append(y, y[0])


def generate_track_map_svg(year: int, city: str = None, country: str = None, track: str = None, session_type: str = "Q", race_name: str = None) -> str:
    track_color = os.environ['TRACK_COLOUR'].strip()

    match = re.search(r'^#(?:[0-9a-fA-F]{3}){1,2}$', track_color)

    if not match:
        raise ValueError("Not a valid hex string")

    # Load data from f1 API
    if race_name:
        gp = race_name
        print(gp)
    elif city and country:
        gp = city + " " + country
    else:
        raise ValueError("Must provide either race name or city + country")
    session = fastf1.get_session(year, gp, session_type)

    # FastF1 and F1API.dev have different country names for UK.
    #if (gp == "Silverstone Great Britain"):
    #    gp = "Silverstone United Kingdom"

    if not race_name: 
        if (city != remove_accents(session.event.Location)) or (country != remove_accents(session.event.Country)):
            raise ValueError("Map not matching correctly")

    x, y, rotation = load_track_outline(session)
    # api position data defaults to top is 'north.' This isn't how most maps "look" though,
    # so they also include a rotation parameter to match standard images
    angle = (rotation / 180) * np.pi
    rot_mat = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
    rotated = np.dot(np.column_stack([x, y]), rot_mat)

    x = rotated[:, 0]
    # Apply a vertical flip since it seems the angle is usually a vertical flip off.
    y = -rotated[:, 1]

    # Calculate bounding box
    min_x, max_x = np.min(x), np.max(x)
    min_y, max_y = np.min(y), np.max(y)
    width = max_x - min_x
    height = max_y - min_y

    # Give a 1% margin cause was clipping
    pad_x = width * 0.01
    pad_y = height * 0.01

    # Translate track so it's centered in the viewbox
    viewbox_width = width + 2 * pad_x
    viewbox_height = height + 2 * pad_y
    x_shift = -min_x + pad_x
    y_shift = -min_y + pad_y
    x = x + x_shift
    y = y + y_shift

    points = list(zip(x, y))

    svg_buf = io.StringIO()

    # Match column: small in glance, but probably shouldnt if wanna use in main
    display_width = 300

    # Have to sort out aspect ratio since will differ for every track. 
    aspect_ratio = viewbox_height/viewbox_width
    display_height = int(display_width * aspect_ratio)
    dwg = svgwrite.Drawing(svg_buf, profile='full',
                           size=(f"{display_width}px", f"{display_height}px"),
                           viewBox=f"0 0 {viewbox_width} {viewbox_height}",
                           preserveAspectRatio="xMidYMid meet")

    track_class = 'track-line'
    # Have to have a super thick line
    dwg.defs.add(dwg.style(f"""
        .{track_class} {{
            fill: transparent;
            stroke: {track_color};
            stroke-width: 40;
            title: {track};
            filter: drop-shadow(0 0 40px white), drop-shadow(0 0 70px {track_color});
        }}"""))

    polyline = dwg.polyline(points=points, class_=track_class, fill='none')
    polyline.elements.append(Title(track))
    dwg.add(polyline)
    dwg.write(svg_buf)

    return svg_buf.getvalue()
