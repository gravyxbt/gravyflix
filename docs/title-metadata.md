# Summaries and principal cast

Gravyflix automatically fills title pages in the background alongside artwork.
No new API key is required. It uses the **same verified public TMDB movie/TV match**
as the artwork, reads the synopsis and up to five names from the page's principal
cast section, and caches everything locally. Directors and creators are excluded
from the cast list. These names follow the source's cast ordering; Gravyflix does
not guess which actor is famous.

Existing artwork matches are backfilled automatically after upgrading. New titles
are enriched after the normal library scan and artwork match. This may take a few
minutes on a large library. Roku requires the updated channel package to show the
new layout. Press Options (*) on Roku's home screen to refresh metadata already
imported by the server. Web title pages also show summaries and cast.

## Episodes and DVD ordering

Verified TV season pages supply episode synopses. When the filename includes an
episode title, Gravyflix requires a **unique matching title within that season**.
This allows DVD numbering to differ from broadcast numbering without attaching a
known different episode's plot. With number-only filenames, standard season and
episode numbering is used. For alternate orders, include the correct episode
names in filenames to avoid ambiguity.

Unmatched names, extras and combined multi-episode files use the series synopsis,
clearly labeled **Series overview**. Episode pages label inherited stars **Series
cast**, because a series regular is not guaranteed to appear in every episode.
Unknown metadata gets a friendly fallback; no plots or actors are fabricated.
Adding episodes to an existing season triggers a season metadata refresh. Failed
requests retain existing summaries/artwork and retry after `ARTWORK_RETRY_SECONDS`.

## Cache, sources and troubleshooting

The cache is `data/artwork/index.json`, including `description`, `cast`,
`metadata_version`, and `episode_metadata`. Importer logs use `METADATA`,
`METADATA EPISODES`, and corresponding `ERROR` messages. Source links accompany
API metadata (`metadata_source`) and existing `/artwork-credits` attribution.
Public pages can change or temporarily reject requests. Cached information remains
usable offline and playback never waits for a metadata request.

Use the dashboard's artwork review workflow to fix an incorrect title match. A
successful artwork re-match replaces that title's cached metadata, and its seasons
are imported on the following background pass. Do not manually edit the cache
while an importer is running. Runtime caches and downloaded metadata are private
installation data and must not be committed to a public repository.
