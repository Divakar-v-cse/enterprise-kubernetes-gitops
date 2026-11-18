"""Helm chart tests: every chart lints, renders, and keeps the hardening contract."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHARTS = sorted((ROOT / "helm" / "charts").glob("*/"))
HELM = shutil.which("helm")

pytestmark = pytest.mark.skipif(HELM is None, reason="helm CLI not installed")


def _render(chart: pathlib.Path) -> list[dict]:
    result = subprocess.run(
        [HELM, "template", chart.name, str(chart), "--namespace", "platform"],
        capture_output=True, text=True, check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def test_all_six_service_charts_exist() -> None:
    names = {chart.name for chart in CHARTS}
    assert names == {
        "api-gateway", "user-service", "product-service",
        "order-service", "notification-service", "frontend",
    }


@pytest.mark.parametrize("chart", CHARTS, ids=lambda c: c.name)
def test_chart_lints(chart: pathlib.Path) -> None:
    subprocess.run([HELM, "lint", str(chart)], capture_output=True, text=True, check=True)


@pytest.mark.parametrize("chart", CHARTS, ids=lambda c: c.name)
def test_chart_renders_complete_workload(chart: pathlib.Path) -> None:
    docs = _render(chart)
    kinds = [doc["kind"] for doc in docs]
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "PodDisruptionBudget" in kinds

    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["requests"]["cpu"]
    assert container["resources"]["limits"]["memory"]
    for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert probe in container, f"{chart.name}: missing {probe}"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert deployment["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"] is True


@pytest.mark.parametrize("chart", CHARTS, ids=lambda c: c.name)
def test_chart_annotations_opt_into_scraping(chart: pathlib.Path) -> None:
    docs = _render(chart)
    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    annotations = deployment["spec"]["template"]["metadata"].get("annotations", {})
    if chart.name == "frontend":
        assert annotations.get("prometheus.io/scrape") == "false"
    else:
        assert annotations.get("prometheus.io/scrape") == "true"
        assert annotations.get("prometheus.io/port")


def test_hpa_renders_for_gateway_and_order() -> None:
    for name in ("api-gateway", "order-service"):
        docs = _render(ROOT / "helm" / "charts" / name)
        hpa = next((doc for doc in docs if doc["kind"] == "HorizontalPodAutoscaler"), None)
        assert hpa is not None, f"{name} should render an HPA"
        assert hpa["spec"]["metrics"][0]["resource"]["target"]["averageUtilization"] <= 70
