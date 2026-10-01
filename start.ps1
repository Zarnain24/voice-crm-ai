<#
  One command to run the whole Voice CRM:  .\start.cmd   (or: powershell -File start.ps1)

  First run installs everything; later runs start in seconds.
    -Reset   reload the demo data (wipes the database)
    -NoN8n   don't start n8n

  Runs backend, voice agent, frontend and n8n (via npx) in this terminal with colored,
  prefixed logs: [api] [agent] [web] [n8n]. Ctrl+C stops all four.
#>
param([switch]$Reset, [switch]$NoN8n)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Warn($message) { Write-Host "    $message" -ForegroundColor Yellow }
function Assert-Ok($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

# ---------- Prerequisites ----------
foreach ($tool in 'python', 'node', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed or not on PATH." }
}
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Warn "Created .env from .env.example. Fill in your API keys, then run this again."
    exit 1
}

# ---------- Python environments (reinstall only when requirements.txt changes) ----------
foreach ($service in 'backend', 'agent') {
    $python = "$service\.venv\Scripts\python.exe"
    $marker = "$service\.venv\.requirements-hash"
    $hash = (Get-FileHash "$service\requirements.txt").Hash
    if (-not (Test-Path $python)) {
        Step "Creating $service virtual environment"
        python -m venv "$service\.venv"; Assert-Ok "venv for $service"
    }
    if (-not (Test-Path $marker) -or (Get-Content $marker) -ne $hash) {
        Step "Installing $service dependencies (first run takes a few minutes)"
        & $python -m pip install --disable-pip-version-check -q -r "$service\requirements.txt"; Assert-Ok "pip install for $service"
        if ($service -eq 'agent') {
            Step 'Downloading voice models (VAD, turn detector, noise cancellation)'
            Push-Location agent
            try { & .venv\Scripts\python.exe agent.py download-files; Assert-Ok 'model download' } finally { Pop-Location }
        }
        Set-Content $marker $hash
    }
}

# ---------- Node dependencies ----------
if (-not (Test-Path node_modules)) { Step 'Installing launcher'; npm install --silent; Assert-Ok 'npm install' }
if (-not (Test-Path frontend\node_modules)) { Step 'Installing frontend dependencies'; npm install --silent --prefix frontend; Assert-Ok 'npm install (frontend)' }

# ---------- Database ----------
if ($Reset -or -not (Test-Path backend\crm.db)) {
    Step 'Loading demo data'
    Push-Location backend
    try { & .venv\Scripts\python.exe seed.py; Assert-Ok 'seed' } finally { Pop-Location }
}

# ---------- n8n (optional) ----------
# n8n 2.x requires Node.js 24+. If Node is older, run without n8n; Slack still works
# through the backend's direct fallback.
$runN8n = -not $NoN8n
if ($runN8n) {
    $nodeMajor = [int]((node -v).TrimStart('v').Split('.')[0])
    if ($nodeMajor -lt 24) {
        Warn "n8n needs Node.js 24 or newer (you have $(node -v)). Skipping n8n; Slack uses the direct fallback."
        $runN8n = $false
    }
}

# ---------- Ports ----------
# A previous run that didn't shut down cleanly can leave a process holding a port.
$ports = @{ 8000 = 'backend'; 5173 = 'frontend' }
if ($runN8n) { $ports[5678] = 'n8n' }
$busy = @()
foreach ($port in $ports.Keys) {
    $owner = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $owner) { continue }
    $pid_ = $owner.OwningProcess
    $name = (Get-Process -Id $pid_ -ErrorAction SilentlyContinue).ProcessName
    # If the owner already exited, the socket is held by a child it spawned (e.g. a uvicorn worker).
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$pid_" | ForEach-Object { $_.ProcessId })
    $busy += "Port $port ($($ports[$port])) is in use by PID $pid_ $(if ($name) { "($name)" } else { '(exited)' })" +
        $(if ($children) { "; child PIDs: $($children -join ', ')" } else { '' })
}
if ($busy) {
    $busy | ForEach-Object { Warn $_ }
    Warn 'Close the other window running this project, or stop those processes with: Stop-Process -Id <PID>'
    exit 1
}

# ---------- Run ----------
Write-Host '    Open http://localhost:5173' -ForegroundColor Green
if ($runN8n) {
    Step 'Starting backend (:8000), voice agent, frontend (:5173) and n8n (:5678). Press Ctrl+C to stop.'
    Warn 'The first n8n start downloads it via npx and can take a few minutes.'
    npm run dev
} else {
    Step 'Starting backend (:8000), voice agent and frontend (:5173). Press Ctrl+C to stop.'
    npm run dev:core
}
