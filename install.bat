@echo off
REM ============================================================================
REM EIDOS — Bootstrap Magico para Windows
REM ============================================================================
REM Instala EIDOS de forma autocontenida en el SSD/Pendrive.
REM No usa el Python del sistema: descarga python-build-standalone (Indygreg).
REM Al terminar, genera config\eidos.yaml y crea el Launcher EIDOS.bat.
REM
REM Uso: doble clic sobre install.bat
REM ============================================================================

setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "EIDOS_ROOT=%~dp0"
set "EIDOS_ROOT=%EIDOS_ROOT:~0,-1%"
set "ENV_DIR=%EIDOS_ROOT%\.eidos_env"
set "PYTHON_DIR=%ENV_DIR%\python"
set "UV_DIR=%ENV_DIR%\uv"
set "CONFIG_DIR=%EIDOS_ROOT%\config"
set "MODELS_DIR=%EIDOS_ROOT%\models"

set "PYTHON_VERSION=3.12.7"
set "PYTHON_RELEASE=20241002"
set "PYTHON_BUILD_TAG=%PYTHON_VERSION%+%PYTHON_RELEASE%"

echo.
echo  ============================================================
echo            ^|^|  EIDOS - Instalacion Magica  ^|^|
echo  ============================================================
echo       Tu mente artificial, portable y privada.
echo.
echo  Este asistente instalara EIDOS de forma autocontenida.
echo  No se modificara tu sistema: todo queda en esta carpeta.
echo.

REM ============================================================================
REM 1. Deteccion de entorno (SSD externo vs disco local)
REM ============================================================================

echo  1. Deteccion de entorno

REM En Windows, unidades externas suelen ser D:\, E:\, F:\... (no C:\)
set "DRIVE=%EIDOS_ROOT:~0,2%"
if /I "%DRIVE%"=="C:" (
    echo     [!] Disco local detectado ^(no SSD externo^).
    echo     EIDOS se instalara aqui, pero no sera portable.
    set "IS_PORTABLE=0"
) else (
    echo     [OK] Volumen externo detectado: %DRIVE%
    echo     EIDOS vivira en este SSD/Pendrive y sera portable.
    set "IS_PORTABLE=1"
)
echo.

REM ============================================================================
REM 2. Verificacion de conexion
REM ============================================================================

echo  2. Verificacion de conexion
ping -n 1 -w 3000 github.com >nul 2>&1
if errorlevel 1 (
    echo     [X] No hay conexion a internet.
    echo     EIDOS necesita internet solo para instalacion inicial.
    set /p "CONT=    Continuar de todas formas? (s/N): "
    if /I not "!CONT!"=="s" exit /b 1
) else (
    echo     [OK] Conexion a internet OK
)
echo.

REM ============================================================================
REM 3. Deteccion de arquitectura (x64 vs ARM64)
REM ============================================================================

echo  3. Deteccion de arquitectura
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set "PYARCH=x86_64-pc-windows-msvc-shared-install_only"
    echo     [OK] x86_64 detectado
) else if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    set "PYARCH=aarch64-pc-windows-msvc-install_only"
    echo     [OK] ARM64 detectado
) else (
    echo     [X] Arquitectura no soportada: %PROCESSOR_ARCHITECTURE%
    exit /b 1
)
echo.

REM ============================================================================
REM 4. Descarga e instalacion de Python portable
REM ============================================================================

echo  4. Instalacion de Python portable
echo     Descargando python-build-standalone v%PYTHON_BUILD_TAG%...

if not exist "%ENV_DIR%" mkdir "%ENV_DIR%"
if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"

set "PYTHON_URL=https://github.com/indygreg/python-build-standalone/releases/download/%PYTHON_RELEASE%/cpython-%PYTHON_BUILD_TAG%-%PYARCH%.tar.gz"
set "PYTHON_TARBALL=%ENV_DIR%\python.tar.gz"

if exist "%PYTHON_DIR%\python.exe" (
    "%PYTHON_DIR%\python.exe" --version 2>nul
    echo     [OK] Python ya instalado en .eidos_env\python\
) else (
    REM Descargar con PowerShell (curl no viene en todos los Windows)
    powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_TARBALL%' -UseBasicParsing } catch { exit 1 }"
    if errorlevel 1 (
        echo     [X] Error descargando Python.
        if exist "%PYTHON_TARBALL%" del "%PYTHON_TARBALL%"
        exit /b 1
    )
    echo     [OK] Descarga completa. Extrayendo...
    REM Usar tar (disponible en Windows 10+)
    tar -xzf "%PYTHON_TARBALL%" -C "%ENV_DIR%"
    del "%PYTHON_TARBALL%"
    if not exist "%PYTHON_DIR%\python.exe" (
        echo     [X] La extraccion no produjo un binario Python valido.
        exit /b 1
    )
    "%PYTHON_DIR%\python.exe" --version
    echo     [OK] Python instalado
)
echo.

REM ============================================================================
REM 5. Instalacion de uv
REM ============================================================================

echo  5. Instalacion de uv ^(gestor de paquetes^)
if not exist "%UV_DIR%" mkdir "%UV_DIR%"
set "UV_BIN=%UV_DIR%\uv.exe"
if exist "%UV_BIN%" (
    echo     [OK] uv ya instalado
) else (
    echo     Descargando uv...
    powershell -Command "$env:UV_INSTALL_DIR='%UV_DIR%'; irm https://astral.sh/uv/install.ps1 | iex" 2>nul
    if not exist "%UV_BIN%" (
        echo     [X] Error instalando uv.
        exit /b 1
    )
    echo     [OK] uv instalado
)
echo.

REM ============================================================================
REM 6. Creacion del entorno virtual
REM ============================================================================

echo  6. Creacion del entorno virtual
set "VENV_DIR=%ENV_DIR%\venv"
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo     [OK] Entorno virtual ya existe
) else (
    echo     Creando entorno virtual...
    "%UV_BIN%" venv "%VENV_DIR%" --python "%PYTHON_DIR%\python.exe" >nul 2>&1
    if errorlevel 1 (
        echo     [X] Error creando entorno virtual.
        exit /b 1
    )
    echo     [OK] Entorno virtual creado
)
echo.

REM ============================================================================
REM 7. Instalacion de dependencias
REM ============================================================================

echo  7. Instalacion de dependencias de EIDOS
echo     Sincronizando dependencias ^(puede tardar 1-2 minutos^)...
cd /d "%EIDOS_ROOT%"
set "VIRTUAL_ENV=%VENV_DIR%"
set "PATH=%UV_DIR%;%VENV_DIR%\Scripts;%PYTHON_DIR%;%PATH%"
"%UV_BIN%" sync --no-dev >nul 2>&1
if errorlevel 1 (
    echo     [!] Algunas dependencias opcionales no se instalaron.
    echo     EIDOS funcionara en modo basico.
) else (
    echo     [OK] Dependencias instaladas
)
echo.

REM ============================================================================
REM 8. Pregunta: Cerebro Local
REM ============================================================================

echo  8. Cerebro Local ^(Qwen 2.5 3B^)
echo     EIDOS puede funcionar con un modelo de IA local para privacidad total.
echo     Esto ocupa ~2 GB y permite que EIDOS piense sin internet.
set /p "DOWNLOAD_BRAIN=    Descargar Cerebro Local ahora? (s/N): "
if /I "!DOWNLOAD_BRAIN!"=="s" (
    set "WANT_CORTEX=1"
    echo     [OK] Se descargara el cerebro local.
) else (
    set "WANT_CORTEX=0"
    echo     No se descargara el cerebro local. Podras hacerlo despues.
)
echo.

REM ============================================================================
REM 9. MESH
REM ============================================================================

echo  9. Enjambre MESH
echo     EIDOS puede correr varias instancias en paralelo que cooperan.
set /p "ACTIVATE_MESH=    Activar MESH por defecto? (s/N): "
if /I "!ACTIVATE_MESH!"=="s" (
    set "MESH_ENABLED=true"
    echo     [OK] MESH activado.
) else (
    set "MESH_ENABLED=false"
    echo     MESH desactivado.
)
echo.

REM ============================================================================
REM 10. Generar config\eidos.yaml
REM ============================================================================

echo  Generando config\eidos.yaml...
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

if "!WANT_CORTEX!"=="1" (
    set "BACKEND=auto"
    set "CORTEX_ENABLED=true"
) else (
    set "BACKEND=stub"
    set "CORTEX_ENABLED=false"
)

REM Escribir YAML con redirección (cuidado con los saltos de línea)
> "%CONFIG_DIR%\eidos.yaml" (
echo meta:
echo   name: "EIDOS"
echo   version: "0.1.0"
echo   locale: "es-ES"
echo   identity: "Soy EIDOS, una entidad cognitiva autonoma, profunda y cooperativa."
echo.
echo core:
echo   monologue_backend: "!BACKEND!"
echo   confidence_threshold: 0.6
echo   persist_monologues: true
echo   monologues_dir: "data/monologues"
echo   max_plan_steps: 5
echo.
echo memory:
echo   sensory:
echo     window_size: 50
echo   episodic:
echo     backend: "sqlite_vec"
echo     db_path: "data/eidos.db"
echo     embedding_dim: 384
echo     max_events: 10000
echo   semantic:
echo     graph_path: "data/graph.json"
echo     backend: "networkx"
echo   procedural:
echo     capsules_dir: "data/capsules"
echo     default_ttl_days: 7
echo     favorite_preserve: true
echo   metacognitive:
echo     index_table: "monologue_index"
echo     consolidation_interval_sec: 300
echo.
echo cortex:
echo   enabled: !CORTEX_ENABLED!
echo   models_dir: "models"
echo   default_model: "qwen2.5-3b-instruct-q4_k_m.gguf"
echo   vram_budget_mb: 4096
echo   fallback_to_api: true
echo.
echo mesh:
echo   enabled: !MESH_ENABLED!
echo   transport: "unix_socket"
echo   runtime_dir: "data/runtime"
echo   lockfile_path: "/tmp/eidos.mesh.leader"
echo   heartbeat_sec: 2
echo   leader_timeout_sec: 6
echo   resource_token_ttl_sec: 30
echo.
echo evolution:
echo   enabled: true
echo   auto_forge: true
echo   sandbox_timeout_sec: 5
echo   sandbox_mem_mb: 256
echo.
echo logging:
echo   level: "INFO"
echo   format: "json"
echo   log_file: "data/eidos.log"
echo   rotate_max_mb: 10
echo   rotate_backups: 3
)
echo     [OK] config\eidos.yaml generado
echo.

REM ============================================================================
REM 11. Directorios de datos
REM ============================================================================

echo  Creando estructura de datos...
if not exist "%EIDOS_ROOT%\data\monologues" mkdir "%EIDOS_ROOT%\data\monologues"
if not exist "%EIDOS_ROOT%\data\capsules" mkdir "%EIDOS_ROOT%\data\capsules"
if not exist "%EIDOS_ROOT%\data\migrations" mkdir "%EIDOS_ROOT%\data\migrations"
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"
echo     [OK] Directorios listos
echo.

REM ============================================================================
REM 12. Descarga del cerebro local (si se pidió)
REM ============================================================================

if "!WANT_CORTEX!"=="1" (
    echo  Descargando Cerebro Local ^(Qwen 2.5 3B^)...
    "%VENV_DIR%\Scripts\python.exe" -c "import sys; sys.path.insert(0, '%EIDOS_ROOT%'); from eidos.cortex.manager import ModelManager; from pathlib import Path; mm = ModelManager(db_path=Path('%EIDOS_ROOT%/data/eidos.db'), models_dir=Path('%MODELS_DIR%')); mm.register(model_id='qwen2.5-3b-instruct', name='Qwen2.5-3B-Instruct', filename='qwen2.5-3b-instruct-q4_k_m.gguf', url='https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf', format='gguf', purpose='monologue', quantization='Q4_K_M'); print('Descargando (~2 GB)...'); path = mm.download('qwen2.5-3b-instruct'); print(f'OK: {path}')" 2>nul
    if errorlevel 1 (
        echo     [!] No se pudo descargar el modelo ahora.
        echo     Puedes hacerlo despues desde la UI ^(boton 'Descargar Cerebro'^).
    )
    echo.
)

REM ============================================================================
REM 13. Crear Launcher EIDOS.bat (sin ventana de CMD)
REM ============================================================================

echo  Creando Launcher ^(EIDOS.bat^)...

> "%EIDOS_ROOT%\EIDOS.bat" (
echo @echo off
echo REM EIDOS Launcher - doble clic para despertar EIDOS
echo setlocal
echo set "EIDOS_ROOT=%%~dp0"
echo set "EIDOS_ROOT=%%EIDOS_ROOT:~0,-1%%"
echo cd /d "%%EIDOS_ROOT%%"
echo.
echo REM Resolver Python portable
echo set "PYTHON_BIN=%%EIDOS_ROOT%%\.eidos_env\venv\Scripts\pythonw.exe"
echo if not exist "%%PYTHON_BIN%%" set "PYTHON_BIN=%%EIDOS_ROOT%%\.eidos_env\venv\Scripts\python.exe"
echo if not exist "%%PYTHON_BIN%%" (
echo     msg * "EIDOS no esta instalado. Ejecuta install.bat primero."
echo     exit /b 1
echo ^)
echo.
echo REM Matar instancias previas
echo taskkill /F /FI "WINDOWTITLE eq EIDOS*" >nul 2>&1
echo.
echo REM Iniciar servidor en background con pythonw (sin ventana)
echo set "LOG_FILE=%%EIDOS_ROOT%%\data\eidos_server.log"
echo if not exist "%%EIDOS_ROOT%%\data" mkdir "%%EIDOS_ROOT%%\data"
echo start "" /B "%%PYTHON_BIN%%" -m eidos web --port 8765 --host 127.0.0.1 > "%%LOG_FILE%%" 2^>^&1
echo.
echo REM Esperar a que el servidor este listo
echo echo Iniciando EIDOS...
echo set "READY=0"
echo for /L %%%%i in ^(1,1,30^) do (
echo     ping -n 1 -w 500 127.0.0.1 >nul
echo     powershell -Command "try { ^(Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/health' -UseBasicParsing -TimeoutSec 1^).StatusCode } catch { 0 }" 2>nul | findstr "200" >nul
echo     if not errorlevel 1 ^( set "READY=1" ^& goto :ready ^)
echo ^)
echo :ready
echo.
echo REM Abrir navegador
echo start "" "http://127.0.0.1:8765"
echo.
echo REM Notificacion
echo msg * "EIDOS esta listo. Cierra esta ventana para detenerlo."
echo.
echo REM Mantener vivo hasta que el usuario cierre
echo pause
echo taskkill /F /IM pythonw.exe >nul 2>&1
echo taskkill /F /IM python.exe >nul 2>&1
)
echo     [OK] EIDOS.bat creado
echo.

REM ============================================================================
REM 14. .env y LEEME
REM ============================================================================

if not exist "%EIDOS_ROOT%\.env" (
    > "%EIDOS_ROOT%\.env" (
echo OPENAI_API_KEY=
echo ANTHROPIC_API_KEY=
echo MINIMAX_API_KEY=
    )
)

> "%EIDOS_ROOT%\LEEME.txt" (
echo ===================================================================
echo                       ^|^|  EIDOS  ^|^|
echo           Tu mente artificial, portable y privada
echo ===================================================================
echo.
echo PARA EMPEZAR:
echo   1. Doble clic sobre  EIDOS.bat
echo   2. Se abrira tu navegador con la interfaz de EIDOS.
echo   3. !Habla con EIDOS!
echo.
echo PARA LLEVARTE A EIDOS A OTRO ORDENADOR:
echo   Copia toda esta carpeta a otro SSD/Pendrive y haz doble clic
echo   en EIDOS.bat. Tu memoria cognitiva viaja contigo.
echo.
echo AYUDA:
echo   - Manual completo: docs\USER_MANUAL.md
echo.
echo ===================================================================
)

echo.
echo  ============================================================
echo               !  EIDOS esta listo!  !
echo  ============================================================
echo.
echo  Para empezar:
echo    -^> Haz doble clic en EIDOS.bat en esta carpeta.
echo       Se abrira tu navegador con la interfaz de EIDOS.
echo.
echo  Para llevarte EIDOS a otro ordenador:
echo    Copia toda esta carpeta a otro SSD/Pendrive.
echo.
echo  Manual completo: docs\USER_MANUAL.md
echo.
pause
endlocal
