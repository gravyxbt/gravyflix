"""Presentation-only TV grouping; media IDs and playback URLs stay unchanged."""
import hashlib
import json
from functools import lru_cache
from . import config
import re
from pathlib import Path
from .titles import QUALITY, clean_release

EPISODE = re.compile(r"(?i)(?<![a-z0-9])(?:s(?P<s>\d{1,2})[ ._-]*e(?P<e>\d{1,3})|(?P<xs>\d{1,2})x(?P<xe>\d{1,3}))(?!\d)")

def clean(text):
    return re.sub(r"\s+", " ", text.replace(".", " ").replace("_", " ")).strip(" -[]()")

def show_key(title):
    return re.sub(r"[^\w]+", " ", title.casefold().replace("&", " and ").replace("'", "").replace("’", "")).strip()

@lru_cache(maxsize=1)
def show_aliases():
    path = config.ROOT / "config/show-aliases.json"
    if not path.exists():
        return {}
    aliases = json.loads(path.read_text())
    if not isinstance(aliases, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip() for k, v in aliases.items()):
        raise ValueError("config/show-aliases.json must map show names to nonempty canonical titles")
    return {show_key(k): v.strip() for k, v in aliases.items()}

def episode_identity(filename, folders=()):
    if filename.startswith("._"):
        return None
    stem = Path(filename).stem
    match = EPISODE.search(stem)
    if not match:
        # A correctly named per-episode folder can recover an unlabelled/typo filename.
        # Require a matching explicit Season N ancestor, not just a nearby show folder.
        if len(folders) >= 2:
            season_parent = re.fullmatch(r"(?i)season[ ._-]*(\d{1,2})", folders[-2])
            if season_parent and EPISODE.search(folders[-1]):
                parent = episode_identity(folders[-1] + ".mkv")
                if parent and parent['season_number'] == int(season_parent[1]):
                    return parent
        chapter = re.fullmatch(r"(?i)(?:chapter|episode|ep)[ ._-]*(\d{1,3})", stem)
        season_folder = re.fullmatch(r"(?i)season[ ._-]*(\d{1,2})", folders[-1]) if len(folders) >= 2 else None
        if chapter and season_folder:
            # Only explicit Show/Season N/Chapter N paths; never infer season numbers.
            return episode_identity(f"{folders[-2]}.S{season_folder[1]}E{chapter[1]}.avi")
        return None
    title = clean(stem[:match.start()])
    if not title:
        return None  # Do not guess which show an unlabelled file belongs to.
    season = int(match['s'] or match['xs'])
    episode = int(match['e'] or match['xe'])
    tail = stem[match.end():]
    combined = re.match(r"(?i)^(?:-?e|-)(\d{1,3})(?!\d)", tail)
    end = episode
    if combined:
        end = max(episode, int(combined[1]))
        tail = tail[combined.end():]
    subtitle = clean(clean_release(tail))
    label = f"Episode {episode}" if end == episode else f"Episodes {episode}–{end}"
    if subtitle:
        label += " · " + subtitle
    title = show_aliases().get(show_key(title), title)
    normalized = show_key(title)
    return dict(show_title=title, show_key=normalized, season_number=season,
                episode_number=episode, episode_end=end, episode_title=label)

@lru_cache(maxsize=1)
def multipart_series():
    path = config.ROOT / "config/library-rules.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    names = data.get("multipart_series", [])
    if not isinstance(names, list) or any(not isinstance(n, str) or not n.strip() for n in names):
        raise ValueError("multipart_series must contain nonempty series names")
    return {show_key(n): n.strip() for n in names}

def grouping_hint(filename, folders=()):
    if filename.startswith('._'):
        return None
    if len(folders) >= 2 and folders[-1].casefold() in {'extras', 'bonus', 'bonus features', 'featurettes'}:
        title = show_aliases().get(show_key(clean(folders[-2])), clean(folders[-2]))
        return dict(type='extra', show_title=title, show_key=show_key(title), label=clean(Path(filename).stem))
    match = re.match(r"(?i)^(.+?)[ ._-]+(part|disc|disk)[ ._-]*(\d{1,3})(?!\d)(.*)$", Path(filename).stem)
    if not match:
        return None
    title = clean(match[1])
    key = show_key(title)
    return dict(type='multipart', show_title=title, show_key=key, number=int(match[3]),
                label=('Part' if match[2].casefold() == 'part' else 'Disc') + ' ' + str(int(match[3])),
                section='Parts' if match[2].casefold() == 'part' else 'Discs',
                matching_folder=bool(folders and show_key(clean(folders[-1])) == key))

def natural_key(text):
    return tuple((0, int(t)) if t.isdigit() else (1, t.casefold()) for t in re.split(r'(\d+)', text))

def build_catalog(movies):
    movies = [m for m in movies if not m['filename'].startswith('._')]
    identities = {m['id']: m.get('series_info') or episode_identity(m['filename']) for m in movies}
    hints = {m['id']: m.get('grouping_hint') or grouping_hint(m['filename']) for m in movies}
    known = {i['show_key'] for i in identities.values() if i}
    approved = multipart_series()
    evidence = {}
    for hint in hints.values():
        if hint and hint['type'] == 'multipart' and hint['matching_folder']:
            evidence.setdefault(hint['show_key'], set()).add(hint['number'])
    automatic = {key for key, numbers in evidence.items() if len(numbers) >= 2}
    titles, shows = [], {}
    for movie in movies:
        identity = identities[movie['id']]
        hint = hints[movie['id']]
        if not identity and hint:
            key = hint['show_key']
            if hint['type'] == 'extra' and key in known:
                identity = dict(show_key=key, show_title=hint['show_title'], season_number=-1,
                                episode_number=0, episode_end=0, episode_title=hint['label'], section_title='Extras')
            elif hint['type'] == 'multipart' and (key in approved or key in automatic):
                identity = dict(show_key=key, show_title=approved.get(key, hint['show_title']), season_number=1,
                                episode_number=hint['number'], episode_end=hint['number'],
                                episode_title=hint['label'], section_title=hint['section'])
        if not identity:
            titles.append({**movie, 'kind': 'movie'})
            continue
        key = identity['show_key']
        show = shows.setdefault(key, dict(
            id='show-' + hashlib.sha256(key.encode()).hexdigest(), kind='show',
            title=identity['show_title'], date_added=movie['date_added'],
            poster_url=movie.get('poster_url'), seasons={}, episode_count=0, extra_count=0))
        show['date_added'] = max(show['date_added'], movie['date_added'])
        season = show['seasons'].setdefault(identity['season_number'], [])
        season.append({**movie, **identity, 'kind':'episode', 'title':identity['episode_title']})
        show['extra_count' if identity['season_number'] == -1 else 'episode_count'] += 1
    for show in shows.values():
        show['seasons'] = [dict(number=number,
                               title=episodes[0].get('section_title') or ('Specials' if number == 0 else f'Season {number}'),
                               episodes=sorted(episodes, key=lambda e:(e['episode_number'],e['episode_end'],natural_key(e['filename']),e['id'])))
                           for number, episodes in sorted(show['seasons'].items(), key=lambda pair:(pair[0] == -1, pair[0]))]
        show['season_count'] = sum(s['number'] >= 0 for s in show['seasons'])
        show['description'] = 'Choose a season or collection to browse.'
        titles.append(show)
    return sorted(titles, key=lambda item:(item['title'].casefold(),str(item['id'])))
