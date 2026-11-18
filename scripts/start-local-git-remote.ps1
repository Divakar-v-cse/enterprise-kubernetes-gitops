#requires -Version 7.0
<#
.SYNOPSIS
  Serve this repository as a read-only Git remote for Argo CD, without GitHub.
.DESCRIPTION
  Creates a bare mirror under .gitops-remote/ and exposes it over HTTP using
  Git's "dumb HTTP" protocol (git update-server-info + a static file server).
  Argo CD in the Kind cluster reaches it at http://host.docker.internal:8099/.
  This is a local demo aid, not a production Git server.
#>
param(
  [int]$Port = 8099,
  [string]$RemoteName = "local"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$remoteRoot = Join-Path (Split-Path -Parent $repo) ".gitops-remote"
$bare = Join-Path $remoteRoot "enterprise-kubernetes-gitops.git"

New-Item -ItemType Directory -Force -Path $remoteRoot | Out-Null
if (-not (Test-Path $bare)) {
  git init --bare $bare | Out-Null
  Write-Host "Created bare repository: $bare"
}

Push-Location $repo
try {
  $existing = git remote
  if ($existing -notcontains $RemoteName) {
    git remote add $RemoteName $bare
  }
  git push $RemoteName HEAD:main --force
  Write-Host "Pushed current HEAD to $RemoteName/main" -ForegroundColor Green
} finally {
  Pop-Location
}

Push-Location $bare
try {
  git update-server-info
  # Refresh the dumb-HTTP metadata whenever a push lands.
  $hook = Join-Path $bare "hooks/post-receive"
  "#!/bin/sh`ngit update-server-info" | Set-Content -Encoding UTF8 $hook
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "Serving $bare at http://localhost:$Port/enterprise-kubernetes-gitops.git" -ForegroundColor Cyan
Write-Host "Argo CD (inside Kind) uses http://host.docker.internal:$Port/enterprise-kubernetes-gitops.git"
Write-Host "Press Ctrl+C to stop. Re-run this script after new commits to re-push."
Push-Location $remoteRoot
try {
  python -m http.server $Port --bind 0.0.0.0
} finally {
  Pop-Location
}
