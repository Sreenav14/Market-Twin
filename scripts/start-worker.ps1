# Start exactly one MarketTwin execution worker.
#
# Stop-then-start: every existing worker chain (supervisors, their worker
# children, and the venv shim processes around them) is stopped first, the
# viewer port must be free, and only then is ONE worker started, detached
# via WMI so it survives the shell that launched it. Running this script
# twice in a row therefore still leaves exactly one chain.

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Module = 'markettwin_execution_orchestrator.worker'

function Get-WorkerProcess {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*$Module*" }
}

# 1. Stop all worker chains. Chain roots (whose parent is not itself a
#    worker process) die first so supervisors cannot respawn children
#    while the rest are being stopped; repeat until none remain.
for ($pass = 0; $pass -lt 10; $pass++) {
    $procs = @(Get-WorkerProcess)
    if ($procs.Count -eq 0) { break }
    $ids = $procs.ProcessId
    $roots = $procs | Where-Object { $ids -notcontains $_.ParentProcessId }
    $rest = $procs | Where-Object { $ids -contains $_.ParentProcessId }
    foreach ($p in @($roots) + @($rest)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}
if (@(Get-WorkerProcess).Count -gt 0) {
    throw 'Execution worker processes are still running after the stop passes.'
}

# 2. The viewer port must be free before the new worker binds it.
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 1
}
if (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8020 is still in use; not starting a worker.'
}

# 3. Start one worker, detached (WMI processes survive this shell).
$uv = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
if (-not (Test-Path $uv)) { $uv = 'uv' }
$command = "$uv run --no-sync --env-file .env python -m $Module"
$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine      = $command
    CurrentDirectory = $Repo
}
if ($created.ReturnValue -ne 0) {
    throw "Worker launch failed: WMI Create returned $($created.ReturnValue)."
}
Write-Output "Started worker launcher (pid $($created.ProcessId))."

# 4. Report the resulting chain and the viewer port owner.
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue) { break }
}
Write-Output '--- execution worker processes ---'
Get-WorkerProcess | ForEach-Object {
    Write-Output "pid $($_.ProcessId) parent $($_.ParentProcessId) started $($_.CreationDate)"
}
Write-Output '--- port 8020 ---'
$listener = Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "listening, owned by pid $($listener.OwningProcess)"
} else {
    Write-Output 'not listening yet (worker still starting)'
}
