#!/usr/bin/env python3
"""Behavioral checks; isolated stores, no real terminal writes."""
import copy
import concurrent.futures
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import peer_tasks as pt


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.sqlite'
        self.obs = patch.object(pt, 'observe', side_effect=lambda i: {
            'socket': '/tmp/test-socket', 'server_pid': '10', 'server_started': '20',
            'session': '$0', 'pane': i['pane'], 'pane_pid': '30', 'command': 'codex',
            'worktree': self.temp.name})
        self.obs.start()
        self.box = pt.Mailbox(self.path)
        self.enroll = dict(worker='a', actor_session='runtime-a', identity=dict(
            socket='/tmp/test-socket', pane='%1', worktree=self.temp.name,
            agent_session_id='runtime-a', model='observed-model', identity_evidence='receiver handshake'))
        self.binding = self.box.enroll(self.enroll)
        self.req = dict(worker='a', generation=self.binding['generation'], task_id='task-a', message_id='m-a',
                        message='Do bounded work: $(false) `false` 雙引號 "', acceptance='artifact reviewed',
                        base_revision='sha:abc;dirty:123', owned_paths=[self.temp.name + '/work'])
        self.actor = {k: self.req[k] for k in ('worker', 'generation', 'task_id', 'message_id')}
        self.actor.update(actor_session='runtime-a', accepted=True, evidence='I read and accept m-a')

    def tearDown(self):
        self.box.db.close()
        self.obs.stop()
        self.temp.cleanup()

    def accepted(self):
        self.box.send_task(self.req)
        return self.box.acknowledge(self.actor)

    def done_request(self):
        return dict(self.actor, state='done', handoff=dict(revision=1, source_sha=None,
                    source_note='uncommitted fixture', dirty_digest='snapshot:123', tests=[dict(
                    command='check', result='pass', tested_revision='snapshot:123', updated_at=pt.stamp())],
                    unresolved=[], artifacts=[dict(path=self.temp.name + '/result', sha256='abc')], updated_at=pt.stamp()))

    def test_queue_and_transport_do_not_acknowledge(self):
        self.box.send_task(self.req)
        calls = []
        with patch.object(pt, 'tmux', side_effect=lambda *a, **kw: calls.append((a, kw)) or ''), patch.object(pt.time, 'sleep'):
            result = self.box.notify(dict(self.actor, ui_ready_evidence='main input empty'))
        self.assertEqual(result['delivery'], 'queued')
        self.assertFalse(result['receipt_confirmed'])
        self.assertEqual(self.box.get_status(self.actor)['state'], 'unknown')
        self.assertEqual(self.box.get_status(self.actor)['delivery'], 'queued')
        pasted = next(kw['data'] for a, kw in calls if a[1] == 'load-buffer')
        self.assertIn('$(false)', pasted)
        self.assertIn('雙引號', pasted)
        self.assertEqual([a[1] for a, kw in calls], ['load-buffer', 'paste-buffer', 'send-keys', 'delete-buffer'])

    def test_ack_requires_recipient_session_task_and_explicit_acceptance(self):
        self.box.send_task(self.req)
        for change in ({'actor_session': 'sender'}, {'task_id': 'wrong'}, {'generation': 'old'}, {'accepted': False}):
            with self.assertRaises(ValueError):
                self.box.acknowledge(dict(self.actor, **change))
        self.assertEqual(self.box.get_status(self.actor)['delivery'], 'queued')
        self.assertEqual(self.box.acknowledge(self.actor)['delivery'], 'acknowledged')
        self.assertEqual(self.box.get_status(self.actor)['state'], 'unknown')
        self.box.report(dict(self.actor, state='running'))
        self.assertEqual(self.box.get_status(self.actor)['state'], 'running')

    def test_duplicate_is_immutable_and_single_ack_event(self):
        self.accepted()
        self.assertTrue(self.box.send_task(self.req)['duplicate'])
        self.assertTrue(self.box.acknowledge(self.actor)['duplicate'])
        with self.assertRaises(ValueError):
            self.box.send_task(dict(self.req, message='different'))
        kinds = [e['type'] for e in self.box.read_updates(self.actor)['new_events']]
        self.assertEqual(kinds.count('queued'), 1)
        self.assertEqual(kinds.count('acknowledged'), 1)

    def test_identity_change_and_socket_failure_are_unknown(self):
        self.accepted()
        self.box.report(dict(self.actor, state='running'))
        with patch.object(pt, 'observe', side_effect=OSError('socket inaccessible')):
            self.assertEqual(self.box.get_status(self.actor)['state'], 'unknown')
            with self.assertRaises(OSError):
                self.box.send_task(self.req)
        with patch.object(pt, 'observe', return_value=dict(self.binding['identity'], pane_pid='99')):
            self.assertEqual(self.box.get_status(self.actor)['state'], 'unknown')
            with self.assertRaises(ValueError):
                self.box.acknowledge(self.actor)

    def test_all_task_states_expire_without_erasing_historical_report(self):
        self.accepted()
        for state in ('running', 'waiting_approval', 'blocked', 'unknown'):
            self.box.report(dict(self.actor, state=state))
            with patch.object(pt.time, 'time', return_value=time.time() + 301):
                status = self.box.get_status(self.actor)
            self.assertEqual(status['state'], 'unknown')
            self.assertEqual(status['reported_state'], state)
        self.box.report(self.done_request())
        with patch.object(pt.time, 'time', return_value=time.time() + 301):
            self.assertEqual(self.box.get_status(self.actor)['state'], 'unknown')
        self.assertEqual(self.box.get_status(self.actor)['reported_state'], 'done')

    def test_cursor_pagination_reset_and_no_repeated_history(self):
        self.accepted()
        first = self.box.read_updates(dict(self.actor, limit=1))
        self.assertTrue(first['has_more'])
        second = self.box.read_updates(dict(self.actor, cursor=first['next_cursor']))
        self.assertEqual([e['type'] for e in second['new_events']], ['queued', 'acknowledged'])
        third = self.box.read_updates(dict(self.actor, cursor=second['next_cursor']))
        self.assertEqual(third['new_events'], [])
        for cursor in ('other:epoch:1', second['next_cursor'].rsplit(':', 1)[0] + ':9999'):
            reset = self.box.read_updates(dict(self.actor, cursor=cursor))
            self.assertTrue(reset['reset'])
            self.assertTrue(reset['truncated'])
            self.assertEqual(len(reset['new_events']), 3)

    def test_fresh_enrollment_invalidates_same_tuple_cursor(self):
        old = self.box.read_updates(self.actor)['next_cursor']
        new = self.box.enroll(self.enroll)
        self.assertNotEqual(new['generation'], self.binding['generation'])
        self.assertTrue(self.box.read_updates(dict(worker='a', cursor=old))['reset'])
        with self.assertRaises(ValueError):
            self.box.send_task(self.req)

    def test_store_recreation_has_new_epoch(self):
        old_epoch = self.box.epoch
        other = pt.Mailbox(Path(self.temp.name) / 'other.sqlite')
        try:
            self.assertNotEqual(old_epoch, other.epoch)
        finally:
            other.db.close()

    def test_claims_include_parent_child_and_survive_blocked(self):
        self.accepted()
        self.box.report(dict(self.actor, state='blocked'))
        other = copy.deepcopy(self.enroll)
        other.update(worker='b', actor_session='runtime-b')
        other['identity'].update(agent_session_id='runtime-b', pane='%2')
        gen = self.box.enroll(other)['generation']
        request = dict(self.req, worker='b', generation=gen, message_id='m-b', task_id='task-b',
                       owned_paths=[self.temp.name + '/work/child'])
        with self.assertRaisesRegex(ValueError, 'ownership conflict'):
            self.box.send_task(request)
        with self.assertRaisesRegex(ValueError, 'unresolved task'):
            self.box.enroll(self.enroll)
        self.box.report(self.done_request())
        self.assertEqual(self.box.send_task(request)['delivery'], 'queued')

    def test_handoff_requires_versioned_evidence_and_cannot_overwrite_new_task(self):
        self.accepted()
        bad = self.done_request()
        del bad['handoff']['dirty_digest']
        with self.assertRaises(ValueError):
            self.box.report(bad)
        good = self.done_request()
        self.box.report(good)
        with self.assertRaises(ValueError):
            self.box.report(good)
        newer = copy.deepcopy(good)
        newer['handoff']['revision'] = 2
        self.box.report(newer)
        self.box.send_task(dict(self.req, message_id='m-next', task_id='task-next'))
        newer['handoff']['revision'] = 3
        with self.assertRaisesRegex(ValueError, 'newer task'):
            self.box.report(newer)
        history = [e['handoff']['revision'] for e in self.box.read_updates(self.actor)['new_events'] if 'handoff' in e]
        self.assertEqual(history, [1, 2])

    def test_failed_submit_requires_inspection_and_bounded_retry(self):
        self.box.send_task(self.req)
        r = dict(self.actor, ui_ready_evidence='empty main input')
        with patch.object(pt, 'tmux', side_effect=subprocess.CalledProcessError(1, ['tmux'])):
            with self.assertRaises(subprocess.CalledProcessError):
                self.box.notify(r)
        self.assertEqual(self.box.get_status(self.actor)['notification_attempts'], 1)
        with self.assertRaisesRegex(ValueError, 'inspect status'):
            self.box.notify(r)
        with patch.object(pt, 'tmux', return_value=''), patch.object(pt.time, 'sleep'):
            self.box.notify(dict(r, retry=True, recovery_evidence='checked events and UI; first paste absent'))
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            self.box.notify(dict(r, retry=True, recovery_evidence='inspection'))
        self.box.acknowledge(self.actor)
        self.assertFalse(self.box.notify(r)['notified'])

    def test_concurrent_duplicate_sends_have_one_queue_record(self):
        def send(_):
            b = pt.Mailbox(self.path)
            try:
                return b.send_task(self.req)
            finally:
                b.db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(send, range(4)))
        self.assertEqual(sum(not r['duplicate'] for r in results), 1)
        self.assertEqual(sum(e['type'] == 'queued' for e in self.box.read_updates(self.actor)['new_events']), 1)

    def test_restart_reconciliation_requires_evidence_and_fresh_enrollment(self):
        self.accepted()
        with patch.object(pt, 'observe', side_effect=OSError('old runtime gone')):
            with self.assertRaises(ValueError):
                self.box.reconcile(self.actor)
            result = self.box.reconcile(dict(self.actor, workers_stopped_evidence='old writers exited',
                                            artifact_review_evidence='partial changes reviewed and preserved'))
        self.assertTrue(result['requires_handshake'])
        with self.assertRaisesRegex(ValueError, 'fresh receiver enrollment'):
            self.box.send_task(dict(self.req, task_id='new-task', message_id='new-message'))
        fresh = self.box.enroll(self.enroll)
        self.assertNotEqual(fresh['generation'], self.binding['generation'])
        self.assertEqual(self.box.send_task(dict(self.req, generation=fresh['generation'],
                         task_id='new-task', message_id='new-message'))['delivery'], 'queued')


if __name__ == '__main__':
    unittest.main(verbosity=2)
