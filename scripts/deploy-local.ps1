#requires -Version 7.0
<#
.SYNOPSIS
  One-shot local deployment: Kind cluster -> images -> secrets -> manifests.
.EXAMPLE
  ./scripts/deploy-local.ps1
  ./scripts/deploy-local.ps1 -SkipCluster -SkipImages
#>
param(
  [string]$ClusterName = "gitops-platform",
  [string]$Tag = "1.0.0",
  [switch]$SkipCluster,
  [switch]$SkipImages,
  [switch]$SkipMonitoring
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$kind = Join-Path $env:USERPROFILE ".local\bin\kind.exe"
if (-not (Test-Path $kind)) { $kind = "kind" }

function Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }

if (-not $SkipCluster) {
  Step "Ensuring Kind cluster '$ClusterName'"
  $clusters = & $kind get clusters 2>$null
  if ($clusters -notcontains $ClusterName) {
    & $kind create cluster --config (Join-Path $repo "kubernetes/kind-config.yaml") --wait 240s
  } else {
    Write-Host "Cluster already exists."
  }
}

Step "Installing ingress-nginx (Kind flavour)"
& kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.0/deploy/static/provider/kind/deploy.yaml" | Out-Null
& kubectl -n ingress-nginx wait --for=condition=Available deployment/ingress-nginx-controller --timeout=240s

Step "Installing metrics-server (required for HPA)"
& kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml" | Out-Null
# Kind uses self-signed kubelet certificates.
& kubectl -n kube-system patch deployment metrics-server --type=json `
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' 2>$null
& kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s

if (-not $SkipImages) {
  Step "Building images"
  & docker compose --profile observability build
  Step "Loading images into Kind"
  foreach ($image in @(
      "platform/api-gateway:$Tag", "platform/user-service:$Tag", "platform/product-service:$Tag",
      "platform/order-service:$Tag", "platform/notification-service:$Tag",
      "platform/frontend:$Tag", "platform/platform-api:$Tag")) {
    & $kind load docker-image $image --name $ClusterName
  }
}

Step "Creating namespaces and secrets"
& kubectl apply -f (Join-Path $repo "kubernetes/namespaces/namespaces.yaml")
& (Join-Path $PSScriptRoot "create-dev-secrets.ps1") -Namespace platform

Step "Applying development overlay"
& kubectl apply -k (Join-Path $repo "kubernetes/overlays/development")

Step "Waiting for workloads"
& kubectl -n platform rollout status deployment/postgres --timeout=180s 2>$null
foreach ($svc in @("api-gateway", "user-service", "product-service", "order-service",
                   "notification-service", "frontend", "platform-api")) {
  & kubectl -n platform rollout status "deployment/$svc" --timeout=240s
}

if (-not $SkipMonitoring) {
  Step "Installing monitoring and logging"
  & kubectl apply -k (Join-Path $repo "monitoring")
  & kubectl apply -k (Join-Path $repo "logging")
  Write-Host "Prometheus/Grafana/Alertmanager/Loki are rolling out; check: kubectl -n monitoring get pods"
}

Step "Done"
Write-Host "UI:            http://localhost:18080/"
Write-Host "Platform API:  http://localhost:18080/platform/api/health"
Write-Host "Gateway:       http://localhost:18080/gateway/api/health"
Write-Host "Argo CD:       kubectl -n argocd port-forward svc/argocd-server 8080:443"
Write-Host "Grafana:       kubectl -n monitoring port-forward svc/grafana 3000:3000"
