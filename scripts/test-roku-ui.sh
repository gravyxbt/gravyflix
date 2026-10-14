#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH"
./scripts/check-roku.sh
python3 scripts/validate-roku-ui.py
output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeData.brs tests/roku/home-data.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Home data adapter"* && "$output" != *"FAIL:"* ]]
output="$(./node_modules/.bin/brs --root tests/roku roku/components/MediaVideo.brs roku/components/IntroControls.brs tests/roku/video-controls.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Video controls"* && "$output" != *"FAIL:"* ]]
output="$(./node_modules/.bin/brs --root tests/roku roku/source/AutoplayData.brs roku/components/AutoplayController.brs roku/components/HistoryController.brs roku/components/PrefetchController.brs tests/roku/autoplay.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Autoplay policy and controller"* && "$output" != *"FAIL:"* ]]
output="$(./node_modules/.bin/brs --root tests/roku roku/source/SubtitleLabels.brs tests/roku/subtitle-labels.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Subtitle availability labels"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeActions.brs roku/source/HomeData.brs roku/components/home/HomeView.brs tests/roku/home-actions.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Home resume actions"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/components/MainScene.brs tests/roku/library-return.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Library return navigation"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/components/home/TopNavigation.brs tests/roku/top-navigation.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Top navigation"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeData.brs roku/source/TitleData.brs tests/roku/title-data.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Title page presentation"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/components/home/MediaRows.brs tests/roku/row-selection.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Row selection events"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeData.brs roku/source/SearchData.brs tests/roku/search-data.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Search data matching"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeData.brs roku/source/SearchData.brs roku/source/SearchLayout.brs roku/components/search/SearchView.brs tests/roku/search-view.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Search navigation and cache updates"* && "$output" != *"FAIL:"* ]]

output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeData.brs roku/source/SearchLayout.brs tests/roku/search-layout.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Search keyboard layout"* && "$output" != *"FAIL:"* ]]
