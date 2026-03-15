"""
Gunicorn configuration for production deployment.

Start with:
    gunicorn --config gunicorn_config.py dm_web:app

Or via the Render start command:
    gunicorn --config gunicorn_config.py dm_web:app
"""

import os

# Flask-SocketIO requires async worker
worker_class   = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
workers        = 1          # eventlet is single-process async — do NOT increase
threads        = 1

# Bind
bind           = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# Timeouts — long because Gemini calls can take 10-20s
timeout        = 120
keepalive      = 5

# Logging
accesslog      = "-"        # stdout (Render captures it)
errorlog       = "-"
loglevel       = os.environ.get("LOG_LEVEL", "info")

# Restart workers after this many requests to prevent memory bloat
max_requests        = 1000
max_requests_jitter = 100
