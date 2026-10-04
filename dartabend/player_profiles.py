"""Persistent display names and optional account aliases, independent of history."""
from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictInt, model_validator

class ProfileInput(BaseModel):
    name: str = Field(min_length=1,max_length=60)
    account_name: str | None = Field(default=None,max_length=60)
    revision: StrictInt = Field(default=0,ge=0)

    @model_validator(mode='after')
    def clean(self):
        self.name=self.name.strip()
        self.account_name=(self.account_name or '').strip() or None
        if not self.name or self.name.casefold()=='pause':
            raise ValueError('Bitte einen Spielernamen eingeben; PAUSE ist reserviert.')
        return self

def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS player_profiles (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, account_name TEXT,
        hidden INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS profile_aliases (
        name_key TEXT PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES player_profiles(id));''')

def lookup(db,name):
    row=db.execute('SELECT p.* FROM player_profiles p JOIN profile_aliases a ON a.profile_id=p.id WHERE a.name_key=?',(name.casefold(),)).fetchone()
    return dict(row) if row else None

def ensure(db,name):
    profile=lookup(db,name)
    if profile:return profile
    ident=db.execute('INSERT INTO player_profiles(name) VALUES(?)',(name,)).lastrowid
    db.execute('INSERT INTO profile_aliases VALUES(?,?)',(name.casefold(),ident))
    return lookup(db,name)

def seed(db,defaults):
    for name in [*defaults,*[r['name'] for r in db.execute('SELECT name FROM players ORDER BY id')]]:ensure(db,name)

def participants(db,names):
    return [{'name':name,'account_name':(lookup(db,name) or {}).get('account_name')} for name in names]

def install(app,database,defaults):
    @app.get('/api/player-profiles')
    def profiles():
        with database() as db:
            seed(db,defaults)
            return [dict(r) for r in db.execute('SELECT id,name,account_name,revision FROM player_profiles WHERE hidden=0 ORDER BY id')]

    def save(db,body,ident=None):
        existing=lookup(db,body.name)
        if existing and existing['id']!=ident:
            if ident is None and existing['hidden']:
                ident=existing['id'];body.revision=existing['revision']
            else:raise HTTPException(409,'Dieser Spielername ist bereits vorhanden (auch als früherer Name).')
        if body.account_name:
            for row in db.execute('SELECT id,account_name FROM player_profiles WHERE account_name IS NOT NULL'):
                if row['id']!=ident and row['account_name'].casefold()==body.account_name.casefold():
                    raise HTTPException(409,'Dieser Autodarts-Account ist bereits einem anderen Spieler zugewiesen.')
        if ident is None:
            ident=db.execute('INSERT INTO player_profiles(name,account_name) VALUES(?,?)',(body.name,body.account_name)).lastrowid
        else:
            row=db.execute('SELECT * FROM player_profiles WHERE id=?',(ident,)).fetchone()
            if not row:raise HTTPException(404,'Spieler nicht gefunden.')
            if row['revision']!=body.revision:raise HTTPException(409,'Spieler inzwischen geändert. Ansicht aktualisieren.')
            db.execute('UPDATE player_profiles SET name=?,account_name=?,hidden=0,revision=revision+1 WHERE id=?',(body.name,body.account_name,ident))
        db.execute('INSERT OR IGNORE INTO profile_aliases VALUES(?,?)',(body.name.casefold(),ident))
        return dict(db.execute('SELECT id,name,account_name,revision FROM player_profiles WHERE id=?',(ident,)).fetchone())

    @app.post('/api/player-profiles',status_code=201)
    def create(body:ProfileInput):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');return save(db,body)

    @app.put('/api/player-profiles/{ident}')
    def update(ident:int,body:ProfileInput):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');return save(db,body,ident)

    @app.delete('/api/player-profiles/{ident}')
    def remove(ident:int,revision:int):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM player_profiles WHERE id=?',(ident,)).fetchone()
            if not row:raise HTTPException(404,'Spieler nicht gefunden.')
            if row['revision']!=revision:raise HTTPException(409,'Spieler inzwischen geändert. Ansicht aktualisieren.')
            db.execute('UPDATE player_profiles SET hidden=1,revision=revision+1 WHERE id=?',(ident,))
        return {'removed':ident}
