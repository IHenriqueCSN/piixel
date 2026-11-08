@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if errorlevel 1 goto :python_missing
        python -m venv .venv
    ) else (
        py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if errorlevel 1 goto :python_missing
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -c "import PySide6.QtWidgets" >nul 2>&1
if errorlevel 1 (
    echo Instalando os componentes do Piixelverso. A primeira execução precisa de internet.
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -m piixelverso
if errorlevel 1 goto :failed
popd
exit /b 0

:python_missing
echo Instale Python 3.11 ou superior para Windows e marque a opção de adicionar ao PATH.
goto :failure_end

:failed
echo Não foi possível iniciar o Piixelverso. Confira a mensagem acima e o README.md.

:failure_end
pause
popd
exit /b 1
