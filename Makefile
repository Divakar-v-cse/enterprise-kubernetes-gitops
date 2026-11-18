# Developer entry points. On Windows use PowerShell (or `make` with Git Bash).
SHELL := /bin/bash
PY ?= python
SERVICES := api-gateway user-service product-service order-service notification-service

.PHONY: help install test test-static test-live build up down logs smoke kind k8s k8s-delete \
        helm-lint helm-template validate scan dashboards charts clean

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "%-16s %s\n", $$1, $$2}'

install: ## Install Python dev dependencies
	$(PY) -m pip install -r requirements-dev.txt

test: ## Run every service suite (isolated processes)
	@for s in $(SERVICES) platform-api; do echo "== $$s =="; (cd $$s && $(PY) -m pytest -q) || exit 1; done

test-static: ## Manifest, Helm and hygiene tests
	$(PY) -m pytest tests -q --ignore=tests/test_integration_live.py

test-live: ## Integration tests against a running gateway
	$(PY) -m pytest tests/test_integration_live.py -q

build: ## Build all images
	docker compose --profile observability build

up: ## Start the local stack
	docker compose --profile observability up -d

down: ## Stop the stack (keep volumes)
	docker compose --profile observability down

logs: ## Tail gateway logs
	docker compose logs -f api-gateway

smoke: ## End-to-end API smoke test
	./scripts/smoke-test.ps1

kind: ## Create the Kind cluster
	kind create cluster --config kubernetes/kind-config.yaml

k8s: ## Deploy via kustomize
	kubectl apply -f kubernetes/namespaces/namespaces.yaml
	kubectl apply -k kubernetes/overlays/development

k8s-delete: ## Delete the Kind cluster
	kind delete cluster --name gitops-platform

helm-lint: ## Lint the reusable chart and every generated chart
	helm lint helm/microservice
	@for c in helm/charts/*/; do helm lint "$$c" || exit 1; done

helm-template: ## Render every chart
	@mkdir -p rendered
	@for c in helm/charts/*/; do n=$$(basename $$c); helm template $$n $$c -n platform > rendered/$$n.yaml; echo "rendered/$$n.yaml"; done

validate: ## kustomize + kubeconform (requires kubeconform)
	kubectl kustomize kubernetes/overlays/development > /tmp/dev.yaml
	kubeconform -strict -summary -kubernetes-version 1.31.0 /tmp/dev.yaml

scan: ## Trivy config scan (requires trivy)
	trivy config --severity HIGH,CRITICAL kubernetes

charts: ## Regenerate per-service Helm charts
	$(PY) tools/generate_helm_charts.py

dashboards: ## Regenerate Grafana dashboards
	$(PY) tools/generate_dashboards.py

clean: ## Remove local caches and render output
	rm -rf rendered .pytest_cache .ruff_cache **/__pycache__ applications/frontend/dist
