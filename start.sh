#!/bin/bash
# 民泊動画メーカー 起動スクリプト (Mac / Linux)
# ダブルクリックまたは ./start.sh で起動

set -e

cd "$(dirname "$0")"

if ! command -v docker &> /dev/null; then
    echo "====================================="
    echo " Docker がインストールされていません"
    echo " https://www.docker.com/products/docker-desktop/"
    echo " ↑ からインストールしてください"
    echo "====================================="
    read -rp "Enterキーで終了..."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "====================================="
    echo " Docker Desktop を起動してください"
    echo "====================================="
    read -rp "Enterキーで終了..."
    exit 1
fi

echo "民泊動画メーカーを起動中..."
echo "ブラウザで http://localhost:8501 を開いてください"
echo ""

docker compose up --build
