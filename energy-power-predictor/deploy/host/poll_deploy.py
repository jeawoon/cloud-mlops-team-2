"""Public main + successful push CI gate. No GitHub key or SSH ingress required."""
import json,os,re,subprocess,tarfile,tempfile,urllib.request
from pathlib import Path
REPO='jeawoon/cloud-mlops-team-2'
API='https://api.github.com/repos/'+REPO
STATE=Path.home()/'.local/state/energy-predictor-deploy/current.json'
RELEASES=Path.home()/'energy-releases'

def get(url):
    req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'energy-predictor-deployer'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)

def eligible(runs,sha):
    selected=[r for r in runs if r.get('head_sha')==sha and r.get('event')=='push' and r.get('head_branch')=='main' and r.get('path')=='.github/workflows/appliance-tests.yml']
    return bool(selected) and max(selected,key=lambda r:r['id']).get('conclusion')=='success' and max(selected,key=lambda r:r['id']).get('status')=='completed'

def extract(archive,dest):
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        if sum(m.size for m in members)>200*1024*1024:raise RuntimeError('Archive too large')
        for m in members:
            parts=Path(m.name).parts[1:]
            if not parts:continue
            if m.name.startswith('/') or '..' in parts or not (m.isdir() or m.isfile()):raise RuntimeError('Unsafe archive member')
            target=dest.joinpath(*parts)
            if m.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(m) as source,target.open('wb') as output:
                    import shutil
                    shutil.copyfileobj(source,output)

def main():
    sha=get(API+'/commits/main')['sha']
    if not re.fullmatch('[0-9a-f]{40}',sha):raise RuntimeError('Invalid commit')
    previous=json.loads(STATE.read_text()) if STATE.exists() else {}
    if previous.get('sha')==sha:print('No new main commit: '+sha);return
    runs=get(API+'/actions/workflows/appliance-tests.yml/runs?event=push&head_sha='+sha+'&per_page=20')['workflow_runs']
    if not eligible(runs,sha):print('Waiting for successful main CI: '+sha);return
    if get(API+'/commits/main')['sha']!=sha:print('Main advanced; retry next poll');return
    RELEASES.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=RELEASES,prefix='verified-') as temp:
        archive=Path(temp)/'source.tar.gz'
        req=urllib.request.Request('https://codeload.github.com/'+REPO+'/tar.gz/'+sha,headers={'User-Agent':'energy-predictor-deployer'})
        with urllib.request.urlopen(req,timeout=60) as response,archive.open('wb') as f:
            total=0
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>150*1024*1024:raise RuntimeError('Download too large')
                f.write(chunk)
        dest=Path(temp)/'source';dest.mkdir();extract(archive,dest)
        env=dict(os.environ,DEPLOY_REVISION=sha)
        subprocess.run(['bash',str(dest/'energy-power-predictor/deploy/deploy-ec2.sh')],env=env,check=True,timeout=1200)
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps({'sha':sha}));tmp.replace(STATE)
    print('Deployed verified main: '+sha)

if __name__=='__main__':main()
