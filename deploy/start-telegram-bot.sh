#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

read -r -s -p "Telegram BOT_TOKEN: " bot_token
printf '\n'
test -n "$bot_token"

umask 077
{
    printf 'BOT_TOKEN=%s\n' "$bot_token"
} > .env.bot
chmod 600 .env.bot
unset bot_token

docker compose --profile telegram-experimental up -d --build telegram-bot
docker compose ps telegram-bot
