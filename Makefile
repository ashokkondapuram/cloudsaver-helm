.PHONY: lint test package
HELM ?= helm
lint:
	$(HELM) lint charts/cloudsaver --strict
	$(HELM) lint charts/cloudsaver-platform --strict -f charts/cloudsaver-platform/values-production.example.yaml
test:
	HELM=$(HELM) python3 scripts/test_charts.py
package: lint
	mkdir -p dist
	$(HELM) package charts/cloudsaver -d dist
	$(HELM) package charts/cloudsaver-platform -d dist
