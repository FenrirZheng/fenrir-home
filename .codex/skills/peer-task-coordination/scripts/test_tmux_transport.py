#!/usr/bin/env python3
"""Explicit live test: creates and stops only its own private tmux server."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

helper_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(helper_dir))
import peer_tasks as p

root = Path(tempfile.mkdtemp(prefix='peer-task-live-'))
socket = str(root / 'tmux.sock')
store = root / 'mailbox.sqlite'
fixture = root / 'receiver.py'
fixture.write_text('''import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nimport peer_tasks as p\nroot=Path(sys.argv[2])\nb=p.Mailbox(root/'mailbox.sqlite',create=True)\nr=dict(worker='test-receiver',actor_session='fixture-session',identity=dict(socket=str(root/'tmux.sock'),pane='%0',worktree=str(root),agent_session_id='fixture-session',model='test-fixture-not-an-LLM',identity_evidence='isolated Python test receiver'))\nbinding=b.enroll(r)\n(root/'binding.json').write_text(p.pack(binding))\nfor line in sys.stdin:\n try:\n  task=json.loads(line)\n except ValueError:\n  continue\n r={k:task[k] for k in ('worker','generation','task_id','message_id')}\n r.update(actor_session='fixture-session',accepted=True,evidence='Fixture parsed and accepted exact task envelope')\n receipt=b.acknowledge(r)\n b.report(dict(r,state='running',evidence='Fixture processing received task'))\n (root/'receipt.json').write_text(p.pack(receipt))\n print('RECEIVER_ACK_RECORDED',flush=True)\n''')
started = False
try:
    subprocess.run(['tmux','-S',socket,'-f','/dev/null','new-session','-d','-s','peer-check',
                    '-c',str(root),'python3','-B',str(fixture),str(helper_dir),str(root)],check=True)
    started = True
    for _ in range(50):
        if (root/'binding.json').exists():
            break
        time.sleep(.1)
    binding=json.loads((root/'binding.json').read_text())
    b=p.Mailbox(store)
    req=dict(worker='test-receiver',generation=binding['generation'],task_id='transport-check',message_id='literal-001',
             message='Literal $(touch SHOULD_NOT_EXIST) `false` 中文 "quotes"',acceptance='recipient writes ACK',
             base_revision='fixture:none',owned_paths=[])
    assert b.send_task(req)['delivery']=='queued'
    screen=subprocess.run(['tmux','-S',socket,'capture-pane','-p','-t','%0'],text=True,capture_output=True,check=True).stdout
    assert 'Traceback' not in screen
    result=b.notify(dict(req,ui_ready_evidence='isolated fixture waiting for stdin; no user draft'))
    assert result['delivery']=='queued' and not result['receipt_confirmed']
    for _ in range(50):
        if (root/'receipt.json').exists():
            break
        time.sleep(.1)
    receipt=json.loads((root/'receipt.json').read_text())
    status=b.get_status(req)
    assert receipt['receipt']['message_id']=='literal-001'
    assert status['delivery']=='acknowledged' and status['state']=='running',status
    assert not (root/'SHOULD_NOT_EXIST').exists()
    events=b.read_updates(req)
    assert [e['type'] for e in events['new_events']]==['enrolled','queued','notification_attempt','acknowledged','status']
    b.db.close()
    report=dict(result='pass',kind='real tmux transport with Python receiver fixture; not LLM acceptance',
                root=str(root),receipt=receipt,status=status,events=len(events['new_events']))
    (root / 'result.json').write_text(p.pack(report))
    print(p.pack(report))
finally:
    if started:
        subprocess.run(['tmux','-S',socket,'kill-server'],check=True)
