@echo off
REM Dev: build frontend + run Rust backend
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."

REM Install frontend dependencies if missing
if not exist "web\node_modules\@vue\tsconfig" (
    echo Installing frontend dependencies...
    pushd web
    call npm install
    if errorlevel 1 ( popd & popd & exit /b 1 )
    popd
)

REM Check if frontend needs rebuild
set "NEED_BUILD=0"
if not exist "web\dist" (
    set "NEED_BUILD=1"
) else (
    REM Compare timestamps: find any src file newer than dist folder
    for /f "delims=" %%F in ('forfiles /p "web\src" /s /d +0 /c "cmd /c if @isdir==FALSE echo @path" 2^>nul') do (
        set "NEED_BUILD=1"
        goto :check_done
    )
    REM Also check config files
    for %%C in (web\index.html web\vite.config.ts web\tsconfig.json web\package.json) do (
        if exist "%%C" (
            for /f "delims=" %%A in ('forfiles /p "." /m "%%C" /d +0 /c "cmd /c echo @path" 2^>nul') do (
                set "NEED_BUILD=1"
                goto :check_done
            )
        )
    )
)
:check_done

if "!NEED_BUILD!"=="1" (
    echo Frontend changed, rebuilding...
    pushd web
    call npm run build
    if errorlevel 1 ( popd & popd & exit /b 1 )
    popd
) else (
    echo Frontend up to date, skipping build.
)

REM Run
cargo run %*
popd
