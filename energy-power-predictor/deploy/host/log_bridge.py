"""Bridge durable SQLite feedback and Docker output to stable CloudWatch input files."""
import json,os,sqlite3,subprocess
from pathlib import Path
STATE=Path('/var/lib/energy-operations/log-offsets.json')
OUT=Path('/var/log/energy-predictor')
DB=Path('/var/lib/docker/volumes/energy-predictor_history/_data/history.sqlite3')

def main():
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
    state=json.loads(STATE.read_text()) if STATE.exists() else {'feedback_row':0,'files':{}}
    with (OUT/'api.jsonl').open('a') as api,(OUT/'web.jsonl').open('a') as web:
        if DB.exists():
            db=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=5)
            if db.execute("SELECT name FROM sqlite_master WHERE name='feedback_events'").fetchone():
                for rowid,encoded in db.execute('SELECT rowid,event_json FROM feedback_events WHERE rowid>? ORDER BY rowid LIMIT 1000',(state['feedback_row'],)):
                    value=json.loads(encoded)
                    api.write(json.dumps(dict(value,record_type='prediction_feedback'),ensure_ascii=False)+'\n')
                    state['feedback_row']=rowid
            db.close()
        ids=subprocess.check_output(['docker','ps','-q','--filter','name=energy-'],text=True).split()
        containers=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True)) if ids else []
        paths=set()
        for c in containers:
            if c['Name'] not in ('/energy-blue-app-1','/energy-green-app-1','/energy-predictor-app-1'):continue
            path=Path(c['LogPath']);paths.add(str(path))
            if not path.is_file():continue
            inode=path.stat().st_ino;previous=state['files'].get(str(path),{})
            offset=previous.get('offset',0) if previous.get('inode')==inode else 0
            if offset>path.stat().st_size:offset=0
            with path.open('rb') as f:
                f.seek(offset)
                for _ in range(2000):
                    line=f.readline()
                    if not line or not line.endswith(b'\n'):break
                    record=json.loads(line)
                    message=record.get('log','').rstrip()
                    output=api if 'energy_api ' in message else web
                    output.write(json.dumps({'record_type':'container_output','container':c['Name'][1:],'time':record.get('time'),'message':message},ensure_ascii=False)+'\n')
                    offset=f.tell()
            state['files'][str(path)]={'inode':inode,'offset':offset}
        state['files']={p:v for p,v in state['files'].items() if p in paths}
        for f in (api,web):f.flush();os.fsync(f.fileno())
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.chmod(0o600);tmp.replace(STATE)

if __name__=='__main__':main()
