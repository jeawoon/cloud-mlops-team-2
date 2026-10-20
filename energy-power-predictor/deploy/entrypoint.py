"""Supervise local API and UI; stop both if either exits. No shell execution."""
import os
import signal
import subprocess
import sys
import time

children=[]


def stop(*_):
    for child in children:
        if child.poll() is None:child.terminate()
    for child in children:
        try:child.wait(timeout=10)
        except subprocess.TimeoutExpired:child.kill();child.wait()


def main():
    token=os.environ.get('PREDICTION_API_TOKEN','')
    if len(token)<32 or 'replace' in token.lower():
        raise SystemExit('배포 환경에서 32자 이상의 무작위 PREDICTION_API_TOKEN을 설정하세요.')
    os.umask(0o077)
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    signal.signal(signal.SIGINT,lambda *_:sys.exit(0))
    try:
        children.append(subprocess.Popen([sys.executable,'api.py','--host','127.0.0.1','--port','8000']))
        children.append(subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.address','0.0.0.0','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false']))
        while all(c.poll() is None for c in children):time.sleep(.5)
        raise SystemExit('API 또는 UI가 종료되어 두 프로세스를 정리합니다.')
    finally:stop()


if __name__=='__main__':main()
