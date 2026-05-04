param(
    [int]$Port = 18080
)

$ErrorActionPreference = "SilentlyContinue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PidFile = Join-Path $Root ".server.pid"

if (Test-Path $PidFile) {
    $SavedPid = [int](Get-Content $PidFile -Raw)
    $Process = Get-Process -Id $SavedPid
    if ($Process) {
        Stop-Process -Id $SavedPid -Force
        Start-Sleep -Milliseconds 500
    }
    Remove-Item $PidFile -Force
}

$Listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
foreach ($Listener in $Listeners) {
    if ($Listener.OwningProcess -gt 0) {
        Stop-Process -Id $Listener.OwningProcess -Force
    }
}
