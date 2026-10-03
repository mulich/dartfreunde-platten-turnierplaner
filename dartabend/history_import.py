"""Validated, repeatable import of extracted Excel tournament data."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def validate_tournament(t):
    if not re.fullmatch(r'[0-9a-f]{64}', t['source_sha256']):
        raise ValueError('Invalid source fingerprint')
    datetime.fromisoformat(t['created_at'])
    names = t['players']
    if not 2 <= len(names) <= 64 or len({n.casefold() for n in names}) != len(names):
        raise ValueError('Invalid or duplicate players')
    if any(not n.strip() or len(n) > 60 for n in names):
        raise ValueError('Invalid player name')
    if t['boards'] not in (2, 3):
        raise ValueError('Invalid board count')
    matches = t['matches']
    if len(matches) != len(names) * (len(names) - 1) // 2:
        raise ValueError('Incomplete round-robin schedule')
    pairs, waves, numbers = set(), {}, set()
    for m in matches:
        pair = frozenset((m['player1'], m['player2']))
        if len(pair) != 2 or not pair <= set(names) or pair in pairs:
            raise ValueError('Invalid or repeated pairing')
        pairs.add(pair)
        if any(type(m[k]) is not int or m[k] < 1 for k in ('number', 'round', 'wave')):
            raise ValueError('Invalid match numbering')
        if m['number'] in numbers:
            raise ValueError('Repeated match number')
        numbers.add(m['number'])
        if m['board'] not in ['Rot', 'Blau', 'Schwarz'][:t['boards']]:
            raise ValueError('Invalid board')
        players, boards = waves.setdefault(m['wave'], (set(), set()))
        if players & pair or m['board'] in boards:
            raise ValueError('Player or board collision')
        players.update(pair)
        boards.add(m['board'])
        one, two = m['score1'], m['score2']
        if one is None and two is None:
            continue
        if any(type(s) is not int or not 0 <= s <= 999 for s in (one, two)) or one == two:
            raise ValueError('Invalid match result')
    if numbers != set(range(1, len(matches) + 1)):
        raise ValueError('Missing match numbers')


def import_history(db, path: Path):
    tournaments = json.loads(Path(path).read_text(encoding='utf-8'))
    # Validate the entire batch before writing any rows.
    for t in tournaments:
        validate_tournament(t)
    now = datetime.now(timezone.utc).isoformat()
    imported, skipped = [], []
    db.execute('SAVEPOINT excel_history')
    try:
        for t in tournaments:
            existing = db.execute('SELECT id FROM tournaments WHERE source_sha256=?', (t['source_sha256'],)).fetchone()
            deleted = db.execute('SELECT source_sha256 FROM deleted_imports WHERE source_sha256=?', (t['source_sha256'],)).fetchone()
            if existing or deleted:
                skipped.append(existing['id'] if existing else str(uuid5(NAMESPACE_URL, 'dartabend:excel:' + t['source_sha256'])))
                continue
            tournament_id = str(uuid5(NAMESPACE_URL, 'dartabend:excel:' + t['source_sha256']))
            db.execute('''INSERT INTO tournaments
                (id,name,created_at,boards,archived_at,source_file,source_sha256,source_notes)
                VALUES(?,?,?,?,?,?,?,?)''',
                (tournament_id, t['name'], t['created_at'], t['boards'], now,
                 t['source_file'], t['source_sha256'], json.dumps(t.get('source_notes', []), ensure_ascii=False)))
            db.executemany('INSERT INTO players(tournament_id,name,position) VALUES(?,?,?)',
                           [(tournament_id, name, i) for i, name in enumerate(t['players'])])
            db.executemany('''INSERT INTO matches
                (tournament_id,number,round,wave,board,player1,player2,score1,score2)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                [(tournament_id, m['number'], m['round'], m['wave'], m['board'],
                  m['player1'], m['player2'], m['score1'], m['score2']) for m in t['matches']])
            imported.append(tournament_id)
        db.execute('RELEASE excel_history')
    except Exception:
        db.execute('ROLLBACK TO excel_history')
        db.execute('RELEASE excel_history')
        raise
    return {'imported': imported, 'skipped': skipped}
