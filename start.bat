@echo off
chcp 65001 >nul
REM 民泊動画メーカー 起動スクリプト (Windows)
REM ダブルクリックで起動

cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
    echo =====================================
    echo  Docker がインストールされていません
    echo  https://www.docker.com/products/docker-desktop/
    echo  ↑ からインストールしてください
    echo =====================================
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo =====================================
    echo  Docker Desktop を起動してください
    echo =====================================
    pause
    exit /b 1
)

echo 民泊動画メーカーを起動中...
echo ブラウザで http://localhost:8501 を開いてください
echo.

docker compose up --build
pause
