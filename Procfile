# flowPay process definitions (Heroku/Railway/Render style).
# PYTHONPATH=. makes apps.* importable while manage.py lives in config/.
release: PYTHONPATH=. python config/manage.py migrate --noinput
web: gunicorn config.wsgi:application -c gunicorn.conf.py
