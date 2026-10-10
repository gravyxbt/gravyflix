.PHONY: setup start scan test roku-check roku-package roku-install test-video
setup:
	./scripts/setup.sh
start:
	./scripts/start.sh
scan:
	./scripts/scan.sh
test:
	./scripts/test.sh
roku-check:
	./scripts/check-roku.sh
roku-package:
	./scripts/package-roku.sh
roku-install:
	./scripts/install-roku.sh
test-video:
	./scripts/create-test-video.sh

.PHONY: roku-test-ui
roku-test-ui:
	./scripts/test-roku-ui.sh

.PHONY: public-audit source-package
public-audit:
	python3 scripts/audit-publication.py
source-package:
	python3 scripts/package-source.py --output ../gravyflix-source.zip
