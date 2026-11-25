"""Gunicorn configuration for flowPay.

The project keeps its Django package one level down in ``config/`` (so that
``manage.py`` lives at ``config/manage.py``). That means both the repository
root (for ``apps.*``) and ``config/`` (for ``config.settings``) must be
importable, which is what ``pythonpath`` below handles.

Run with:  gunicorn config.wsgi:application -c gunicorn.conf.py
"""
import os

# Hosts usually inject $PORT; fall back to 8000 for local runs.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Repo root first (apps.*), then config/ (config.wsgi / config.settings).
pythonpath = ".,config"

# Deliberately small: hosts size the box, not the core count of the build
# machine. Override with WEB_CONCURRENCY.
workers = int(os.environ.get('WEB_CONCURRENCY', '3'))
threads = int(os.environ.get('GUNICORN_THREADS', '2'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5

# Platform log collectors read stdout/stderr.
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
