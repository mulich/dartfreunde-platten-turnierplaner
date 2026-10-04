import pytest
from fastapi.testclient import TestClient
from dartabend.main import app, database


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TOURNAMENT_DB',str(tmp_path/'statistics.sqlite3'))
    monkeypatch.setenv('TOURNAMENT_HISTORY','')
    with TestClient(app) as c:
        yield c


def tournament(client,names=('Alice','Bob'),scores=None,finish=True):
    t=client.post('/api/tournaments',json={'name':'Statistiktest','players':list(names)}).json()
    for m in t['matches']:
        result=scores.get(frozenset((m['player1'],m['player2']))) if scores is not None else {names[0]:2,names[1]:1}
        if result is None:
            continue
        response=client.put(f"/api/tournaments/{t['id']}/matches/{m['id']}",json={'score1':result[m['player1']],'score2':result[m['player2']],'revision':0})
        assert response.status_code==200,response.text
    if finish:
        assert client.post(f"/api/tournaments/{t['id']}/finish").status_code==200
    return t


def players(client):
    return {p['name']:p for p in client.get('/api/statistics').json()['players']}


def test_empty_archive_and_active_results_do_not_count(client):
    assert client.get('/api/statistics').json()['players']==[]
    tournament(client,finish=False)
    data=client.get('/api/statistics').json()
    assert data['summary']['tournaments']==0
    assert data['summary']['legs']==0
    assert data['players']==[]


def test_aggregate_matches_legs_rates_and_medals(client):
    tournament(client)
    tournament(client,scores={frozenset(('Alice','Bob')):{'Alice':0,'Bob':3}})
    data=client.get('/api/statistics').json()
    assert data['summary']==dict(tournaments=2,complete_tournaments=2,incomplete_tournaments=0,excluded_aborted=0,players=2,matches=2,missing_results=0,legs=6)
    stats={p['name']:p for p in data['players']}
    a=stats['Alice']
    assert (a['played'],a['wins'],a['losses'],a['legs_for'],a['legs_against'],a['difference'])==(2,1,1,2,4,-2)
    assert a['medal_points']==5
    assert a['win_rate']==50 and a['leg_win_rate']==33.3
    assert (a['gold'],a['silver'],a['bronze'],a['medals'],a['tournaments'])==(1,1,0,2,2)
    assert sum(p['wins'] for p in data['players'])==data['summary']['matches']
    assert sum(p['legs_for'] for p in data['players'])==data['summary']['legs']


def test_incomplete_import_counts_known_results_without_medals(client):
    t=tournament(client,('Alice','Bob','Carol'),scores={frozenset(('Alice','Bob')):{'Alice':2,'Bob':0}},finish=False)
    with database() as db:
        db.execute("UPDATE tournaments SET archived_at=created_at,source_file='import.xlsx' WHERE id=?",(t['id'],))
    data=client.get('/api/statistics').json()
    assert data['summary']['incomplete_tournaments']==1
    assert data['summary']['missing_results']==2
    assert data['summary']['matches']==1
    assert data['summary']['legs']==2
    assert all(p['medals']==p['medal_points']==0 for p in data['players'])
    assert players(client)['Carol']['win_rate'] is None
    assert players(client)['Carol']['leg_win_rate'] is None
    assert players(client)['Carol']['played']==0


def test_aborted_results_are_excluded(client):
    t=tournament(client,finish=False)
    assert client.post(f"/api/tournaments/{t['id']}/abort").status_code==200
    data=client.get('/api/statistics').json()
    assert data['summary']['excluded_aborted']==1
    assert data['summary']['matches']==0 and data['players']==[]


def test_shared_places_award_shared_medals(client):
    scores={frozenset(('Alice','Bob')):{'Alice':2,'Bob':1},frozenset(('Bob','Carol')):{'Bob':2,'Carol':1},frozenset(('Carol','Alice')):{'Carol':2,'Alice':1}}
    tournament(client,('Alice','Bob','Carol'),scores)
    stats=players(client)
    assert all(p['gold']==1 and p['silver']==p['bronze']==0 for p in stats.values())
    assert all(p['medals']==1 and p['medal_points']==3 for p in stats.values())


def test_renames_and_hidden_profiles_preserve_cumulative_results(client):
    tournament(client,('Muli','Bob'))
    profile=next(p for p in client.get('/api/player-profiles').json() if p['name']=='Muli')
    renamed=client.put(f"/api/player-profiles/{profile['id']}",json={**profile,'name':'Michael'}).json()
    tournament(client,('Michael','Bob'))
    assert client.delete(f"/api/player-profiles/{profile['id']}?revision={renamed['revision']}").status_code==200
    stats=players(client)
    assert 'Muli' not in stats
    assert stats['Michael']['tournaments']==2
    assert stats['Michael']['gold']==2 and stats['Michael']['legs_for']==4


def test_reopen_correction_and_delete_recalculate_statistics(client):
    t=tournament(client)
    path=f"/api/tournaments/{t['id']}"
    assert client.post(path+'/reopen').status_code==200
    assert players(client)=={}
    m=t['matches'][0]
    result={'Alice':0,'Bob':4}
    assert client.put(path+f"/matches/{m['id']}",json={'score1':result[m['player1']],'score2':result[m['player2']],'revision':1}).status_code==200
    assert client.post(path+'/finish').status_code==200
    assert players(client)['Bob']['gold']==1
    assert players(client)['Alice']['gold']==0
    assert client.delete(path).status_code==200
    assert client.get('/api/statistics').json()['summary']['tournaments']==0
    assert players(client)=={}


def test_medal_points_rank_above_medal_count(client):
    # One gold (3 points) ranks above two bronze medals (2 points).
    for names in [('Alice','Bob','Carol'),('Dave','Bob','Carol')]:
        scores={frozenset((a,b)):{a:2,b:0} for i,a in enumerate(names) for b in names[i+1:]}
        tournament(client,names,scores)
    data=client.get('/api/statistics').json()
    stats={p['name']:p for p in data['players']}
    assert stats['Alice']['medals']==1 and stats['Alice']['medal_points']==3
    assert stats['Bob']['medals']==2 and stats['Bob']['medal_points']==4
    assert stats['Carol']['medals']==2 and stats['Carol']['medal_points']==2
    assert [p['name'] for p in data['players']]==['Bob','Alice','Dave','Carol']
