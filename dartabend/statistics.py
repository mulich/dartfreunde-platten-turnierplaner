"""Aggregate recorded archive results; award medals only for complete tournaments."""
from collections import defaultdict


def aggregate(db, standings):
    # Read one database snapshot; profiles and aliases survive picker removals.
    db.execute('BEGIN')
    archived = [dict(r) for r in db.execute(
        'SELECT id,aborted_at FROM tournaments WHERE archived_at IS NOT NULL OR finished_at IS NOT NULL')]
    eligible = {t['id'] for t in archived if not t['aborted_at']}
    names, matches = defaultdict(list), defaultdict(list)
    for row in db.execute('SELECT tournament_id,name FROM players ORDER BY position,id'):
        if row['tournament_id'] in eligible:
            names[row['tournament_id']].append(row['name'])
    for row in db.execute('SELECT * FROM matches ORDER BY number,id'):
        if row['tournament_id'] in eligible:
            matches[row['tournament_id']].append(dict(row))
    aliases = {r['name_key']:dict(r) for r in db.execute(
        'SELECT a.name_key,p.id,p.name FROM profile_aliases a JOIN player_profiles p ON p.id=a.profile_id')}
    players = {}
    complete = recorded = missing = 0
    for tournament_id in eligible:
        games = matches[tournament_id]
        played = sum(m['score1'] is not None and m['score2'] is not None for m in games)
        finished = bool(games) and played == len(games)
        complete += int(finished)
        recorded += played
        missing += len(games) - played
        participants = set()
        for entry in standings(names[tournament_id], games):
            profile = aliases.get(entry['name'].casefold())
            key = ('profile',profile['id']) if profile else ('name',entry['name'].casefold())
            if key not in players:
                players[key] = dict(name=profile['name'] if profile else entry['name'],
                    tournaments=0, complete_tournaments=0, played=0, wins=0, losses=0,
                    legs_for=0, legs_against=0, gold=0, silver=0, bronze=0)
            player = players[key]
            if key not in participants:
                player['tournaments'] += 1
                player['complete_tournaments'] += int(finished)
                participants.add(key)
            for field in ('played','wins','losses','legs_for','legs_against'):
                player[field] += entry[field]
            if finished and entry['rank'] <= 3:
                player[('gold','silver','bronze')[entry['rank']-1]] += 1
    for player in players.values():
        player['medals'] = player['gold'] + player['silver'] + player['bronze']
        player['difference'] = player['legs_for'] - player['legs_against']
        player['win_rate'] = round(100 * player['wins'] / player['played'],1) if player['played'] else None
        legs = player['legs_for'] + player['legs_against']
        player['leg_win_rate'] = round(100 * player['legs_for'] / legs,1) if legs else None
    result = sorted(players.values(),key=lambda p:(-p['medals'],-p['gold'],-p['silver'],-p['bronze'],p['name'].casefold()))
    return dict(summary=dict(tournaments=len(eligible),complete_tournaments=complete,
        incomplete_tournaments=len(eligible)-complete,excluded_aborted=sum(bool(t['aborted_at']) for t in archived),
        players=len(result),matches=recorded,missing_results=missing,legs=sum(p['legs_for'] for p in result)),players=result)
