$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonGuiPath = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$pythonCliPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path $pythonGuiPath) { $pythonGuiPath } else { $pythonCliPath }
$entryPoint = Join-Path $projectRoot "main.py"

if (-not (Test-Path $pythonPath)) {
    Write-Error "未找到项目虚拟环境解释器: $pythonPath"
}

if (-not (Test-Path $entryPoint)) {
    Write-Error "未找到项目入口文件: $entryPoint"
}

Push-Location $projectRoot
try {
    & $pythonPath $entryPoint @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
