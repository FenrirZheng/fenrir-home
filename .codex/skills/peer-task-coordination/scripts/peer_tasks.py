#!/usr/bin/env python3
"""Cooperative local peer-task/v1 mailbox. Linux, Python 3 and tmux; no daemon."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

STATES = {'idle', 'running', 'waiting_approval', 'blocked', 'done', 'unknown'}
FIELDS = ('socket', 'server_pid', 'server_started', 'session', 'pane', 'pane_pid', 'command', 'worktree')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def need(value, message):
    if not value:
        raise ValueError(message)


def tmux(socket, *args, data=None):
    return subprocess.run(['tmux', '-S', socket, *args], input=data, text=True,
                          capture_output=True, check=True, timeout=10).stdout


def observe(identity):
    need(os.path.isabs(identity['socket']), 'socket must be absolute')
    need(re.fullmatch(r'%[0-9]+', identity['pane']), 'use an exact %N pane')
    fields = ('socket_path', 'pid', 'start_time', 'session_id', 'pane_id',
              'pane_pid', 'pane_current_command', 'pane_current_path')
    values = tmux(identity['socket'], 'display-message', '-p', '-t', identity['pane'],
                  '\t'.join('#{' + f + '}' for f in fields)).rstrip('\n').split('\t')
    need(len(values) == len(fields) and all(values), 'incomplete tmux identity')
    result = dict(zip(FIELDS, values))
    need(result['pane'] == identity['pane'], 'tmux resolved another pane')
    result['worktree'] = str(Path(result['worktree']).resolve())
    return result


class Mailbox:
    def __init__(self, path):
        path = Path(path).expanduser().resolve()
        self.path = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS workers
          (worker TEXT PRIMARY KEY, generation TEXT NOT NULL, identity TEXT NOT NULL,
           state TEXT NOT NULL, evidence TEXT NOT NULL, updated REAL NOT NULL,
           task_id TEXT, message_id TEXT);
        CREATE TABLE IF NOT EXISTS messages
          (message_id TEXT PRIMARY KEY, worker TEXT NOT NULL, generation TEXT NOT NULL,
           task_id TEXT NOT NULL, payload TEXT NOT NULL, ack TEXT,
           terminal INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events
          (seq INTEGER PRIMARY KEY AUTOINCREMENT, worker TEXT NOT NULL,
           generation TEXT NOT NULL, body TEXT NOT NULL);
        ''')
        self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('epoch', uuid.uuid4().hex))
        self.epoch = self.db.execute('SELECT value FROM meta WHERE key=?', ('epoch',)).fetchone()[0]

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def worker(self, name):
        row = self.db.execute('SELECT * FROM workers WHERE worker=?', (name,)).fetchone()
        need(row is not None, 'worker is not enrolled')
        return dict(row)

    def event(self, w, kind, body):
        record = dict(protocol='peer-task/v1', type=kind, worker=w['worker'],
                      generation=w['generation'], updated_at=stamp(), **body)
        self.db.execute('INSERT INTO events(worker,generation,body) VALUES (?,?,?)',
                        (w['worker'], w['generation'], pack(record)))

    def verified(self, r, receiver=False):
        w = self.worker(r['worker'])
        need(r['generation'] == w['generation'], 'generation changed; handshake again')
        identity = json.loads(w['identity'])
        need(not identity.get('reconciled'), 'task reconciled; fresh receiver enrollment required')
        actual = observe(identity)
        need(all(actual[k] == identity[k] for k in FIELDS), 'tmux identity changed')
        if receiver:
            need(r.get('actor_session') == identity['agent_session_id'], 'receiver session mismatch')
        return w

    def message(self, r, w):
        row = self.db.execute('SELECT * FROM messages WHERE message_id=?', (r['message_id'],)).fetchone()
        need(row is not None, 'unknown message')
        m = dict(row)
        need((m['worker'], m['generation'], m['task_id']) ==
             (w['worker'], w['generation'], r['task_id']), 'message/task/identity mismatch')
        return m

    def enroll(self, r):
        identity = dict(r['identity'])
        for k in ('agent_session_id', 'model', 'identity_evidence'):
            need(isinstance(identity.get(k), str) and identity[k].strip(), k + ' is required')
        need(r.get('actor_session') == identity['agent_session_id'], 'receiver must self-enroll')
        actual = observe(identity)
        need(str(Path(identity['worktree']).resolve()) == actual['worktree'], 'worktree mismatch')
        identity.update(actual)
        with self.transaction():
            need(not self.db.execute('SELECT 1 FROM messages WHERE worker=? AND terminal=0',
                                     (r['worker'],)).fetchone(), 'unresolved task; reconcile before reenrollment')
            generation = uuid.uuid4().hex
            self.db.execute('INSERT OR REPLACE INTO workers VALUES (?,?,?,?,?,?,NULL,NULL)',
                            (r['worker'], generation, pack(identity), 'idle',
                             'receiver enrollment: ' + identity['identity_evidence'], time.time()))
            self.event(self.worker(r['worker']), 'enrolled', {'identity': identity})
        return dict(worker=r['worker'], generation=generation, identity=identity)

    def send_task(self, r):
        keys = ('task_id', 'message_id', 'message', 'acceptance', 'base_revision')
        for k in keys:
            need(isinstance(r.get(k), str) and r[k].strip(), k + ' is required')
        owned = r.get('owned_paths')
        need(isinstance(owned, list), 'owned_paths must be a list; [] for read-only')
        need(all(isinstance(p, str) and os.path.isabs(p) for p in owned), 'owned_paths must be absolute')
        payload = {k: r[k] for k in keys}
        payload['owned_paths'] = sorted({str(Path(p).resolve()) for p in owned})
        with self.transaction():
            w = self.verified(r)
            payload.update(worker=w['worker'], generation=w['generation'],
                           worktree=json.loads(w['identity'])['worktree'])
            old = self.db.execute('SELECT * FROM messages WHERE message_id=?', (r['message_id'],)).fetchone()
            if old:
                need(old['payload'] == pack(payload), 'message_id reused with different payload')
                return dict(delivery='acknowledged' if old['ack'] else 'queued', duplicate=True, message_id=r['message_id'])
            need(not self.db.execute('SELECT 1 FROM messages WHERE worker=? AND terminal=0',
                                     (w['worker'],)).fetchone(), 'worker already has unresolved work')
            for row in self.db.execute('SELECT payload FROM messages WHERE terminal=0'):
                other = json.loads(row['payload'])
                for a in payload['owned_paths']:
                    for b in other['owned_paths']:
                        need(not (Path(a) == Path(b) or Path(a) in Path(b).parents or Path(b) in Path(a).parents),
                             'ownership conflict with ' + other['message_id'] + ': ' + a)
            self.db.execute('INSERT INTO messages(message_id,worker,generation,task_id,payload) VALUES (?,?,?,?,?)',
                            (r['message_id'], w['worker'], w['generation'], r['task_id'], pack(payload)))
            self.db.execute('UPDATE workers SET state=?,evidence=?,updated=?,task_id=?,message_id=? WHERE worker=?',
                            ('unknown', 'queued; no receiver acceptance', time.time(), r['task_id'], r['message_id'], w['worker']))
            self.event(w, 'queued', dict(task_id=r['task_id'], message_id=r['message_id'], payload=payload))
        return dict(delivery='queued', duplicate=False, message_id=r['message_id'])

    def acknowledge(self, r):
        need(r.get('evidence'), 'explicit receiver acceptance evidence required')
        need(r.get('accepted') is True, 'only explicit accepted=true creates an ACK')
        with self.transaction():
            w = self.verified(r, receiver=True)
            m = self.message(r, w)
            if m['ack']:
                return dict(delivery='acknowledged', duplicate=True, receipt=json.loads(m['ack']))
            receipt = {k: r[k] for k in ('worker', 'generation', 'task_id', 'message_id', 'actor_session', 'evidence', 'accepted')}
            receipt['updated_at'] = stamp()
            self.db.execute('UPDATE messages SET ack=? WHERE message_id=?', (pack(receipt), r['message_id']))
            self.db.execute('UPDATE workers SET evidence=?,updated=? WHERE worker=?',
                            ('accepted; execution not yet reported: ' + r['evidence'], time.time(), w['worker']))
            self.event(w, 'acknowledged', dict(receipt=receipt, task_id=m['task_id'], message_id=m['message_id']))
        return dict(delivery='acknowledged', duplicate=False, receipt=receipt)

    def report(self, r):
        need(r.get('state') in STATES and r.get('evidence'), 'valid state and evidence required')
        with self.transaction():
            w = self.verified(r, receiver=True)
            m = self.message(r, w)
            need(m['ack'], 'acknowledge before reporting work')
            need(w['message_id'] == m['message_id'], 'cannot overwrite newer task state')
            need(not m['terminal'] or r['state'] == 'done', 'terminal task cannot resume')
            need(r['state'] != 'idle', 'unfinished task cannot be released as idle')
            body = dict(task_id=m['task_id'], message_id=m['message_id'], state=r['state'], evidence=r['evidence'])
            if r['state'] == 'done':
                h = r.get('handoff', {})
                for k in ('revision', 'source_sha', 'source_note', 'dirty_digest', 'tests', 'unresolved', 'artifacts', 'updated_at'):
                    need(k in h, 'handoff.' + k + ' is required')
                need(type(h['revision']) is int and h['revision'] > 0, 'handoff revision must be positive integer')
                need(h['source_sha'] or h['source_note'], 'explain unavailable source SHA')
                need(isinstance(h['dirty_digest'], str) and h['dirty_digest'], 'snapshot digest required')
                for k in ('tests', 'unresolved', 'artifacts'):
                    need(isinstance(h[k], list), 'handoff.' + k + ' must be a list')
                for t in h['tests']:
                    need(all(t.get(k) for k in ('command', 'result', 'tested_revision', 'updated_at')), 'incomplete test evidence')
                for a in h['artifacts']:
                    need(os.path.isabs(a.get('path', '')) and a.get('sha256'), 'artifact path/digest required')
                for row in self.db.execute('SELECT body FROM events WHERE worker=? AND generation=? ORDER BY seq DESC',
                                           (w['worker'], w['generation'])):
                    old = json.loads(row['body'])
                    if old.get('message_id') == m['message_id'] and old.get('handoff'):
                        need(h['revision'] > old['handoff']['revision'], 'handoff revision must increase')
                        break
                body['handoff'] = h
                self.db.execute('UPDATE messages SET terminal=1 WHERE message_id=?', (m['message_id'],))
            self.db.execute('UPDATE workers SET state=?,evidence=?,updated=? WHERE worker=?',
                            (r['state'], r['evidence'], time.time(), w['worker']))
            self.event(w, 'status', body)
        return body

    def get_status(self, r):
        w = self.worker(r['worker'])
        state, evidence = w['state'], w['evidence']
        source = 'receiver_ledger' if state != 'unknown' else 'task_ledger'
        observed_at = datetime.fromtimestamp(w['updated'], timezone.utc).isoformat()
        ttl = r.get('max_age_seconds', 300)
        need(isinstance(ttl, (int, float)) and ttl > 0, 'max_age_seconds must be positive')
        try:
            self.verified(dict(worker=w['worker'], generation=r.get('generation', w['generation'])))
        except (ValueError, OSError, subprocess.SubprocessError) as e:
            state, evidence = 'unknown', str(e)
            source, observed_at = 'identity_check', stamp()
        else:
            age = time.time() - w['updated']
            if age < 0 or age > ttl:
                state, evidence = 'unknown', 'status expired or clock moved backwards'
                source, observed_at = 'freshness_check', stamp()
        m = self.db.execute('SELECT ack,attempts FROM messages WHERE message_id=?', (w['message_id'],)).fetchone()
        return dict(worker=w['worker'], generation=w['generation'], state=state,
                    evidence=[dict(source=source, value=evidence, observed_at=observed_at)],
                    reported_state=w['state'], last_update=datetime.fromtimestamp(w['updated'], timezone.utc).isoformat(),
                    task_id=w['task_id'], message_id=w['message_id'],
                    delivery=('acknowledged' if m['ack'] else 'queued') if m else None,
                    notification_attempts=m['attempts'] if m else 0)

    def reconcile(self, r):
        """Coordinator records manual recovery; never pretends an old task succeeded."""
        for k in ('workers_stopped_evidence', 'artifact_review_evidence'):
            need(isinstance(r.get(k), str) and r[k].strip(), k + ' required before releasing claims')
        with self.transaction():
            w = self.worker(r['worker'])
            need(r['generation'] == w['generation'], 'reconcile the recorded generation')
            m = self.message(r, w)
            need(not m['terminal'], 'task already resolved')
            need(w['message_id'] == m['message_id'], 'cannot reconcile a newer task')
            self.db.execute('UPDATE messages SET terminal=1 WHERE message_id=?', (m['message_id'],))
            self.db.execute('UPDATE workers SET state=?,evidence=?,updated=? WHERE worker=?',
                            ('unknown', 'coordinator reconciled task; new receiver handshake required', time.time(), w['worker']))
            # Invalidate dispatch until fresh receiver enrollment, while keeping old events readable.
            identity = json.loads(w['identity'])
            identity['reconciled'] = True
            self.db.execute('UPDATE workers SET identity=? WHERE worker=?', (pack(identity), w['worker']))
            self.event(w, 'reconciled', {k: r[k] for k in ('task_id', 'message_id', 'workers_stopped_evidence', 'artifact_review_evidence')})
        return dict(resolved=True, state='unknown', requires_handshake=True)

    def read_updates(self, r):
        with self.transaction():
            w = self.worker(r['worker'])
            prefix = self.epoch + ':' + w['generation'] + ':'
            cursor = r.get('cursor')
            reset = bool(cursor and (not isinstance(cursor, str) or not cursor.startswith(prefix)))
            since = 0
            if cursor and not reset:
                try:
                    since = int(cursor[len(prefix):])
                    need(since >= 0, 'negative cursor')
                except ValueError:
                    reset, since = True, 0
            maximum = self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE worker=? AND generation=?',
                                      (w['worker'], w['generation'])).fetchone()[0]
            if since > maximum:
                reset, since = True, 0
            limit = r.get('limit', 100)
            need(type(limit) is int and 1 <= limit <= 1000, 'limit must be 1..1000')
            rows = self.db.execute('SELECT seq,body FROM events WHERE worker=? AND generation=? AND seq>? ORDER BY seq LIMIT ?',
                                   (w['worker'], w['generation'], since, limit + 1)).fetchall()
            events = [dict(json.loads(row['body']), seq=row['seq']) for row in rows[:limit]]
            next_seq = events[-1]['seq'] if events else since
        return dict(new_events=events, next_cursor=prefix + str(next_seq), reset=reset,
                    truncated=reset, has_more=len(rows) > limit)

    def notify(self, r):
        need(r.get('ui_ready_evidence'), 'inspect UI/drafts/conversation and record ui_ready_evidence')
        # Write attempt BEFORE keys: a crash cannot silently enable automatic resend.
        with self.transaction():
            w = self.verified(r)
            m = self.message(r, w)
            if m['ack']:
                return dict(delivery='acknowledged', notified=False)
            need(not m['terminal'], 'task already terminal')
            need(m['attempts'] < 2, 'retry budget exhausted; reconcile manually')
            if m['attempts']:
                need(r.get('retry') is True and r.get('recovery_evidence'), 'inspect status/UI/ACK before explicit retry')
                self.get_status(r)
            self.db.execute('UPDATE messages SET attempts=attempts+1 WHERE message_id=?', (m['message_id'],))
            self.event(w, 'notification_attempt', dict(task_id=m['task_id'], message_id=m['message_id'],
                       ui_ready_evidence=r['ui_ready_evidence'], recovery_evidence=r.get('recovery_evidence')))
        identity = json.loads(w['identity'])
        key = hashlib.sha256((identity['socket'] + ':' + identity['pane']).encode()).hexdigest()
        lockdir = Path(tempfile.gettempdir()) / ('peer-task-locks-' + str(os.getuid()))
        lockdir.mkdir(mode=0o700, exist_ok=True)
        with (lockdir / key).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.verified(r)
            # ACK may arrive while acquiring the transport lock.
            if self.message(r, w)['ack']:
                return dict(delivery='acknowledged', notified=False)
            buffer = 'peer-' + uuid.uuid4().hex
            payload = ('[peer-task/v1] Read this task from the shared mailbox. Only acknowledge it yourself '
                       'after accepting its scope, then report running before work.\n' + pack(dict(
                           protocol='peer-task/v1', store=self.path, helper=str(Path(__file__).resolve()),
                           **json.loads(m['payload']))))
            try:
                tmux(identity['socket'], 'load-buffer', '-b', buffer, '-', data=payload)
                tmux(identity['socket'], 'paste-buffer', '-d', '-p', '-b', buffer, '-t', identity['pane'])
                time.sleep(0.3)
                tmux(identity['socket'], 'send-keys', '-t', identity['pane'], 'Enter')
            finally:
                try:
                    tmux(identity['socket'], 'delete-buffer', '-b', buffer)
                except subprocess.SubprocessError:
                    pass
        return dict(delivery='queued', notified=True, receipt_confirmed=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version='peer-task/v1 helper 1.0')
    p.add_argument('--store', required=True, help='shared task-owned SQLite path')
    p.add_argument('operation', choices=['enroll', 'send_task', 'acknowledge', 'report', 'get_status', 'read_updates', 'notify', 'reconcile'])
    p.add_argument('--request', required=True, help='JSON request file, or - for stdin')
    args = p.parse_args()
    try:
        r = json.load(sys.stdin) if args.request == '-' else json.loads(Path(args.request).read_text())
        need(isinstance(r, dict), 'request must be a JSON object')
        old_umask = os.umask(0o077)
        try:
            mailbox = Mailbox(args.store)
        finally:
            os.umask(old_umask)
        try:
            result = getattr(mailbox, args.operation)(r)
        finally:
            mailbox.db.close()
        print(pack(result))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, subprocess.SubprocessError) as e:
        print(pack(dict(error=str(e), operation=args.operation)), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; reconcile notification status before retry.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
