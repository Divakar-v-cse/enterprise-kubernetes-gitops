#requires -Version 7.0
<#
.SYNOPSIS
  Create the platform Secret with random credentials (never committed).
.DESCRIPTION
  Prefers `kubectl create secret` so values never touch a file on disk.
  Re-running rotates the credentials; pods must be restarted afterwards.
#>
param(
  [string]$Namespace = "platform",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$existing = & kubectl -n $Namespace get secret platform-secrets --ignore-not-found -o name
if ($existing -and -not $Force) {
  Write-Host "Secret platform-secrets already exists in namespace $Namespace. Use -Force to rotate." -ForegroundColor Yellow
  exit 0
}

function New-Secret([int]$Bytes = 24) {
  $buffer = [byte[]]::new($Bytes)
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
  return [Convert]::ToBase64String($buffer).Replace("+", "A").Replace("/", "B").Replace("=", "")
}

$postgres = New-Secret 24
$internal = New-Secret 32
$publicKey = New-Secret 24
$platformToken = New-Secret 24

if ($existing) { & kubectl -n $Namespace delete secret platform-secrets | Out-Null }

& kubectl -n $Namespace create secret generic platform-secrets `
  --from-literal=POSTGRES_PASSWORD=$postgres `
  --from-literal=INTERNAL_API_TOKEN=$internal `
  --from-literal=PUBLIC_API_KEY=$publicKey `
  --from-literal=PLATFORM_API_TOKEN=$platformToken | Out-Null

Write-Host "Created platform-secrets in $Namespace." -ForegroundColor Green
Write-Host "Platform API token (store it securely, it is not in Git): $platformToken"
Write-Host "Public storefront API key:                                 $publicKey"
