# Organizing your media

This guide covers movie titles, TV seasons and episodes, specials, extras, multipart
collections, and corrections. No metadata account is required for browsing or
filename-based grouping.

## Choose a library folder

The default library is `media/Movies/` inside the project. Despite its name, this
folder holds both movies and shows. The scanner searches all subfolders.
To use another location, set `MOVIES_DIR` in `.env` and restart the backend.
Relative paths resolve from the project directory.

Supported extensions are `.mp4`, `.mkv`, `.m4v`, `.mov`, and `.avi`, regardless
of capitalization. Being detected does not guarantee direct playback: codecs
matter, and Roku may prepare a compatible copy for MKV or AVI.

## Recommended layout

```text
media/Movies/
├── Arrival (2016).mkv
├── Iron Man (2008).mp4
└── Example Show/
    ├── Season 1/
    │   ├── Example Show.S01E01 - Pilot.mp4
    │   └── Example Show.S01E02 - The Return.mkv
    ├── Season 2/
    │   └── Example Show.S02E01.mp4
    ├── Specials/
    │   └── Example Show.S00E01 - Holiday Special.mp4
    └── Extras/
        └── Making Of.mp4
```

Choose names before the first scan when possible. Existing, correctly identified
files do not need reorganizing to match this layout.

## Movies

Prefer `Movie Title (Year).extension`, for example `Arrival (2016).mkv`.
A movie can be directly in the library or in its own folder; its display title
comes from the filename, not the folder.

Periods and underscores become spaces. A parenthesized or bracketed four-digit
year beginning with 19 or 20 is recognized; otherwise the scanner looks for a
non-leading year. Prefer parentheses to distinguish release years from numbers
that belong to a title.

The scanner removes technical suffixes such as `1080p`, `BluRay`, `WEB-DL`,
`DVDRip`, `HDTV`, `XviD`, and `x264`. It also removes bracketed website prefixes
and collection prefixes of the form `1-1 ` before an alphabetic title.
Meaningful leading numbers and sequel numbers remain, for example
`1917 (2019).mp4`, `12 Angry Men (1957).mkv`, and `Iron Man 2.mp4`.

## TV shows

Prefer `Show Name.S01E02 - Episode Title.extension`. The episode title is optional;
without it, the app displays `Episode 2`. Use the same show name for every episode.

| Filename | Recognized season and episode |
| --- | --- |
| `Example Show.S01E02.mp4` | Season 1, episode 2 |
| `Example Show S01-E02 - The Return.mp4` | Season 1, episode 2 |
| `Example Show 1x02 The Return.mkv` | Season 1, episode 2 |

For these names, the filename supplies the show, season and episode. A season
folder is helpful for organization but does not override a valid filename token.
Seasons and episodes sort numerically; only files actually present are listed.
The Roku shows one show card, then season and episode lists. The Android casting page also groups shows into seasons and episode lists.

Show names normalize case, spaces, punctuation, and `&`/`and`. Keep any remake year
consistent: `Example Show (2005)` and `Example Show (2020)` remain separate shows.
There is no fuzzy matching or automatic episode identification from video contents.

### Folder-based alternatives

Short filenames are supported inside an explicit show and season path:

```text
Example Show/Season 1/Chapter 1.avi
Example Show/Season 1/Episode 2.avi
Example Show/Season 1/Ep 3.mp4
```

A bare `S01E01.mp4` is not a recommended naming pattern: a show name is required
for filename-based identification. Use the full recommended filename or the
explicit `Chapter N`, `Episode N`, or `Ep N` folder pattern.

A correctly named immediate episode folder can recover an unrecognized filename:
`Example Show/Season 1/Example Show.S01E02/unlabelled.avi`. This fallback requires
the episode folder's season to agree with the enclosing `Season N` folder.

### Specials and combined episodes

Use `S00` for specials, such as `Example Show.S00E01 - Holiday Special.mp4`.
The `Specials` folder name alone does not identify an unnumbered file.

A combined file named `Example Show.S01E01E02.mp4`,
`Example Show.S01E01-E02.mp4`, or `Example Show.S01E01-02.mp4` is one selectable
item labelled `Episodes 1–2`; it is not split into separate videos.
Duplicate encodes of an episode remain separate selectable files.

## Extras

Put descriptive filenames directly inside one of these folders:

```text
Example Show/Extras/Making Of.mp4
Example Show/Bonus/Deleted Scenes.mp4
Example Show/Bonus Features/Interview.mp4
Example Show/Featurettes/Behind The Scenes.mp4
```

The parent show name must match an identified TV show. The Extras section sorts
after seasons and does not inflate episode counts. Unknown parent shows are not
guessed; their extras remain standalone entries. Extras retain descriptive
filename-based labels. Use aliases below if the parent name differs from the
name in the episodes. Keep numbered `S00` specials distinct from unnumbered extras.

## Multipart collections

A matching collection folder containing at least two distinct numbered parts
or discs is automatically grouped:

```text
Example Documentary/
├── Example Documentary.Part1.avi
└── Example Documentary.Part2.avi
```

`Part`, `Disc`, and `Disk` are supported. The folder name must match the title
before that token. Loose parts or isolated files are not automatically treated
as a series. Movie sequel numbers are not multipart evidence.

For a deliberate collection that lacks a matching folder, add its shared title
to `config/library-rules.json`:

```json
{
  "multipart_series": ["Example Documentary"]
}
```

Merge this into existing rules rather than replacing unrelated entries. Restart
the backend and refresh the Roku after rule edits. Do not use a multipart rule
for ordinary numbered TV episodes; use season/episode naming instead.

## Correct names without renaming videos

### Combine show-name variants

Edit `config/show-aliases.json` to map the show-name portion before the episode
token, or the extras parent folder name, to one canonical name:

```json
{
  "Example Show US": "Example Show (2020)",
  "releasegroup-Example Show": "Example Show (2020)"
}
```

Alias keys use case/punctuation and `&`/`and` normalization. Values are the display
names. Restart the backend, then reopen or refresh Roku; no rescan or package
installation is required. Changing a canonical name can change its show ID;
individual video IDs remain unchanged.

### Correct a movie's display title

Edit `config/title-overrides.json`, using the exact filename including extension:

```json
{
  "1-1 Iron Man.avi": "Iron Man",
  "Unclear.Movie.Name.mp4": "Correct Movie Title"
}
```

Merge entries into the existing JSON object. Filename matching is case-sensitive;
an override applies to every file with that exact basename. Rescan and refresh
the app. This changes the displayed file title without moving the video or
changing its ID. It does not override show grouping or episode labels: use show
aliases or the supported episode naming patterns for those.

## Add files and refresh

From the project directory:

```bash
./scripts/scan.sh
# Alternatively, while the backend is running:
curl -X POST http://localhost:8080/api/library/scan
```

The backend also scans on startup. Finish copying a video before scanning it;
a temporary `.partial` extension keeps unfinished copies out of the scan.
Then open the Roku app or press Options (*) to refresh. In Roku build 00014
and later, Options (*) scans for new files before fetching the catalog; older
versions only reload the saved catalog. Large imports may take longer to scan,
so the CLI remains useful. After installing this refresh improvement once,
adding media or changing naming rules requires no new Roku ZIP.

IDs follow absolute file paths. Renaming or moving an existing file creates a
new media ID and can lose its associations with ID-based artwork or prepared
playback caches. Prefer display-title overrides and aliases for existing files.
Missing files are hidden, while their database rows remain for restoration at
the original path. Symlinks pointing outside the library are excluded.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Episodes appear as separate movies | Include a show name plus `S01E02`, or use the explicit folder-based pattern. |
| One show appears several times | Make show names consistent or add aliases, then restart and refresh. |
| Extras appear separately | Use a recognized extras folder whose parent matches an identified TV show. |
| A file is missing | Check its extension and location, finish copying, rescan, then refresh. |
| Titles still contain release text | Add an exact filename override; arbitrary prefixes are not guessed. |
| Two versions of an episode appear | Duplicate encodes are retained; there is no automatic version selection. |
| Correct titles have placeholder artwork | Automatic matching needs a unique title/year match. Check the matching report and README override workflow. |

macOS `._` resource-fork files are hidden from the grouped Roku catalog.
New library files are scanned every five minutes by default, with public-source artwork
matching in the background. See [automatic artwork](../README.md#manage-and-organize)
for settings, review reports and manual corrections. Refresh Roku after downloads finish.

## Genre categories

Recognized public artwork matches also receive automatic genre categories. Movie
and show names/years determine the public title match; genre folders or words in
filenames do not determine categories. A title can appear in several genre rows.
Shows stay grouped and their episodes/extras inherit the parent genres. Unmatched
or genre-less titles remain under Uncategorized. Use `config/genre-overrides.json`
for corrections, keyed by the movie or show ID from the browse API, then refresh
Roku. See [automatic genre categories](../README.md#features)
for examples and review behavior.


## Subtitle files

Place text subtitles beside the matching video, using its exact basename:

```text
Movies/Film (2024).mkv
Movies/Film (2024).en.srt
Movies/Film (2024).en.sdh.srt
Movies/Film (2024).en.forced.srt
```

Use the same convention for episodes. `en` means English; `sdh` includes sound
descriptions; `forced` covers only selected dialogue, not the full movie. UTF-8
SRT is recommended. A bare matching `.srt` is supported with unknown language.

The background subtitle worker discovers sidecars and extracts embedded text
tracks, preserving originals. With an OpenSubtitles API key it also queues
missing English captions, capped at five download-link attempts per UTC day by
default. Strong matches are downloaded; uncertain matches stay flagged for review.
Subtitle assets become available when you next start the title. Roku build 00015
adds playback caption controls through Options (*); adding future subtitle files
does not require reinstalling the app. See the README subtitle section for quota,
matching, timing and unsupported bitmap-track details.
