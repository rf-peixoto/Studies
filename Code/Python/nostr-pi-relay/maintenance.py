#!/usr/bin/env python3
"""Offline schema-validated pruning. Stops the relay while it works, then restarts it."""
import json, os, shutil, sqlite3, subprocess, time
from pathlib import Path

p = json.loads(Path('/etc/nostrgw/policy.json').read_text()); root = Path(p['data_path']); file = root / 'nostr.db'
if not file.exists(): raise SystemExit('No database yet')


def total(): return sum(f.stat().st_size for f in root.glob('nostr.db*') if f.is_file())


# Do not stop the relay on every timer invocation; only trigger at warning threshold.
if total() < p['prune_bytes']: raise SystemExit(0)

owner = file.stat()
uid = subprocess.check_output(['id', '-u', 'nostr'], text=True).strip()


def ctl(*args):
    return subprocess.run(['runuser', '-u', 'nostr', '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
                           f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', 'systemctl', '--user', *args], check=True, cwd='/')


def live_bytes(c):
    pages = c.execute('PRAGMA page_count').fetchone()[0]; free = c.execute('PRAGMA freelist_count').fetchone()[0]
    return (pages - free) * c.execute('PRAGMA page_size').fetchone()[0]


# Keep SQLite's VACUUM temp copy on the same filesystem we measure free space on.
os.environ['SQLITE_TMPDIR'] = str(root)
ctl('stop', 'nostr-relay.service')
try:
    c = sqlite3.connect(file, timeout=30); c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=30000')
    cols = {x[1] for x in c.execute('PRAGMA table_info(event)')}
    if not {'first_seen', 'kind', 'hidden'}.issubset(cols): raise RuntimeError('Unsupported upstream event schema, refusing to prune')
    # Mandatory FK safety checks on tag-like references to event, including cascades.
    for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        for fk in c.execute(f'PRAGMA foreign_key_list("{table}")'):
            if fk[2] == 'event' and fk[6].upper() != 'CASCADE': raise RuntimeError(f'Unsupported FK on {table}: no cascade')
    if c.execute('PRAGMA foreign_key_check').fetchone(): raise RuntimeError('Database has FK errors, aborting')
    cutoff = int(time.time()) - p['note_retention_days'] * 86400
    with c:
        c.execute('DELETE FROM event WHERE kind=1 AND first_seen<?', (cutoff,))
        c.execute('DELETE FROM event WHERE hidden=1')
    # Escalating pruning by live (non-free) pages: the file itself won't shrink until VACUUM.
    while live_bytes(c) > p['target_bytes']:
        with c:
            ids = c.execute('SELECT rowid FROM event WHERE kind=1 ORDER BY first_seen ASC LIMIT 5000').fetchall()
            if not ids:
                print('WARNING: no kind-1 notes left to prune; remaining data is metadata (kinds 0/3/10002)'); break
            c.executemany('DELETE FROM event WHERE rowid=?', ids)
    if c.execute('PRAGMA foreign_key_check').fetchone(): raise RuntimeError('FK check failed after pruning')
    c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    # VACUUM builds a full temp copy, then (in WAL mode) writes the result through the WAL:
    # budget about twice the live database size plus some slack.
    need = live_bytes(c) * 2 + 512 * 1024**2
    if shutil.disk_usage(root).free > need:
        c.execute('VACUUM'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    else:
        print(f'WARNING: VACUUM needs ~{need // 1024**2} MiB free; skipped. Pages are reusable but the file stays large')
    c.close()
finally:
    # This runs as root: give any files SQLite created back to the container's user.
    for f in root.glob('nostr.db*'):
        try: os.chown(f, owner.st_uid, owner.st_gid)
        except FileNotFoundError: pass
    ctl('start', 'nostr-relay.service')
print('DB bytes:', total())
