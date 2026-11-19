#requires -Version 7.0
<#
.SYNOPSIS
  Inject runtime configuration into the dashboard so it works on first visit.
.DESCRIPTION
  Reads the read-only dashboard token and storefront API key from the
  platform-secrets Secret, writes a config.json ConfigMap, and mounts it into
  the frontend pod at /usr/share/nginx/html/config.json.

  Nothing secret is written to the repository: the ConfigMap lives only in the
  cluster and is regenerated whenever the Secret is rotated.
#>
param(
  [string]$Namespace = "platform",
  [string]$Deployment = "frontend"
)

$ErrorActionPreference = "Stop"

function Read-SecretValue([string]$name) {
  $b64 = kubectl -n $Namespace get secret platform-secrets -o jsonpath="{.data.$name}"
  if (-not $b64) { throw "platform-secrets is missing key '$name'. Run scripts/create-dev-secrets.ps1 first." }
  [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
}

$token = Read-SecretValue "PLATFORM_API_TOKEN"
$apiKey = Read-SecretValue "PUBLIC_API_KEY"

$config = [ordered]@{
  apiBase     = "/platform"
  gatewayBase = "/gateway"
  token       = $token
  apiKey      = $apiKey
} | ConvertTo-Json

kubectl -n $Namespace create configmap frontend-runtime-config `
  --from-literal=config.json=$config --dry-run=client -o yaml | kubectl apply -f - | Out-Null
Write-Host "ConfigMap frontend-runtime-config applied (token from platform-secrets)."

$deploymentJson = kubectl -n $Namespace get deployment $Deployment -o json | ConvertFrom-Json
$container = $deploymentJson.spec.template.spec.containers[0]
$hasVolume = $deploymentJson.spec.template.spec.volumes.name -contains "runtime-config"
if (-not $hasVolume -and -not $container.volumeMounts.mountPath.Contains("/usr/share/nginx/html/config.json")) {
  kubectl -n $Namespace patch deployment $Deployment --type=json -p @'
[
  {"op": "add", "path": "/spec/template/spec/volumes/-", "value": {"name": "runtime-config", "configMap": {"name": "frontend-runtime-config"}}},
  {"op": "add", "path": "/spec/template/spec/containers/0/volumeMounts/-", "value": {"name": "runtime-config", "mountPath": "/usr/share/nginx/html/config.json", "subPath": "config.json", "readOnly": true}}
]
'@ | Out-Null
  Write-Host "Deployment patched to mount runtime config."
} else {
  kubectl -n $Namespace rollout restart deployment $Deployment | Out-Null
  Write-Host "Runtime config changed; frontend restarted."
}

kubectl -n $Namespace rollout status deployment $Deployment --timeout=180s | Out-Null
Write-Host "Dashboard ready: http://localhost:18080/ops (no manual token entry needed)."
