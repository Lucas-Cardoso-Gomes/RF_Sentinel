import requests

def fetch_tle(satellite='ISS'):
    url = f'https://celestrak.com/NORAD/elements/stations.txt'
    r = requests.get(url)
    lines = r.text.strip().split('\n')
    for i in range(0, len(lines), 3):
        if satellite.upper() in lines[i].upper():
            return lines[i:i+3]
    return []
