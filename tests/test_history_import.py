import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dartabend.main import app, database, init_database
from dartabend.history_import import import_history


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / 'history.sqlite3'
    monkeypatch.setenv('TOURNAMENT_DB', str(path))
    monkeypatch.setenv('TOURNAMENT_HISTORY', '')
    init_database()
    return path


def source_tournament():
    return dict(name='Turnier · 02.07.2026 · 18:30', created_at='2026-07-02T16:30:00+00:00',
                source_file='test.xlsx', source_sha256='a'*64, boards=2, players=['Muli','Bruce'],
                matches=[dict(number=1, round=1, wave=1, board='Rot', player1='Bruce', player2='Muli', score1=0, score2=1)])


def test_import_preserves_plan_and_does_not_overwrite_corrections(db_path, tmp_path):
    path=tmp_path/'history.json'
    path.write_text(json.dumps([source_tournament()]))
    with database() as db:
        imported=import_history(db,path)['imported']
        assert len(imported)==1
        match=db.execute('SELECT * FROM matches').fetchone()
        assert (match['player1'],match['player2'],match['score1'],match['score2'])==('Bruce','Muli',0,1)
        db.execute('UPDATE matches SET score1=3,score2=1')
        assert import_history(db,path)=={'imported':[],'skipped':imported}
        assert db.execute('SELECT score1 FROM matches').fetchone()[0]==3
    with TestClient(app) as client:
        t=client.get('/api/tournaments').json()[0]
        assert t['archived_at'] and not t['finished_at']
        assert t['created_at']=='2026-07-02T16:30:00+00:00'
        assert t['winner']=='Bruce'


def test_missing_results_stay_unknown_and_can_be_reopened(db_path, tmp_path):
    source=source_tournament()
    source['matches'][0].update(score1=None,score2=None)
    path=tmp_path/'history.json';path.write_text(json.dumps([source]))
    with database() as db:
        tournament_id=import_history(db,path)['imported'][0]
    with TestClient(app) as client:
        url=f'/api/tournaments/{tournament_id}'
        t=client.get(url).json()
        assert t['played']==0 and t['archived_at']
        assert client.get('/api/tournaments').json()[0]['winner'] is None
        match_id=t['matches'][0]['id']
        score={'score1':3,'score2':1,'revision':0}
        assert client.put(url+f'/matches/{match_id}',json=score).status_code==409
        assert client.post(url+'/reopen').json()['archived_at'] is None
        assert client.put(url+f'/matches/{match_id}',json=score).status_code==200


def test_invalid_batch_writes_nothing(db_path, tmp_path):
    good=source_tournament();bad=copy.deepcopy(good)
    bad['source_sha256']='b'*64
    bad['matches'][0]['score1']=-1
    path=tmp_path/'history.json';path.write_text(json.dumps([good,bad]))
    with database() as db:
        with pytest.raises(ValueError):
            import_history(db,path)
        assert db.execute('SELECT COUNT(*) FROM tournaments').fetchone()[0]==0


def test_opt_in_history_startup_and_deletion_are_repeatable(db_path, monkeypatch, tmp_path):
    history=tmp_path/'history.json'
    history.write_text(json.dumps([source_tournament()]))
    monkeypatch.setenv('TOURNAMENT_HISTORY',str(history))
    with TestClient(app) as client:
        tournaments=client.get('/api/tournaments').json()
        assert len(tournaments)==1
        tournament_id=tournaments[0]['id']
        assert client.delete('/api/tournaments/'+tournament_id).status_code==200
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get('/api/tournaments').json()==[]
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM deleted_imports').fetchone()[0]==1


def test_default_start_preserves_existing_imports_without_seeding(db_path, monkeypatch, tmp_path):
    history=tmp_path/'history.json'
    history.write_text(json.dumps([source_tournament()]))
    with database() as db:
        tournament_id=import_history(db,history)['imported'][0]
    monkeypatch.delenv('TOURNAMENT_HISTORY')
    with TestClient(app) as client:
        assert len(client.get('/api/tournaments').json())==1
        assert client.get('/api/tournaments/'+tournament_id).status_code==200
