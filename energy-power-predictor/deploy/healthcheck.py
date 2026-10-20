"""Return nonzero if API model load or UI health fails."""
import json
from urllib.request import urlopen

with urlopen('http://127.0.0.1:8000/api/health',timeout=5) as r:
    assert json.load(r)['status']=='ok'
with urlopen('http://127.0.0.1:8501/_stcore/health',timeout=5) as r:
    assert r.status==200
