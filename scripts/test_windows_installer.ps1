<# Smoke test for the actual installer and frozen application in a disposable folder. #>
[CmdletBinding()]
param([string]$PythonExecutable = "python")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Execute esta verificação em Windows." }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installers = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot "dist\installer") -Filter "Piixel-Setup-*-x64.exe")
if ($installers.Count -ne 1) { throw "Era esperado um único instalador Windows." }
$checkRoot = Join-Path ([IO.Path]::GetTempPath()) ("piixel-installer-check-" + [guid]::NewGuid().ToString("N"))
$installRoot = Join-Path $checkRoot "Programa com espaços"
$dataRoot = Join-Path $checkRoot "Dados de teste"
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
$sentinel = Join-Path $dataRoot "preservar.txt"
Set-Content -LiteralPath $sentinel -Value "Dados pessoais precisam sobreviver à desinstalação."
$design = Join-Path $dataRoot "Minha criação.pii"
Copy-Item -LiteralPath (Join-Path $projectRoot "examples\cogumelo-do-bosque.pii") -Destination $design
$designHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $design).Hash
$previousDataDirectory = $env:PIIXEL_DATA_DIR
$env:PIIXEL_DATA_DIR = $dataRoot

try {
    $installArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/TASKS=',
        ('/DIR="' + $installRoot + '"'), ('/LOG="' + (Join-Path $checkRoot 'install.log') + '"'))
    $installation = Start-Process -FilePath $installers[0].FullName -ArgumentList $installArguments -Wait -PassThru
    if ($installation.ExitCode -ne 0) { throw "A instalação falhou: $($installation.ExitCode)." }
    $application = Join-Path $installRoot "Piixel.exe"
    if (-not (Test-Path -LiteralPath $application)) { throw "O aplicativo não foi instalado." }

    # Opening a real .pii proves that the frozen GUI, fonts, SVGs, format and
    # Ateliê all load successfully. Its saved recent-file entry is the signal.
    $smokeCode = @'
import json, os, pathlib, subprocess, sys, time
executable, data_dir, design = map(pathlib.Path, sys.argv[1:])
environment = dict(os.environ, PIIXEL_DATA_DIR=str(data_dir), QT_QPA_PLATFORM="offscreen")
process = subprocess.Popen([str(executable), str(design)], cwd=data_dir, env=environment)
try:
    deadline = time.monotonic() + 30
    loaded = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"O aplicativo encerrou durante o carregamento: {process.returncode}")
        try:
            document = json.loads((data_dir / "preferences.json").read_text(encoding="utf-8"))
            loaded = any(pathlib.Path(entry["path"]) == design for entry in document.get("recent_files", []))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if loaded:
            break
        time.sleep(0.1)
    if not loaded:
        raise RuntimeError("O aplicativo instalado não concluiu a abertura do design de teste.")
    print("Aplicativo instalado abriu o design, renderizou os recursos e gravou os recentes.")
finally:
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=10)
'@
    & $PythonExecutable -c $smokeCode $application $dataRoot $design
    if ($LASTEXITCODE -ne 0) { throw "O teste do aplicativo instalado falhou." }

    $uninstaller = Join-Path $installRoot "unins000.exe"
    if (-not (Test-Path -LiteralPath $uninstaller)) { throw "O desinstalador não foi criado." }
    $removal = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
    if ($removal.ExitCode -ne 0) { throw "A desinstalação falhou: $($removal.ExitCode)." }
    if (Test-Path -LiteralPath $application) { throw "O executável não foi removido." }
    if (-not (Test-Path -LiteralPath $sentinel)) { throw "A desinstalação removeu dados do usuário." }
    if (-not (Test-Path -LiteralPath (Join-Path $dataRoot "preferences.json"))) {
        throw "A desinstalação removeu as preferências do usuário."
    }
    if (-not (Test-Path -LiteralPath $design) -or (Get-FileHash -Algorithm SHA256 -LiteralPath $design).Hash -ne $designHash) {
        throw "A desinstalação alterou o design do usuário."
    }
    Write-Host "Instalação, inicialização e desinstalação verificadas; dados pessoais preservados."
}
catch {
    $installLog = Join-Path $checkRoot "install.log"
    if (Test-Path -LiteralPath $installLog) { Get-Content -LiteralPath $installLog -Tail 40 | Write-Host }
    throw
}
finally {
    $env:PIIXEL_DATA_DIR = $previousDataDirectory
    # Only this script's uniquely named temporary directory is removed.
    if (Test-Path -LiteralPath $checkRoot) { Remove-Item -LiteralPath $checkRoot -Recurse -Force }
}
