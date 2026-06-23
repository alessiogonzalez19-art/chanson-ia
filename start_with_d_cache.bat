@echo off
setlocal
REM Configure caches on D: when available, otherwise inside the project.
set "CACHE_ROOT=%CD%\.local_models"
set "TEMP_ROOT=%CD%\.local_temp"
if exist "D:\" (
  set "CACHE_ROOT=D:\studio_ia_models"
  set "TEMP_ROOT=D:\studio_ia_temp"
)

echo Configuration des caches vers %CACHE_ROOT%...

if not exist "%CACHE_ROOT%" mkdir "%CACHE_ROOT%"
if not exist "%CACHE_ROOT%\transformers" mkdir "%CACHE_ROOT%\transformers"
if not exist "%CACHE_ROOT%\datasets" mkdir "%CACHE_ROOT%\datasets"
if not exist "%CACHE_ROOT%\torch" mkdir "%CACHE_ROOT%\torch"
if not exist "%TEMP_ROOT%" mkdir "%TEMP_ROOT%"

set "HF_HOME=%CACHE_ROOT%"
set "TRANSFORMERS_CACHE=%CACHE_ROOT%\transformers"
set "HF_DATASETS_CACHE=%CACHE_ROOT%\datasets"
set "TORCH_HOME=%CACHE_ROOT%\torch"
set "MODELS_CACHE=%CACHE_ROOT%"
set "STUDIO_TEMP=%TEMP_ROOT%"
set "TEMP=%TEMP_ROOT%"
set "TMP=%TEMP_ROOT%"
set "TMPDIR=%TEMP_ROOT%"

echo Caches configures:
echo    HF_HOME=%HF_HOME%
echo    TRANSFORMERS_CACHE=%TRANSFORMERS_CACHE%
echo    TEMP=%TEMP%
echo.
echo Demarrage des services...
echo.

call venv\Scripts\activate.bat

echo [1/2] Demarrage du backend FastAPI...
start "Backend FastAPI" cmd /k "venv\Scripts\activate.bat && python -m uvicorn api.routes:app --host 0.0.0.0 --port 8000 --no-use-colors"

timeout /t 3 /nobreak >nul

echo [2/2] Demarrage du worker Celery...
start "Celery Worker" cmd /k "venv\Scripts\activate.bat && python -m celery -A workers.celery_app worker --loglevel=info --pool=solo"

echo.
echo Studio IA demarre:
echo    Backend: http://localhost:8000
echo    Docs API: http://localhost:8000/docs
echo    Cache: %CACHE_ROOT%
echo.
pause
