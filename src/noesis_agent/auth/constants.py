from __future__ import annotations

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
BASE_URL = "https://chatgpt.com/backend-api/wham"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email offline_access"
REDIRECT_URI = "http://localhost:1455/auth/callback"
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 1455
TOKEN_REFRESH_BUFFER_MS = 30_000
USER_AGENT = "noesis-agent/0.1.0"
