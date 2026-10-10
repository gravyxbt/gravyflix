"""Cast recommendations mirror Roku policy; catalog refresh happens only at load."""

def next_item(current, catalog, visited):
    if not current:
        return None
    if current.get('kind') == 'episode':
        season = current.get('season_number', 0)
        if season <= 0:
            return None
        end = current.get('episode_end') or current['episode_number']
        candidates = [e for show in catalog if show['kind'] == 'show' for s in show['seasons'] for e in s['episodes'] if e['show_key'] == current['show_key'] and e['season_number'] > 0 and (e['id'] not in visited) and (e['season_number'] > season or (e['season_number'] == season and e['episode_number'] > end))]
        return min(candidates, key=lambda e: (e['season_number'], e['episode_number'], e['id']), default=None)
    wanted = {g.casefold() for g in current.get('genres', [])}
    scored = [(len(wanted & {g.casefold() for g in item.get('genres', [])}), item) for item in catalog if item['kind'] == 'movie' and item['id'] not in visited and (item['id'] != current['id']) and ((item.get('duration') or 0) >= 600)]
    scored = [pair for pair in scored if pair[0] > 0]
    return min(scored, key=lambda pair: (-pair[0], pair[1]['title'].casefold(), pair[1]['id']), default=(0, None))[1]

def load_catalog(base):
    from .database import connection
    from .models import movie_response
    from .catalog import build_catalog
    from .artwork import decorate
    with connection() as db:
        rows = db.execute('SELECT * FROM movies WHERE available=1').fetchall()
    items = build_catalog([movie_response(row, base).model_dump() for row in rows])
    for item in items:
        decorate(item, base)
        if item['kind'] == 'show':
            for season in item['seasons']:
                for episode in season['episodes']:
                    decorate(episode, base, str(item['id']))
    return items

def find_item(movie_id, catalog):
    for item in catalog:
        if item['kind'] == 'show':
            for s in item['seasons']:
                for e in s['episodes']:
                    if e['id'] == movie_id:
                        return e
        elif item['id'] == movie_id:
            return item
    return None
