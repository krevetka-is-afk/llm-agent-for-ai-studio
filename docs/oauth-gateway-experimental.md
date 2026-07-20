# OAuth Gateway (experimental)

Прототип находится в `src/experimental/oauth/`, не подключён к Web UI или
Telegram и включается только отдельным Compose profile.

```bash
PYTHONPATH=src uv run --env-file .env.gateway python -m experimental.oauth.app
```

Минимальная конфигурация:

```dotenv
YC_OAUTH_CLIENT_ID=...
YC_OAUTH_CLIENT_SECRET=...
YC_OAUTH_REDIRECT_URI=https://<domain>/yc/oauth/callback
YC_OAUTH_SCOPES=openid profile email
YC_TOKEN_ENCRYPTION_KEY=<Fernet key>
YC_OAUTH_CALLBACK_HOST=0.0.0.0
YC_OAUTH_CALLBACK_PORT=8080
YC_OAUTH_DB_PATH=/data/refresh_tokens.db
OAUTH_GATEWAY_SHARED_SECRET=<random shared secret>
```

Production callback требует HTTPS reverse proxy. Compose публикует Gateway только
на localhost; пример Caddy-конфигурации находится в
`deploy/Caddyfile.bot-staging`.
