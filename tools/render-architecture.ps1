#requires -Version 7.0
<#
.SYNOPSIS
  Render architecture/platform-architecture.mmd to PNG using headless Chrome.
.DESCRIPTION
  Keeps the diagram source reviewable in Git while producing the PNG required
  by the docs. Requires Chrome and internet access for the Mermaid CDN.
#>
param(
  [string]$Source = "architecture/platform-architecture.mmd",
  [string]$Output = "architecture/platform-architecture.png",
  [int]$Width = 2000,
  [int]$Height = 1500
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repo $Source
$out = Join-Path $repo $Output
$html = Join-Path $env:TEMP "architecture-render-$PID.html"

$mermaid = Get-Content -Raw -Encoding UTF8 $src

$template = @"
<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: #ffffff; font-family: 'Segoe UI', sans-serif; }
  .mermaid { display: inline-block; }
</style>
</head><body>
<pre class="mermaid">
$mermaid
</pre>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({
    startOnLoad: true,
    theme: 'base',
    themeVariables: {
      primaryColor: '#eef2ff', primaryTextColor: '#0f172a', primaryBorderColor: '#6366f1',
      lineColor: '#475569', secondaryColor: '#f1f5f9', tertiaryColor: '#f8fafc',
      fontFamily: 'Segoe UI, sans-serif', fontSize: '15px'
    },
    flowchart: { curve: 'basis', nodeSpacing: 45, rankSpacing: 55, htmlLabels: true }
  });
</script>
</body></html>
"@

Set-Content -Path $html -Value $template -Encoding UTF8

$chrome = @(
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) { throw "Chrome not found; open $html manually and export a screenshot." }

& $chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
  --window-size="$Width,$Height" --virtual-time-budget=12000 `
  --screenshot="$out" "file:///$($html -replace '\\','/')" | Out-Null

if (Test-Path $out) {
  Write-Host "Wrote $out ($([math]::Round((Get-Item $out).Length / 1KB)) KB)" -ForegroundColor Green
} else {
  throw "PNG was not produced"
}
