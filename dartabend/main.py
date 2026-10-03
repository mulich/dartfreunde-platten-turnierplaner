import os
import json
import sqlite3
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, model_validator

from .scheduler import spielplan_erstellen
from .history_import import import_history

STATIC = Path(__file__).parent / 'static'
DEFAULT_PLAYERS = ('Muli', 'Bruce', 'Ly', 'Schlatho', 'Michel', 'Rote', 'Manuel', 'Swobi')


@contextmanager
def database():
    path = Path(os.environ.get('TOURNAMENT_DB', 'data/tournaments.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_database():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS tournaments (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
            finished_at TEXT, boards INTEGER NOT NULL CHECK(boards IN (2,3))
        );
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY, tournament_id TEXT NOT NULL REFERENCES tournaments(id),
            name TEXT NOT NULL, position INTEGER NOT NULL,
            UNIQUE(tournament_id, name)
        );
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY, tournament_id TEXT NOT NULL REFERENCES tournaments(id),
            number INTEGER NOT NULL, round INTEGER NOT NULL, wave INTEGER NOT NULL,
            board TEXT NOT NULL, player1 TEXT NOT NULL, player2 TEXT NOT NULL,
            score1 INTEGER, score2 INTEGER, revision INTEGER NOT NULL DEFAULT 0,
            CHECK ((score1 IS NULL AND score2 IS NULL) OR
                   (score1 >= 0 AND score2 >= 0 AND score1 != score2)),
            UNIQUE(tournament_id, number)
        );
        CREATE INDEX IF NOT EXISTS matches_tournament ON matches(tournament_id);
        CREATE INDEX IF NOT EXISTS players_tournament ON players(tournament_id);
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(tournaments)')}
        for name, kind in [('archived_at', 'TEXT'), ('aborted_at', 'TEXT'), ('source_file', 'TEXT'),
                           ('source_sha256', 'TEXT'), ('source_notes', "TEXT NOT NULL DEFAULT '[]'")]:
            if name not in columns:
                db.execute(f'ALTER TABLE tournaments ADD COLUMN {name} {kind}')
        db.execute('UPDATE tournaments SET archived_at=finished_at WHERE finished_at IS NOT NULL AND archived_at IS NULL')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS tournament_source ON tournaments(source_sha256)')
        db.execute('PRAGMA user_version = 3')
        db.execute('CREATE TABLE IF NOT EXISTS deleted_imports (source_sha256 TEXT PRIMARY KEY)')
        history = Path(os.environ.get('TOURNAMENT_HISTORY', ''))
        if history.is_file():
            import_history(db, history)


@asynccontextmanager
async def lifespan(app):
    init_database()
    yield


app = FastAPI(title='Dartfreunde Platten · Turnierplaner', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    players: list[str] = Field(min_length=2, max_length=64)
    boards: StrictInt = Field(default=2, ge=2, le=3)

    @model_validator(mode='after')
    def validate_names(self):
        self.name = self.name.strip()
        self.players = [name.strip() for name in self.players]
        if not self.name or any(not name or len(name) > 60 for name in self.players):
            raise ValueError('Turniername und Spielernamen dürfen nicht leer sein. Spielernamen: maximal 60 Zeichen.')
        if len({name.casefold() for name in self.players}) != len(self.players):
            raise ValueError('Jeder Spielername darf nur einmal vorkommen.')
        if any(name.casefold() == 'pause' for name in self.players):
            raise ValueError('PAUSE ist für Freilose reserviert. Bitte einen anderen Namen verwenden.')
        return self


class ScoreUpdate(BaseModel):
    score1: StrictInt | None = Field(default=None, ge=0, le=999)
    score2: StrictInt | None = Field(default=None, ge=0, le=999)
    revision: StrictInt = Field(ge=0)

    @model_validator(mode='after')
    def validate_score(self):
        if (self.score1 is None) != (self.score2 is None):
            raise ValueError('Bitte beide Ergebnisse eintragen.')
        if self.score1 is not None and self.score1 == self.score2:
            raise ValueError('Ein Dartspiel benötigt einen Sieger; Unentschieden sind nicht möglich.')
        return self


def get_tournament(db, tournament_id):
    row = db.execute('SELECT * FROM tournaments WHERE id=?', (tournament_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Turnier nicht gefunden.')
    tournament = dict(row)
    tournament['source_notes'] = json.loads(tournament['source_notes'])
    return tournament


def standings(players, matches):
    stats = {name: dict(name=name, played=0, wins=0, losses=0, points=0,
                       legs_for=0, legs_against=0, difference=0) for name in players}
    for match in matches:
        if match['score1'] is None:
            continue
        for name, own, other in [(match['player1'], match['score1'], match['score2']),
                                 (match['player2'], match['score2'], match['score1'])]:
            player = stats[name]
            player['played'] += 1
            player['wins'] += int(own > other)
            player['losses'] += int(own < other)
            player['points'] += 2 * int(own > other)
            player['legs_for'] += own
            player['legs_against'] += other
            player['difference'] = player['legs_for'] - player['legs_against']
    key = lambda p: (p['points'], p['legs_for'], p['difference'])
    result = sorted(stats.values(), key=key, reverse=True)
    previous, rank = None, 0
    for index, player in enumerate(result, 1):
        if key(player) != previous:
            rank = index
        player['rank'] = rank
        previous = key(player)
    return result


def detail(db, tournament_id):
    tournament = get_tournament(db, tournament_id)
    players = [r['name'] for r in db.execute('SELECT name FROM players WHERE tournament_id=? ORDER BY position', (tournament_id,))]
    matches = [dict(r) for r in db.execute('SELECT * FROM matches WHERE tournament_id=? ORDER BY number', (tournament_id,))]
    tournament.update(players=players, matches=matches, standings=standings(players, matches),
                      total=len(matches), played=sum(m['score1'] is not None for m in matches))
    return tournament


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


@app.get('/health')
def health():
    with database() as db:
        db.execute('SELECT 1 FROM tournaments LIMIT 1')
    return {'status': 'ok'}


@app.get('/api/tournaments')
def list_tournaments():
    with database() as db:
        result = []
        for row in db.execute('SELECT * FROM tournaments ORDER BY created_at DESC, id'):
            t = dict(row)
            t['players'] = db.execute('SELECT COUNT(*) FROM players WHERE tournament_id=?', (t['id'],)).fetchone()[0]
            t['total'], t['played'] = db.execute('SELECT COUNT(*), COUNT(score1) FROM matches WHERE tournament_id=?', (t['id'],)).fetchone()
            t['winner'] = None
            if t['archived_at'] and not t['aborted_at'] and t['played'] == t['total']:
                t['winner'] = ' / '.join(p['name'] for p in detail(db, t['id'])['standings'] if p['rank'] == 1)
            result.append(t)
        return result


@app.get('/api/players')
def player_shortcuts():
    """Defaults plus names from saved tournaments, without case duplicates."""
    names = {name.casefold(): name for name in DEFAULT_PLAYERS}
    with database() as db:
        for row in db.execute('SELECT name FROM players ORDER BY id'):
            names.setdefault(row['name'].casefold(), row['name'])
    return list(DEFAULT_PLAYERS) + sorted(
        (name for key, name in names.items() if key not in {p.casefold() for p in DEFAULT_PLAYERS}),
        key=str.casefold,
    )


@app.post('/api/tournaments', status_code=201)
def create_tournament(body: TournamentCreate):
    tournament_id = str(uuid4())
    boards = ['Rot', 'Blau', 'Schwarz'][:body.boards]
    plan, _, _ = spielplan_erstellen(body.players, boards)
    plan.sort(key=lambda m: (m['durchgang'], boards.index(m['scheibe'])))
    with database() as db:
        db.execute('INSERT INTO tournaments(id,name,created_at,boards) VALUES(?,?,?,?)',
                   (tournament_id, body.name, datetime.now(timezone.utc).isoformat(), body.boards))
        db.executemany('INSERT INTO players(tournament_id,name,position) VALUES(?,?,?)',
                       [(tournament_id, name, i) for i, name in enumerate(body.players)])
        db.executemany('INSERT INTO matches(tournament_id,number,round,wave,board,player1,player2) VALUES(?,?,?,?,?,?,?)',
                       [(tournament_id, i, m['runde'], m['durchgang'], m['scheibe'], m['spieler1'], m['spieler2'])
                        for i, m in enumerate(plan, 1)])
        return detail(db, tournament_id)


@app.get('/api/tournaments/{tournament_id}')
def tournament_detail(tournament_id: str):
    with database() as db:
        return detail(db, tournament_id)


@app.put('/api/tournaments/{tournament_id}/matches/{match_id}')
def update_score(tournament_id: str, match_id: int, body: ScoreUpdate):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        t = get_tournament(db, tournament_id)
        if t['archived_at']:
            raise HTTPException(409, 'Bitte das Turnier vor einer Korrektur wieder öffnen.')
        match = db.execute('SELECT * FROM matches WHERE id=? AND tournament_id=?', (match_id, tournament_id)).fetchone()
        if not match:
            raise HTTPException(404, 'Spiel nicht gefunden.')
        if match['revision'] != body.revision:
            raise HTTPException(409, 'Dieses Ergebnis wurde inzwischen geändert. Ansicht neu laden und erneut prüfen.')
        db.execute('UPDATE matches SET score1=?,score2=?,revision=revision+1 WHERE id=?', (body.score1, body.score2, match_id))
        return detail(db, tournament_id)


@app.post('/api/tournaments/{tournament_id}/finish')
def finish_tournament(tournament_id: str):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        t = detail(db, tournament_id)
        if t['aborted_at']:
            raise HTTPException(409, 'Das abgebrochene Turnier zuerst wieder öffnen.')
        if t['played'] != t['total']:
            raise HTTPException(409, 'Zuerst die Ergebnisse aller Spiele eintragen.')
        if not t['finished_at']:
            now = datetime.now(timezone.utc).isoformat()
            db.execute('UPDATE tournaments SET finished_at=?,archived_at=? WHERE id=?', (now, now, tournament_id))
        return detail(db, tournament_id)


@app.post('/api/tournaments/{tournament_id}/reopen')
def reopen_tournament(tournament_id: str):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        get_tournament(db, tournament_id)
        db.execute('UPDATE tournaments SET finished_at=NULL,archived_at=NULL,aborted_at=NULL WHERE id=?', (tournament_id,))
        return detail(db, tournament_id)


@app.delete('/api/tournaments/{tournament_id}')
def delete_tournament(tournament_id: str):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        t = get_tournament(db, tournament_id)
        if not t['archived_at'] and not t['finished_at']:
            raise HTTPException(409, 'Nur Turniere im Archiv können gelöscht werden.')
        if t['source_sha256']:
            db.execute('INSERT OR IGNORE INTO deleted_imports(source_sha256) VALUES(?)', (t['source_sha256'],))
        db.execute('DELETE FROM matches WHERE tournament_id=?', (tournament_id,))
        db.execute('DELETE FROM players WHERE tournament_id=?', (tournament_id,))
        db.execute('DELETE FROM tournaments WHERE id=?', (tournament_id,))
    return {'deleted': tournament_id}


@app.post('/api/tournaments/{tournament_id}/abort')
def abort_tournament(tournament_id: str):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        t = get_tournament(db, tournament_id)
        if t['aborted_at']:
            return detail(db, tournament_id)
        if t['archived_at'] or t['finished_at']:
            raise HTTPException(409, 'Nur laufende Turniere können abgebrochen werden.')
        now = datetime.now(timezone.utc).isoformat()
        db.execute('UPDATE tournaments SET aborted_at=?,archived_at=? WHERE id=?', (now, now, tournament_id))
        return detail(db, tournament_id)
