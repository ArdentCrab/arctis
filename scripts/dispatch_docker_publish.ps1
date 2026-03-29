# Triggers GitHub Actions "Docker publish" via workflow_dispatch (ref = default branch).
# Requires: $env:GITHUB_TOKEN with repo scope (classic PAT) or fine-grained "Actions: write".
# Usage:  $env:GITHUB_TOKEN = "ghp_..." ; .\scripts\dispatch_docker_publish.ps1
#         Optional: -Ref "master"
param(
    [string] $Owner = "arctis-lab",
    [string] $Repo = "arctis",
    [string] $WorkflowFile = "docker-publish.yml",
    [string] $Ref = "master"
)
$ErrorActionPreference = "Stop"
if (-not $env:GITHUB_TOKEN) {
    Write-Error "Set environment variable GITHUB_TOKEN (PAT with Actions workflow dispatch permission)."
}
$uri = "https://api.github.com/repos/$Owner/$Repo/actions/workflows/$WorkflowFile/dispatches"
$headers = @{
    Accept               = "application/vnd.github+json"
    Authorization        = "Bearer $($env:GITHUB_TOKEN)"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$body = @{ ref = $Ref } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body -ContentType "application/json"
Write-Host "Dispatched workflow_dispatch for $Owner/$Repo ($WorkflowFile) ref=$Ref"
