"""Static policy tests for the Kubernetes manifests.

These assert the properties the platform claims to enforce, so a regression in
a manifest fails CI instead of silently weakening the deployment.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_DIRS = [ROOT / "kubernetes", ROOT / "monitoring", ROOT / "logging"]


def _documents() -> list[dict]:
    docs: list[dict] = []
    for base in MANIFEST_DIRS:
        for path in base.rglob("*.yaml"):
            try:
                for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
                    if isinstance(doc, dict) and doc.get("kind"):
                        doc["__source"] = str(path.relative_to(ROOT))
                        docs.append(doc)
            except yaml.YAMLError as exc:  # pragma: no cover
                pytest.fail(f"{path} is not valid YAML: {exc}")
    return docs


DOCS = _documents()
DEPLOYMENTS = [d for d in DOCS if d["kind"] == "Deployment"]


def test_manifests_are_parseable_and_non_trivial() -> None:
    assert len(DOCS) > 40
    assert len(DEPLOYMENTS) >= 7


@pytest.mark.parametrize("deployment", DEPLOYMENTS, ids=lambda d: f"{d['__source']}:{d['metadata']['name']}")
def test_deployment_hardening(deployment: dict) -> None:
    spec = deployment["spec"]["template"]["spec"]
    pod_security = spec.get("securityContext", {})
    assert pod_security.get("runAsNonRoot") is True, "pod must run as non-root"
    assert pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault"

    containers = spec["containers"]
    assert containers, "deployment has no containers"
    for container in containers:
        assert container.get("resources", {}).get("requests"), "requests required"
        assert container.get("resources", {}).get("limits"), "limits required"
        assert "livenessProbe" in container, "liveness probe required"
        assert "readinessProbe" in container, "readiness probe required"
        assert container.get("image", "").split(":")[-1] != "latest"
        container_security = container.get("securityContext", {})
        assert container_security.get("allowPrivilegeEscalation") is False
        assert "ALL" in container_security.get("capabilities", {}).get("drop", [])


def test_all_application_images_use_pinned_tags() -> None:
    for deployment in DEPLOYMENTS:
        for container in deployment["spec"]["template"]["spec"]["containers"]:
            image = container["image"]
            assert ":" in image or "@sha256:" in image, f"{image} is not pinned"


def test_services_are_cluster_internal_by_default() -> None:
    services = [d for d in DOCS if d["kind"] == "Service"]
    assert services
    for service in services:
        if service["metadata"]["name"] == "node-exporter":
            continue
        assert service["spec"].get("type", "ClusterIP") in {"ClusterIP", "None"}


def test_network_policies_deny_by_default() -> None:
    policies = [d for d in DOCS if d["kind"] == "NetworkPolicy"]
    names = {p["metadata"]["name"] for p in policies}
    assert "default-deny-all" in names
    deny = next(p for p in policies if p["metadata"]["name"] == "default-deny-all")
    assert set(deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    assert "allow-order-to-dependencies" in names


def test_pod_disruption_budgets_cover_stateless_services() -> None:
    pdb_names = {d["metadata"]["name"] for d in DOCS if d["kind"] == "PodDisruptionBudget"}
    for service in {
        "api-gateway", "user-service", "product-service", "order-service",
        "notification-service", "frontend",
    }:
        assert service in pdb_names


def test_hpa_targets_cpu_for_edge_and_order() -> None:
    hpas = {d["metadata"]["name"]: d for d in DOCS if d["kind"] == "HorizontalPodAutoscaler"}
    assert {"api-gateway", "order-service"}.issubset(hpas)
    for name in ("api-gateway", "order-service"):
        metric = hpas[name]["spec"]["metrics"][0]
        assert metric["resource"]["name"] == "cpu"
        assert hpas[name]["spec"]["minReplicas"] >= 1


def test_namespaces_enforce_pod_security_standards() -> None:
    namespaces = [d for d in DOCS if d["kind"] == "Namespace"]
    assert namespaces
    for namespace in namespaces:
        labels = namespace["metadata"].get("labels", {})
        assert "pod-security.kubernetes.io/enforce" in labels, namespace["metadata"]["name"]


def test_resource_quota_and_limit_range_exist() -> None:
    kinds = {d["kind"] for d in DOCS}
    assert "ResourceQuota" in kinds
    assert "LimitRange" in kinds


def test_platform_api_rbac_is_read_only() -> None:
    roles = [d for d in DOCS if d["kind"] == "ClusterRole" and d["metadata"]["name"] == "platform-api-readonly"]
    assert roles, "platform-api ClusterRole missing"
    verbs = {verb for rule in roles[0]["rules"] for verb in rule["verbs"]}
    assert verbs <= {"get", "list"}, f"write verbs granted to read-only role: {verbs}"
    for rule in roles[0]["rules"]:
        assert "secrets" not in rule.get("resources", [])


def test_no_literal_secrets_committed() -> None:
    for doc in DOCS:
        if doc["kind"] != "Secret":
            continue
        payload = doc.get("stringData") or doc.get("data") or {}
        for key, value in payload.items():
            assert "REPLACE_ME" in str(value), (
                f"{doc['__source']} contains a non-placeholder secret value for {key}"
            )


def test_ingress_exposes_only_expected_backends() -> None:
    ingresses = [d for d in DOCS if d["kind"] == "Ingress"]
    assert ingresses
    backends = {
        path["backend"]["service"]["name"]
        for ingress in ingresses
        for rule in ingress["spec"]["rules"]
        for path in rule["http"]["paths"]
    }
    assert backends <= {"frontend", "api-gateway", "platform-api"}


def test_dockerfiles_run_as_non_root() -> None:
    for dockerfile in ROOT.glob("applications/*/Dockerfile"):
        text = dockerfile.read_text(encoding="utf-8")
        assert re.search(r"^USER\s+(10001|101|65534)", text, re.MULTILINE), (
            f"{dockerfile} must switch to a non-root USER"
        )
        assert "HEALTHCHECK" in text, f"{dockerfile} must declare HEALTHCHECK"
    platform_dockerfile = ROOT / "docker" / "platform-api.Dockerfile"
    assert "USER 10001" in platform_dockerfile.read_text(encoding="utf-8")
