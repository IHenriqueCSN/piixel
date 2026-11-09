<#
.SYNOPSIS
Gera o instalador Windows do Piixel com PyInstaller e Inno Setup 6.
.EXAMPLE
.\scripts\build_windows_installer.ps1 -PythonExecutable ".\.venv\Scripts\python.exe"
.EXAMPLE
.\scripts\build_windows_installer.ps1 -SkipBuild
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [string]$PythonExecutable = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "O instalador Windows precisa ser gerado em Windows. Use também o workflow do GitHub Actions."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installerScript = Join-Path $projectRoot "installer\windows\piixel.iss"
$projectFile = Join-Path $projectRoot "pyproject.toml"

function Find-InnoCompiler {
    if ($env:INNO_SETUP_COMPILER) {
        if (-not (Test-Path -LiteralPath $env:INNO_SETUP_COMPILER -PathType Leaf)) {
            throw "INNO_SETUP_COMPILER deve apontar para um arquivo ISCC.exe existente."
        }
        return (Resolve-Path -LiteralPath $env:INNO_SETUP_COMPILER).Path
    }

    $command = Get-Command "ISCC.exe" -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $programDirectories = @(${env:ProgramFiles(x86)}, $env:ProgramFiles)
    foreach ($directory in $programDirectories) {
        if ($directory) {
            $candidate = Join-Path $directory "Inno Setup 6\ISCC.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }

    throw "Instale o Inno Setup 6 em https://jrsoftware.org/isdl.php ou defina INNO_SETUP_COMPILER com o caminho de ISCC.exe."
}

$compiler = Find-InnoCompiler
$versionCode = "import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))['project']['version'])"
$versionOutput = & $PythonExecutable -c $versionCode $projectFile
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível ler a versão. Informe um Python 3.11 ou superior em -PythonExecutable."
}
$appVersion = ($versionOutput -join "`n").Trim()
if ($appVersion -notmatch '^(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})$') {
    throw "A versão em pyproject.toml precisa usar três números, como 0.1.0."
}
foreach ($component in $appVersion.Split('.')) {
    if ([int]$component -gt 65535) {
        throw "Cada número da versão precisa estar entre 0 e 65535."
    }
}

Push-Location $projectRoot
try {
    if (-not $SkipBuild) {
        & $PythonExecutable (Join-Path $projectRoot "scripts\build.py")
        if ($LASTEXITCODE -ne 0) {
            throw "O empacotamento do aplicativo falhou. O instalador não foi compilado."
        }
    }

    $application = Join-Path $projectRoot "dist\Piixel\Piixel.exe"
    $dependencies = Join-Path $projectRoot "dist\Piixel\_internal"
    $icon = Join-Path $projectRoot "build\windows\piixel.ico"
    if (-not (Test-Path -LiteralPath $application -PathType Leaf) -or
        -not (Test-Path -LiteralPath $dependencies -PathType Container) -or
        -not (Test-Path -LiteralPath $icon -PathType Leaf)) {
        throw "O pacote Windows está incompleto. Execute scripts/build.py no Windows antes de usar -SkipBuild."
    }

    & $compiler "/Qp" "/DAppVersion=$appVersion" $installerScript
    if ($LASTEXITCODE -ne 0) {
        throw "O Inno Setup não conseguiu compilar o instalador. Confira as mensagens acima."
    }

    $output = Join-Path $projectRoot "dist\installer\Piixel-Setup-$appVersion-x64.exe"
    if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
        throw "O compilador terminou sem gerar o instalador esperado: $output"
    }
    Write-Host "Instalador gerado em: $output"
}
finally {
    Pop-Location
}
