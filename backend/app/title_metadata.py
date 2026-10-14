"""Bounded synopsis/cast metadata from verified public TMDB pages.

Network access stays in the artwork worker. API and client browsing use its cache.
"""
import html
import re
from bs4 import BeautifulSoup

METADATA_VERSION = 1
MAX_CAST = 5
MAX_DESCRIPTION = 1200
PUBLIC_TITLE = re.compile(r'https://www\.themoviedb\.org/(movie|tv)/(\d+)(?:-[^/?#]+)?/?$')


def plain(value, limit=MAX_DESCRIPTION):
    if not isinstance(value, str):
        return ''
    if '<' in value:
        soup = BeautifulSoup(value, 'html.parser')
        for node in soup(['script', 'style']):
            node.decompose()
        value = soup.get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()[:limit]


def title_fields(soup):
    overview = soup.select_one('.overview')
    description = plain(str(overview)) if overview else ''
    if description.lower() in {'we don\'t have an overview translated in english. help us expand our database by adding one.', 'no overview found.'}:
        description = ''
    names = []
    # Cast cards only: .people also contains directors and creators (.profile).
    for link in soup.select('ol.people li.card > p:not(.character) a[href^="/person/"]'):
        name = plain(link.get_text(' ', strip=True), 100)
        if name and name not in names:
            names.append(name)
        if len(names) == MAX_CAST:
            break
    return {'description': description, 'cast': names, 'metadata_version': METADATA_VERSION}


def season_fields(soup, source_url, season):
    match = PUBLIC_TITLE.fullmatch(source_url)
    if not match or match[1] != 'tv':
        raise ValueError('Season metadata needs a verified TV source')
    prefix = rf'/tv/{match[2]}(?:-[^/]+)?/season/{season}/episode/(\d+)'
    episodes = {}
    for card in soup.select('.episode'):
        link = card.select_one('.episode_title h3 a[href]')
        if not link:
            continue
        identity = re.fullmatch(prefix, link['href'])
        if not identity or link.get('data-season-number') != str(season):
            raise ValueError('Season page episode belongs to a different show or season')
        number = int(identity[1])
        if link.get('data-episode-number') != str(number) or str(number) in episodes:
            raise ValueError('Season page has inconsistent episode numbering')
        overview = card.select_one('.overview')
        # Exclude the "Read More" link and expansion UI.
        paragraphs = overview.select('p') if overview else []
        description = plain(' '.join(str(p) for p in paragraphs))
        episodes[str(number)] = {'title': plain(link.get_text(' ', strip=True), 200),
                                 'description': description,
                                 'source_url': 'https://www.themoviedb.org' + link['href']}
    if not episodes:
        raise ValueError('No identifiable episodes on season page')
    return episodes


def _normal(value):
    import unicodedata
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower().replace('&', 'and'))


def episode_fields(entry, identity):
    """Prefer unique title matches over numbers for differently numbered DVD rips."""
    season = identity.get('season_number', -1)
    number = identity.get('episode_number', 0)
    end = identity.get('episode_end', number)
    if season < 0 or number <= 0 or end != number:
        return None  # Extras and combined files require explicit metadata, not guesses.
    seasons = entry.get('episode_metadata', {})
    if not isinstance(seasons, dict):
        return None
    episodes = seasons.get(str(season), {})
    if not isinstance(episodes, dict):
        return None
    label = identity.get('episode_title', '')
    subtitle = label.split(' · ', 1)[1] if ' · ' in label else ''
    if subtitle:
        matches = [e for e in episodes.values() if isinstance(e, dict) and _normal(e.get('title', '')) == _normal(subtitle)]
        return matches[0] if len(matches) == 1 else None
    found = episodes.get(str(number))
    return found if isinstance(found, dict) else None


def decorate_metadata(item, entry):
    """Never treat a series synopsis as an episode synopsis without labeling it."""
    if not isinstance(entry, dict):
        return item
    names = entry.get('cast', [])
    item['cast'] = list(dict.fromkeys(plain(n, 100) for n in names if isinstance(n, str) and n.strip()))[:MAX_CAST] if isinstance(names, list) else []
    source = entry.get('source_url', '')
    if not isinstance(source, str):
        source = ''
    series = bool(PUBLIC_TITLE.fullmatch(source) and '/tv/' in source)
    item['cast_scope'] = 'series' if series else 'title'
    description = plain(entry.get('description'))
    identity = item.get('series_info') or item.get('grouping_hint')
    if item.get('kind') == 'episode':
        identity = item
    episode = episode_fields(entry, identity) if identity else None
    if episode and plain(episode.get('description')):
        description = plain(episode['description'])
        item['description_scope'] = 'episode'
        item['metadata_source'] = episode['source_url']
    elif description:
        item['description_scope'] = 'series' if series else 'movie'
        item['metadata_source'] = source
    if description:
        item['description'] = description
    return item
