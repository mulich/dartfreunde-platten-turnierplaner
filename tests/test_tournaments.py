from itertools import combinations

import pytest
from fastapi.testclient import TestClient

from dartabend.main import app, standings, database
from dartabend.scheduler import spielplan_erstellen


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TOURNAMENT_HISTORY', '')
    monkeypatch.setenv('TOURNAMENT_DB', str(tmp_path / 'tournaments.sqlite3'))
    with TestClient(app) as client:
        yield client


def create(client, players=None):
    response = client.post('/api/tournaments', json={'name':'Vereinsabend','players':players or ['Julia','Michael','Thomas'], 'boards':2})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize('count', [2,3,4,5,6,7,8,13,64])
@pytest.mark.parametrize('boards', [2,3])
def test_complete_schedule_without_collisions(count, boards):
    players = [f'Spieler {i}' for i in range(count)]
    board_names = ['Rot','Blau','Schwarz'][:boards]
    matches, _, _ = spielplan_erstellen(players, board_names)
    assert len(matches) == count*(count-1)//2
    assert {tuple(sorted([m['spieler1'],m['spieler2']])) for m in matches} == set(combinations(sorted(players), 2))
    for wave in {m['durchgang'] for m in matches}:
        group = [m for m in matches if m['durchgang'] == wave]
        involved = [p for m in group for p in (m['spieler1'],m['spieler2'])]
        assert len(involved) == len(set(involved))
        assert len({m['scheibe'] for m in group}) == len(group) <= boards


def test_full_lifecycle_and_persistence(client):
    t=create(client)
    match=t['matches'][0]
    url=f"/api/tournaments/{t['id']}"
    assert client.post(url+'/finish').status_code == 409
    for m in t['matches']:
        response=client.put(url+f"/matches/{m['id']}", json={'score1':3,'score2':1,'revision':0})
        assert response.status_code == 200
    t=response.json()
    assert t['played']==t['total']==3
    assert sum(p['points'] for p in t['standings']) == 6
    assert sum(p['legs_for'] for p in t['standings']) == 12
    assert client.post(url+'/finish').status_code == 200
    assert client.put(url+f"/matches/{match['id']}",json={'score1':1,'score2':3,'revision':1}).status_code == 409
    assert client.get('/api/tournaments').json()[0]['winner']
    # Recreate the app lifespan against the same on-disk database.
    with TestClient(app) as restarted:
        assert restarted.get(url).json()['played'] == 3
        assert restarted.get(url).json()['finished_at']
        assert restarted.post(url+'/reopen').status_code == 200
        assert restarted.put(url+f"/matches/{match['id']}",json={'score1':None,'score2':None,'revision':1}).status_code == 200
        assert restarted.get(url).json()['played'] == 2


@pytest.mark.parametrize('body',[{'score1':2,'score2':2,'revision':0},{'score1':-1,'score2':2,'revision':0}, {'score1':1,'revision':0},{'score1':1.5,'score2':2,'revision':0},{'score1':True,'score2':2,'revision':0}])
def test_invalid_results(client,body):
    t=create(client)
    assert client.put(f"/api/tournaments/{t['id']}/matches/{t['matches'][0]['id']}",json=body).status_code == 422
    assert client.get(f"/api/tournaments/{t['id']}").json()['played']==0


def test_prevent_overwriting_another_result(client):
    t=create(client)
    url=f"/api/tournaments/{t['id']}/matches/{t['matches'][0]['id']}"
    body={'score1':0,'score2':3,'revision':0}
    assert client.put(url,json=body).status_code==200
    assert client.put(url,json=body).status_code==409


@pytest.mark.parametrize('players', [['Julia',' julia '],['A',''],['A','PAUSE'],['A'],['A'*61,'B']])
def test_invalid_players(client,players):
    assert client.post('/api/tournaments',json={'name':'Test','players':players,'boards':2}).status_code==422
    assert client.get('/api/tournaments').json()==[]


def test_match_isolation(client):
    one=create(client);two=create(client)
    assert client.put(f"/api/tournaments/{one['id']}/matches/{two['matches'][0]['id']}",json={'score1':3,'score2':1,'revision':0}).status_code==404


def test_shared_rank_and_sorting():
    matches=[{'player1':'A','player2':'B','score1':3,'score2':1}, {'player1':'B','player2':'C','score1':3,'score2':1}, {'player1':'C','player2':'A','score1':3,'score2':1}]
    result=standings(['A','B','C'],matches)
    assert [p['rank'] for p in result]==[1,1,1]
    assert [p['points'] for p in result]==[2,2,2]
    # Won legs have priority over leg difference, as in the original script.
    result=standings(['A','B','C','D'],[{'player1':'A','player2':'B','score1':5,'score2':4},{'player1':'C','player2':'D','score1':3,'score2':0}])
    assert result[0]['name']=='A'


def test_health_and_frontend(client):
    assert client.get('/health').json()=={'status':'ok'}
    assert 'Dartfreunde Platten' in client.get('/').text
    assert client.get('/static/app.js').status_code==200
    assert client.get('/api/tournaments/nonexistent').status_code==404


def test_default_player_shortcuts_do_not_create_tournaments(client):
    assert client.get('/api/players').json() == ['Muli', 'Bruce', 'Ly', 'Schlatho', 'Michel', 'Rote', 'Manuel', 'Swobi']
    assert client.get('/api/tournaments').json() == []


def test_shortcuts_use_saved_history_without_case_duplicates(client):
    create(client, ['muli', 'Zoe', 'Neuer Spieler'])
    create(client, ['zoe', 'bruce'])
    names = client.get('/api/players').json()
    assert names.count('Muli') == 1
    assert names.count('Bruce') == 1
    assert 'muli' not in names and 'bruce' not in names and 'zoe' not in names
    assert names[-2:] == ['Neuer Spieler', 'Zoe']
    with TestClient(app) as restarted:
        assert restarted.get('/api/players').json() == names


def test_delete_archive_removes_children_and_survives_restart(client):
    target=create(client, ['Unique Player', 'Other Player'])
    other=create(client)
    url=f"/api/tournaments/{target['id']}"
    match=target['matches'][0]
    client.put(url+f"/matches/{match['id']}",json={'score1':3,'score2':1,'revision':0})
    assert client.post(url+'/finish').status_code==200
    assert client.delete(url).json()=={'deleted':target['id']}
    assert client.get(url).status_code==404
    assert client.delete(url).status_code==404
    assert client.get('/api/tournaments').json()[0]['id']==other['id']
    assert 'Unique Player' not in client.get('/api/players').json()
    assert 'Muli' in client.get('/api/players').json()
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM matches WHERE tournament_id=?',(target['id'],)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM players WHERE tournament_id=?',(target['id'],)).fetchone()[0]==0
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    with TestClient(app) as restarted:
        assert restarted.get(url).status_code==404
        assert restarted.get(f"/api/tournaments/{other['id']}").status_code==200


def test_cannot_delete_active_or_reopened_tournament(client):
    t=create(client,['A','B'])
    url=f"/api/tournaments/{t['id']}"
    assert client.delete(url).status_code==409
    match=t['matches'][0]
    client.put(url+f"/matches/{match['id']}",json={'score1':3,'score2':1,'revision':0})
    client.post(url+'/finish')
    client.post(url+'/reopen')
    assert client.delete(url).status_code==409
    assert client.get(url).json()['played']==1


def test_new_installation_is_empty_without_history_setting(client, monkeypatch):
    monkeypatch.delenv('TOURNAMENT_HISTORY')
    with TestClient(app) as restarted:
        assert restarted.get('/api/tournaments').json()==[]
