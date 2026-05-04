param(
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PidFile = Join-Path $Root ".server.pid"
$Python = "C:\Users\Xiaoj\miniconda3\envs\opentoken\python.exe"

& (Join-Path $PSScriptRoot "stop.ps1") -Port $Port

if (-not (Test-Path $Python)) {
    $Python = "python"
}

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList "-m backend.main" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $PidFile -Value $Process.Id
Write-Output "OpenToken started on http://127.0.0.1:$Port with PID $($Process.Id)"
