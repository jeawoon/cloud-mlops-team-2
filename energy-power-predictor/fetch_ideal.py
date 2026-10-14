"""Download only Home62 mains real power and matching living-room sensors."""
import json
from pathlib import Path
from ideal_remote import archive, download_member

ROOT=Path(__file__).parent
SELECTION={'household':['sensordata/home62_utility711_sensor1786_electric-subcircuit_mains.csv.gz'],
           'room':['sensordata/home62_livingroom706_sensor1669_room_temperature.csv.gz',
                   'sensordata/home62_livingroom706_sensor1668_room_humidity.csv.gz']}


def main():
    out=ROOT/'data/ideal';out.mkdir(parents=True,exist_ok=True)
    entries=[]
    for kind,names in SELECTION.items():
        with archive(kind) as z:
            for name in names:
                print('Downloading',name,round(z.getinfo(name).compress_size/1e6,1),'MB',flush=True)
                item=download_member(z,name,out/Path(name).name)
                entries.append(item)
                print('Verified ZIP CRC',item['file'],flush=True)
    (out/'manifest.json').write_text(json.dumps({'source':'https://doi.org/10.7488/ds/2836','license':'CC-BY-4.0','home':'62','files':entries},indent=2))


if __name__=='__main__':main()
