"""Export latest labeled events for human review, never train automatically."""
import json,os,sqlite3
from pathlib import Path
path=Path(os.environ.get('ENERGY_HISTORY_DB','runtime-data/history.sqlite3'))
db=sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)
# Last row wins: corrections replace earlier labels; tombstones exclude deleted records.
for (encoded,) in db.execute('SELECT event_json FROM feedback_events WHERE rowid IN (SELECT MAX(rowid) FROM feedback_events GROUP BY prediction_id)'):
    value=json.loads(encoded)
    if value.get('status')=='evaluated':print(json.dumps(value,ensure_ascii=False,allow_nan=False))
