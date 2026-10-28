#!/usr/bin/env python3
"""Daily online backup of the relay database, ban state and policy.

Uses SQLite's backup API, so the relay keeps running. Backups land on the same
card by default: copy backup_dir off the Pi (rsync/scp) to survive card failure.
"""
import json, shutil, sqlite3, time
from pathlib import Path

p = json.loads(Path('/etc/nostrgw/policy.json').read_text())
dest_root = Path(p.get('backup_dir', '/var/backups/nostr-relay')); keep = max(1, int(p.get('backup_keep', 3)))
dest_root.mkdir(parents=True, exist_ok=True); dest_root.chmod(0o700)
dest = dest_root / time.strftime('%Y%m%d-%H%M%S'); tmp = dest.with_suffix('.partial'); tmp.mkdir()


def copy_db(src, out):
    if not src.exists(): return
    s = sqlite3.connect(f'file:{src}?mode=ro', uri=True, timeout=30)
    d = sqlite3.connect(out)
    try:
        s.backup(d, pages=1024, sleep=0.05)  # small steps so the relay isn't starved of the lock
    finally:
        d.close(); s.close()


copy_db(Path(p['data_path']) / 'nostr.db', tmp / 'nostr.db')
copy_db(Path('/var/lib/nostrgw/abuse.sqlite3'), tmp / 'abuse.sqlite3')
shutil.copy2('/etc/nostrgw/policy.json', tmp / 'policy.json')
tmp.rename(dest)

for old in sorted(x for x in dest_root.iterdir() if x.is_dir() and x.suffix != '.partial')[:-keep]:
    shutil.rmtree(old)
for stale in dest_root.glob('*.partial'):
    shutil.rmtree(stale, ignore_errors=True)
print('Backup written to', dest)
