#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

read -r -s -p "HTTP(S) proxy URL for Telegram: " proxy_url
printf '\n'
case "$proxy_url" in
    http://*|https://*) ;;
    *) echo "A proxy URL must begin with http:// or https://" >&2; exit 1 ;;
esac

umask 077
temp_file=$(mktemp .env.bot.XXXXXX)
grep -v '^TELEGRAM_PROXY_URL=' .env.bot > "$temp_file" || true
printf 'TELEGRAM_PROXY_URL=%s\n' "$proxy_url" >> "$temp_file"
mv "$temp_file" .env.bot
chmod 600 .env.bot
unset proxy_url

docker compose up -d --build telegram-bot
docker compose ps telegram-bot
