"""Compare saved SQLite samples offline; never prints raw account/life identifiers.

This is evidence collection, not permission to enable a cohort or infer births.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from probe_stats import anchored_value
from stats import ttf_observation_counters


def sample(path):
    path = Path(path).resolve(strict=True)
    # Immutable is safe here only for detached copies with no live journal/WAL.
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('detached SQLite copy without sidecars required')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        rows = db.execute('SELECT username,name,isDead,data,steamid,world FROM networkPlayers').fetchall()
    result = {}
    for username, name, dead, blob, account, world in rows:
        metadata = anchored_value(blob, 'TTFStatsMP')
        identity = metadata.get('characterID')
        if not isinstance(identity, str) or not identity or metadata.get('username') != username:
            raise ValueError('missing or mismatched identity')
        key = (world, identity)
        if key in result:
            raise ValueError('duplicate source life identifier')
        try:
            distance = anchored_value(blob, 'distanceTracker')
        except ValueError:
            distance = None
        result[key] = dict(account=str(account), username=username, name=name,
                           alive=dead == 0 if dead in (0, 1) else None,
                           counters=ttf_observation_counters(blob), distance=distance)
    return hashlib.sha256(path.read_bytes()).hexdigest(), result


def compare(previous, current):
    old_hash, old = sample(previous)
    new_hash, new = sample(current)
    common = old.keys() & new.keys()
    transitions = Counter()
    regressions = account_changes = renames = 0
    for key in common:
        before, after = old[key], new[key]
        account_changes += before['account'] != after['account']
        renames += (before['username'], before['name']) != (after['username'], after['name'])
        transitions[str(before['alive']) + '->' + str(after['alive'])] += 1
        for metric, value in (after['counters'] or {}).items():
            if metric in (before['counters'] or {}) and value < before['counters'][metric]:
                regressions += 1
        if before['distance'] is not None and after['distance'] is not None and after['distance'] < before['distance']:
            regressions += 1
    return dict(previous_sha256=old_hash, current_sha256=new_hash, previous_rows=len(old),
                current_rows=len(new), retained_ids=len(common), new_ids=len(new.keys()-old.keys()),
                absent_ids=len(old.keys()-new.keys()), account_changes=account_changes,
                renames=renames, transitions=dict(transitions), counter_regressions=regressions,
                current_states=dict(Counter(str(r['alive']) for r in new.values())),
                categories_reconciled=sum(r['counters'] is not None for r in new.values()),
                distance_present=sum(r['distance'] is not None for r in new.values()),
                activation_authorized=False,
                limitation='New IDs alone do not certify birth, namespace generation or complete-life coverage.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous')
    parser.add_argument('current')
    args = parser.parse_args()
    print(json.dumps(compare(args.previous, args.current), sort_keys=True))
