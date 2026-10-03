"""Board-scoped coordination. Autodarts credentials never leave the board browser."""
import os
import hashlib
import hmac
import json
import secrets
import time
from typing import Literal
from uuid import uuid4

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field, StrictInt, model_validator

BOARDS = {
    'Blau': 'faa2cd5f-5d19-4e68-9749-1b7b95c753d4',
    'Rot': 'ad381dc0-7e86-45a1-9fa8-61c8b18ec89b',
    'Schwarz': '6e390006-cdba-4ac5-b0bb-0e03eb880af6',
}


class GameSettings(BaseModel):
    base_score: Literal[121, 170, 301, 501, 701, 901] = 501
    length_mode: Literal['best_of', 'first_to'] = 'best_of'
    length: StrictInt = Field(default=3, ge=1, le=99)
    in_mode: Literal['Straight', 'Double', 'Master'] = 'Straight'
    out_mode: Literal['Straight', 'Double', 'Master'] = 'Double'
    bull_mode: Literal['25/50', '50/50'] = '25/50'
    max_rounds: Literal[15, 20, 50, 80] = 50

    @model_validator(mode='after')
    def validate_length(self):
        if self.length_mode == 'best_of' and self.length % 2 == 0:
            raise ValueError('Best of benötigt eine ungerade Anzahl Legs.')
        if self.target > 50:
            raise ValueError('Maximal 50 Legs zum Sieg.')
        return self

    @property
    def target(self):
        return self.length // 2 + 1 if self.length_mode == 'best_of' else self.length

    def lobby(self):
        return {'variant': 'X01', 'isPrivate': True, 'bullOffMode': 'Off', 'legs': self.target,
                'settings': {'baseScore': self.base_score, 'inMode': self.in_mode,
                             'outMode': self.out_mode, 'bullMode': self.bull_mode,
                             'maxRounds': self.max_rounds}}


class Automation(BaseModel):
    enabled: bool


class Poll(BaseModel):
    instance: str = Field(min_length=16, max_length=80)
    status: str = Field(default='', max_length=240)
    ready: bool = False


class JobUpdate(BaseModel):
    instance: str = Field(min_length=16, max_length=80)
    phase: Literal['creating', 'lobby', 'starting', 'playing']
    lobby_id: str | None = Field(default=None, max_length=80)
    autodarts_match_id: str | None = Field(default=None, max_length=80)
    user_ids: list[str] | None = Field(default=None, min_length=2, max_length=2)
    error: str = Field(default='', max_length=240)


class Result(BaseModel):
    instance: str = Field(min_length=16, max_length=80)
    autodarts_match_id: str = Field(min_length=1, max_length=80)
    user_ids: list[str] = Field(min_length=2, max_length=2)
    score1: StrictInt = Field(ge=0, le=50)
    score2: StrictInt = Field(ge=0, le=50)


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS board_bridges (
        name TEXT PRIMARY KEY, board_id TEXT NOT NULL, key_hash TEXT,
        last_seen REAL, status TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS bridge_jobs (
        id TEXT PRIMARY KEY, match_id INTEGER UNIQUE NOT NULL REFERENCES matches(id),
        board TEXT NOT NULL, phase TEXT NOT NULL DEFAULT 'queued', owner TEXT,
        lease_until REAL NOT NULL DEFAULT 0, lobby_id TEXT, autodarts_match_id TEXT,
        user_ids TEXT, revision INTEGER NOT NULL, error TEXT NOT NULL DEFAULT ''
    );
    ''')
    for name, ident in BOARDS.items():
        db.execute('INSERT OR IGNORE INTO board_bridges(name,board_id) VALUES(?,?)', (name, ident))


def install(app, database, get_tournament, detail):
    def admin(key):
        expected = os.environ.get('TOURNAMENT_ADMIN_KEY', '')
        if not expected:
            raise HTTPException(503, 'Für Autodarts zuerst TOURNAMENT_ADMIN_KEY im Docker-Container setzen.')
        if not key or not hmac.compare_digest(key, expected):
            raise HTTPException(401, 'Autodarts-Verwaltungsschlüssel ungültig.')

    def authenticate(db, authorization):
        token = authorization.removeprefix('Bearer ') if authorization else ''
        digest = hashlib.sha256(token.encode()).hexdigest()
        for row in db.execute('SELECT * FROM board_bridges WHERE key_hash IS NOT NULL'):
            if token and hmac.compare_digest(digest, row['key_hash']):
                return dict(row)
        raise HTTPException(401, 'Board-Schlüssel ungültig.')

    def owned_job(db, board, job_id, instance):
        row = db.execute('SELECT * FROM bridge_jobs WHERE id=? AND board=?', (job_id, board['name'])).fetchone()
        if not row:
            raise HTTPException(404, 'Board-Auftrag nicht gefunden.')
        job = dict(row)
        if job['owner'] != instance or job['lease_until'] < time.time():
            raise HTTPException(409, 'Auftrag wird von einer anderen Board-Sitzung bearbeitet. Erneut verbinden.')
        return job

    def job_payload(db, job):
        match = dict(db.execute('SELECT * FROM matches WHERE id=?', (job['match_id'],)).fetchone())
        t = get_tournament(db, match['tournament_id'])
        return {**job, 'user_ids': json.loads(job['user_ids']) if job['user_ids'] else None,
                'match': match, 'board_id': BOARDS[job['board']], 'tournament_name': t['name'],
                'paused': not t['autodarts_enabled'] or bool(t['archived_at']),
                'lobby_payload': GameSettings.model_validate(t['game_settings']).lobby()}

    @app.get('/api/integration')
    def integration_status():
        with database() as db:
            boards = [dict(r) for r in db.execute('SELECT name,board_id,last_seen,status FROM board_bridges ORDER BY name')]
            for b in boards:
                b['online'] = bool(b['last_seen'] and time.time() - b['last_seen'] < 25)
                b['paired'] = bool(db.execute('SELECT key_hash FROM board_bridges WHERE name=?', (b['name'],)).fetchone()[0])
            jobs = [dict(r) for r in db.execute('''SELECT j.id,j.board,j.phase,j.error,j.lobby_id,j.autodarts_match_id,
                 m.tournament_id,m.number FROM bridge_jobs j JOIN matches m ON m.id=j.match_id WHERE j.phase!='done' ''')]
            return {'boards': boards, 'jobs': jobs}

    @app.post('/api/integration/boards/{board_name}/pair')
    def pair(board_name: str, x_integration_key: str | None = Header(default=None)):
        admin(x_integration_key)
        if board_name not in BOARDS:
            raise HTTPException(404, 'Scheibe nicht gefunden.')
        key = secrets.token_urlsafe(32)
        with database() as db:
            db.execute('UPDATE board_bridges SET key_hash=?,last_seen=NULL,status=? WHERE name=?',
                       (hashlib.sha256(key.encode()).hexdigest(), 'Script verbinden', board_name))
        return {'key': key, 'board': board_name, 'board_id': BOARDS[board_name]}

    @app.post('/api/tournaments/{tournament_id}/automation')
    def automation(tournament_id: str, body: Automation, x_integration_key: str | None = Header(default=None)):
        admin(x_integration_key)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            t = get_tournament(db, tournament_id)
            if t['archived_at'] and body.enabled:
                raise HTTPException(409, 'Das Turnier zuerst wieder öffnen.')
            if body.enabled and not t['game_settings_known']:
                raise HTTPException(409, 'Zuerst die Spielregeln für die kommenden Begegnungen speichern.')
            if body.enabled and db.execute('SELECT id FROM tournaments WHERE autodarts_enabled=1 AND archived_at IS NULL AND id!=?', (tournament_id,)).fetchone():
                raise HTTPException(409, 'Die Automatik eines anderen Turniers zuerst pausieren.')
            db.execute('UPDATE tournaments SET autodarts_enabled=? WHERE id=?', (int(body.enabled), tournament_id))
            return detail(db, tournament_id)

    @app.post('/api/tournaments/{tournament_id}/game-settings')
    def settings(tournament_id: str, body: GameSettings, x_integration_key: str | None = Header(default=None)):
        admin(x_integration_key)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            t = get_tournament(db, tournament_id)
            if t['archived_at'] or t['autodarts_enabled']:
                raise HTTPException(409, 'Spielregeln nur in einem offenen, pausierten Turnier ändern.')
            if db.execute("SELECT j.id FROM bridge_jobs j JOIN matches m ON m.id=j.match_id WHERE m.tournament_id=? AND j.phase!='done'", (tournament_id,)).fetchone():
                raise HTTPException(409, 'Offene Autodarts-Zuordnungen zuerst beenden und zurücksetzen.')
            db.execute('UPDATE tournaments SET game_settings=? WHERE id=?', (body.model_dump_json(), tournament_id))
            return detail(db, tournament_id)

    @app.post('/api/integration/jobs/{job_id}/reset')
    def reset(job_id: str, x_integration_key: str | None = Header(default=None)):
        admin(x_integration_key)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM bridge_jobs WHERE id=?', (job_id,)).fetchone()
            if not job:
                raise HTTPException(404, 'Auftrag nicht gefunden.')
            match = db.execute('SELECT * FROM matches WHERE id=?', (job['match_id'],)).fetchone()
            t = get_tournament(db, match['tournament_id'])
            if t['autodarts_enabled'] and not t['archived_at']:
                raise HTTPException(409, 'Automatik vor dem Zurücksetzen pausieren.')
            if match['score1'] is not None:
                raise HTTPException(409, 'Ein gespeichertes Ergebnis wird nicht zurückgesetzt.')
            db.execute('DELETE FROM bridge_jobs WHERE id=?', (job_id,))
            return {'reset': job_id}

    @app.post('/api/bridge/poll')
    def poll(body: Poll, authorization: str | None = Header(default=None)):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            board = authenticate(db, authorization)
            now = time.time()
            db.execute('UPDATE board_bridges SET last_seen=?,status=? WHERE name=?', (now, body.status, board['name']))
            existing = db.execute('''SELECT j.* FROM bridge_jobs j JOIN matches m ON m.id=j.match_id
                 WHERE j.board=? AND j.phase!='done' ORDER BY m.id LIMIT 1''', (board['name'],)).fetchone()
            if existing:
                job = dict(existing)
                if job['owner'] != body.instance and job['lease_until'] > now:
                    return {'job': None, 'message': 'Eine andere Script-Sitzung steuert diese Scheibe.'}
                db.execute('UPDATE bridge_jobs SET owner=?,lease_until=? WHERE id=?', (body.instance, now+75, job['id']))
                job.update(owner=body.instance, lease_until=now+75)
                return {'job': job_payload(db, job)}
            completed = db.execute("SELECT autodarts_match_id FROM bridge_jobs WHERE board=? AND phase='done' ORDER BY match_id DESC LIMIT 1", (board['name'],)).fetchone()
            idle = {'job': None, 'completed_match_id': completed[0] if completed else None}
            if not body.ready:
                return idle
            # Barrier: do not invite players for the next wave while the current wave is unfinished.
            row = db.execute('''SELECT m.* FROM matches m JOIN tournaments t ON t.id=m.tournament_id
              WHERE t.autodarts_enabled=1 AND t.archived_at IS NULL AND m.score1 IS NULL AND m.board=?
                AND m.wave=(SELECT MIN(wave) FROM matches WHERE tournament_id=m.tournament_id AND score1 IS NULL)
              ORDER BY t.created_at,m.number LIMIT 1''', (board['name'],)).fetchone()
            if not row:
                return idle
            ident = str(uuid4())
            db.execute('INSERT INTO bridge_jobs(id,match_id,board,owner,lease_until,revision) VALUES(?,?,?,?,?,?)',
                       (ident, row['id'], board['name'], body.instance, now+75, row['revision']))
            job = dict(db.execute('SELECT * FROM bridge_jobs WHERE id=?', (ident,)).fetchone())
            return {'job': job_payload(db, job)}

    @app.post('/api/bridge/jobs/{job_id}/state')
    def update_job(job_id: str, body: JobUpdate, authorization: str | None = Header(default=None)):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            board = authenticate(db, authorization)
            job = owned_job(db, board, job_id, body.instance)
            allowed = {'queued': 'creating', 'creating': 'lobby', 'lobby': 'starting', 'starting': 'playing'}
            if body.phase != job['phase'] and allowed.get(job['phase']) != body.phase:
                raise HTTPException(409, 'Ungültiger Auftragsschritt.')
            match = db.execute('SELECT * FROM matches WHERE id=?', (job['match_id'],)).fetchone()
            t = get_tournament(db, match['tournament_id'])
            if (t['archived_at'] or not t['autodarts_enabled']) and body.phase != job['phase']:
                raise HTTPException(409, 'Turnier-Automatik ist pausiert oder beendet.')
            lobby_id = body.lobby_id or job['lobby_id']
            match_id = body.autodarts_match_id or job['autodarts_match_id']
            users = body.user_ids or (json.loads(job['user_ids']) if job['user_ids'] else None)
            if body.phase in ['lobby', 'starting', 'playing'] and not lobby_id:
                raise HTTPException(422, 'Lobby-ID fehlt.')
            if body.phase in ['starting', 'playing'] and (not users or len(set(users)) != 2 or any(not u or len(u)>80 for u in users)):
                raise HTTPException(422, 'Zwei eindeutige Spieleraccounts erforderlich.')
            if body.phase == 'playing' and not match_id:
                raise HTTPException(422, 'Match-ID fehlt.')
            if job['lobby_id'] and lobby_id != job['lobby_id'] or job['autodarts_match_id'] and match_id != job['autodarts_match_id'] or job['user_ids'] and json.loads(job['user_ids']) != users:
                raise HTTPException(409, 'Bestehende Zuordnung darf nicht überschrieben werden.')
            db.execute('UPDATE bridge_jobs SET phase=?,lobby_id=?,autodarts_match_id=?,user_ids=?,error=? WHERE id=?',
                       (body.phase, lobby_id, match_id, json.dumps(users) if users else None, body.error, job_id))
            return {'job': job_payload(db, dict(db.execute('SELECT * FROM bridge_jobs WHERE id=?', (job_id,)).fetchone()))}

    @app.post('/api/bridge/jobs/{job_id}/result')
    def result(job_id: str, body: Result, authorization: str | None = Header(default=None)):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            board = authenticate(db, authorization)
            job = owned_job(db, board, job_id, body.instance)
            match = db.execute('SELECT * FROM matches WHERE id=?', (job['match_id'],)).fetchone()
            t = get_tournament(db, match['tournament_id'])
            if job['autodarts_match_id'] != body.autodarts_match_id or job['user_ids'] != json.dumps(body.user_ids):
                raise HTTPException(409, 'Autodarts-Match oder Spieler stimmen nicht mit dem Auftrag überein.')
            if job['phase'] == 'done' and (match['score1'], match['score2']) == (body.score1, body.score2):
                return {'saved': True}
            if job['phase'] != 'playing' or t['archived_at'] or match['revision'] != job['revision'] or match['score1'] is not None:
                raise HTTPException(409, 'Ergebnis bereits geändert oder Turnier beendet. Manuell prüfen.')
            target = GameSettings.model_validate(t['game_settings']).target
            if max(body.score1, body.score2) != target or min(body.score1, body.score2) >= target:
                raise HTTPException(422, 'Ergebnis entspricht keinem abgeschlossenen Match mit diesem Leg-Ziel.')
            db.execute('UPDATE matches SET score1=?,score2=?,revision=revision+1 WHERE id=?', (body.score1, body.score2, job['match_id']))
            db.execute("UPDATE bridge_jobs SET phase='done',error='' WHERE id=?", (job_id,))
            return {'saved': True}
