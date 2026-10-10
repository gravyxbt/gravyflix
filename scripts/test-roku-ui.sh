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

output="$(./node_modules/.bin/brs --root tests/roku roku/source/HomeActions.brs roku/components/home/HomeView.brs tests/roku/home-actions.brs 2>&1)"
printf '%s\n' "$output"
[[ "$output" == *"PASS: Home resume actions"* && "$output" != *"FAIL:"* ]]
