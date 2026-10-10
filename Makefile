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

.PHONY: setup-macos macos-service-install macos-service-status
setup-macos:
	./scripts/setup-macos.sh
macos-service-install:
	.venv/bin/python scripts/macos-service.py install
macos-service-status:
	.venv/bin/python scripts/macos-service.py status
