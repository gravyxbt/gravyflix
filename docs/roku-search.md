# Search on Roku

Select **Search** in the top navigation. Enter a movie/show title, actor name or
genre with the on-screen keyboard. Results update as you type, using the library
already loaded by the channel; keystrokes do not call the server.

- Press **Play/Pause** to move from the keyboard to the results immediately.
  Moving right out of the keyboard or choosing **Browse results** also works.
- Navigate the artwork grid with the directional buttons. **OK** opens the existing
  movie title page or series season/episode browser.
- **Back** from a title returns to the same search query and focused result.
  Back from the results returns to the keyboard; Back from the keyboard leaves
  Search. Select Home, Movies or Shows in the navigation to leave Search directly.
- **Clear** or the keyboard's clear key resets the query.

Matching ignores case, Latin accents and common punctuation. Multiple words must
all match somewhere in the title, principal cast or genres. Exact title matches
appear first, followed by title prefixes, other title matches and metadata matches.
Individual episodes are grouped under their series rather than filling results
with dozens of episode cards. Search uses only the cast/genres currently cached
for each title; unknown metadata still allows title searches.

Empty queries show a typing prompt. Queries with no matches explain what happened.
The query is limited to 75 characters and the grid to the first 150 matches; the
count tells you when to narrow the query. Result cards are virtualized by Roku's
MarkupGrid and use the same bounded artwork and focus styling as the home screen.

A short debounce prevents rebuilding the grid on every rapid text change. New
library responses build the normalized index once; search does not walk episode
trees per keystroke. Background progress updates patch existing result nodes without
changing the query, selected position or emitting title-selection commands.

The native keyboard is measured after its graphics initialize and fitted inside a
reserved area. Browse results and Clear occupy a separate action row below it,
with a gap between that row and the keyboard's own space/delete keys.

## Keyboard compatibility and device testing

The channel uses Roku's [DynamicMiniKeyboard](https://developer.roku.com/dev/docs/dynamic-mini-keyboard)
when available, with a native MiniKeyboard fallback for older devices. Keyboard
Options behavior is left to Roku. Voice entry may be available on supported
keyboards/remotes; it is not required for searching.

Automated BrightScript tests cover matching, sorting, result limits, selection
commands, Back navigation and background updates. Test the native keyboard's layout,
edge navigation and card focus animation on the physical Roku after sideloading
an updated package. The current server and playback endpoints remain unchanged.
