import importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path

def load(name):
    p=Path(__file__).parent/'deploy/host'/name
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class HostOperationTests(unittest.TestCase):
    def test_gate_only_successful_current_main_push(self):
        m=load('poll_deploy.py');r=dict(id=1,head_sha='a'*40,event='push',head_branch='main',path='.github/workflows/appliance-tests.yml',status='completed',conclusion='success')
        self.assertTrue(m.eligible([r],'a'*40))
        for patch in ({'event':'pull_request'},{'head_branch':'feature'},{'conclusion':'failure'},{'status':'in_progress'},{'head_sha':'b'*40}):
            self.assertFalse(m.eligible([dict(r,**patch)],'a'*40))
        self.assertFalse(m.eligible([r,dict(r,id=2,conclusion='failure')],'a'*40))
    def test_reject_archive_traversal_and_symlink(self):
        m=load('poll_deploy.py')
        for name,kind in [('root/../../outside',tarfile.REGTYPE),('root/link',tarfile.SYMTYPE)]:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);archive=p/'source.tar.gz';out=p/'out';out.mkdir()
                with tarfile.open(archive,'w:gz') as t:
                    item=tarfile.TarInfo(name);item.type=kind;item.linkname='/etc/passwd';t.addfile(item)
                with self.assertRaises(RuntimeError):m.extract(archive,out)
    def test_extract_regular_file(self):
        m=load('poll_deploy.py')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);archive=p/'a.tar.gz';out=p/'out';out.mkdir()
            with tarfile.open(archive,'w:gz') as t:
                item=tarfile.TarInfo('root/README.md');item.size=2;t.addfile(item,io.BytesIO(b'ok'))
            m.extract(archive,out);self.assertEqual((out/'README.md').read_text(),'ok')
    def test_feedback_bridge_checkpoint(self):
        import sqlite3
        from unittest.mock import patch
        m=load('log_bridge.py')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);m.STATE=p/'state/checkpoint.json';m.OUT=p/'out';m.DB=p/'source.sqlite3'
            db=sqlite3.connect(m.DB);db.execute('CREATE TABLE feedback_events(event_json TEXT)');db.execute('INSERT INTO feedback_events VALUES (?)',(json.dumps({'event_id':'test-event','training_eligible':False}),));db.commit();db.close()
            with patch.object(m.subprocess,'check_output',return_value=''):
                m.main();m.main()
            lines=(m.OUT/'api.jsonl').read_text().splitlines()
            self.assertEqual(len(lines),1);self.assertEqual(json.loads(lines[0])['event_id'],'test-event')
            self.assertEqual(json.loads(m.STATE.read_text())['feedback_row'],1)
