# flowPay

A payments platform for Nigerian businesses. flowPay lets a registered business
collect money through **Paystack** or **Flutterwave**, keep a transaction ledger,
and pay out to saved beneficiaries — all scoped to the business, with API keys
and an audit trail.

> **Status:** pre-production. Local development and a single-web-process
> deployment are supported; see [Deployment](#deployment) before going live.

## Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.14 |
| Framework | Django 6.1.3 |
| API | Django REST Framework 3.18 + drf-spectacular (OpenAPI) |
| Database | PostgreSQL (`psycopg2-binary`) |
| Server | gunicorn (included in `requirements.txt`) |
| Gateways | Paystack, Flutterwave |

## Project layout

Django's package sits one level down, which is why commands use
`PYTHONPATH=.` and `config/manage.py`:

```
flowPay/
├── config/                  # Django project
│   ├── manage.py
│   └── config/              # settings.py, urls.py, wsgi.py
├── apps/                    # one Django app per domain
├── templates/               # project-wide templates (incl. admin overrides)
├── static/                  # source CSS/JS
├── gunicorn.conf.py         # production server config
├── Procfile                 # release + web processes
└── requirements.txt
```

## Apps

| App | Responsibility |
| --- | --- |
| `accounts` | Custom `User` (email-less username) and one-to-one `Account` profile. Signup, login, user list. |
| `businesses` | `Business` with `pending` → `active` / `suspended` lifecycle, webhook URL, owner, brand settings. |
| `api_keys` | Per-business API keys; only a SHA hash and a 12-char prefix are stored. |
| `payments` | `Payment` + ordered `PaymentEvent` history (initiate, webhook, callback, reconcile). |
| `transfers` | Bank list, account-name resolution, payouts to beneficiaries, verification. |
| `beneficiaries` | Saved payout recipients per business. |
| `providers` | Gateway registry (`Provider.code`, e.g. `paystack`). |
| `transactions` | Unified credit/debit ledger rows linked to payments or transfers. |
| `webhooks` | Signature-verified inbound gateway events (`WebhookEvent`). |
| `audit` | `AuditLog` plus the `audit(action, business=..., **metadata)` helper. |

## Routes

| URL | View | Notes |
| --- | --- | --- |
| `/signup/`, `/login/`, `/users/` | accounts | Session auth; `/users/` is the post-login landing page. |
| `/admin/` | Django admin | Business approval workflow lives here. |
| `/businesses/register/` | businesses | Register a business (`pending` by default). |
| `/businesses/<uuid>/` | businesses | Business settings. |
| `/businesses/<uuid>/keys/` | api_keys | Create a key (shown once). |
| `/businesses/<uuid>/keys/<int>/revoke/` | api_keys | Revoke a key. |
| `/payments/initiate/` | payments | `POST`, login required. |
| `/payments/callback/` | payments | Gateway return URL. |
| `/payments/<reference>/` | payments | Payment detail. |
| `/transfers/banks/` | transfers | Supported banks. |
| `/transfers/resolve/` | transfers | Resolve an account number. |
| `/transfers/initiate/` | transfers | `POST`, starts a payout. |
| `/transfers/<reference>/verify/` | transfers | Confirm payout status. |
| `/transactions/` | transactions | Ledger list. |
| `/webhooks/paystack/` | webhooks | HMAC-SHA512 `x-paystack-signature`. |
| `/webhooks/flutterwave/` | webhooks | `verif-hash` header. |
| `/api/schema/`, `/api/docs/` | drf-spectacular | OpenAPI schema and Swagger UI. |

There is no view mapped to `/`, so the bare domain returns 404 — start at
`/login/`.

## Local setup

Requires Python 3.14 and a running PostgreSQL server.

```bash
cd flowPay

# 1. Virtualenv and dependencies
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 2. Configuration
cp .env.example .env
# edit .env: SECRET_KEY, DB_NAME, DB_USER, DB_PASSWORD, DEBUG=True

# 3. Database
createdb flowpay
PYTHONPATH=. venv/bin/python config/manage.py migrate
PYTHONPATH=. venv/bin/python config/manage.py createsuperuser

# 4. Run
PYTHONPATH=. venv/bin/python config/manage.py runserver 8000
```

Two things trip people up:

- **Run from the repository root with `PYTHONPATH=.`.** Running from `config/`
  fails with `ModuleNotFoundError: No module named 'apps'`.
- `SECRET_KEY`, `DB_NAME` and `DB_USER` are read with `os.environ[...]` and have
  no defaults, so the app refuses to start until they are set.

### Sharing a local server

The dev server alone only listens on localhost. To expose it (for gateway
webhooks, for example):

```bash
ngrok http --domain=your-domain.ngrok-free.dev 8000
```

Add the hostname to `ALLOWED_HOSTS` and, if you POST over https behind the
tunnel, to `CSRF_TRUSTED_ORIGINS`. Both are comma-separated in `.env`.

## Environment variables

Everything is configured through the environment; `config/settings.py` also
reads `.env` from the project root, with real environment variables taking
precedence. See `.env.example` for a ready-to-copy template.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | yes | — | Django secret key. |
| `DEBUG` | no | `False` | `True` only locally. |
| `ALLOWED_HOSTS` | no | localhost, 127.0.0.1, two tunnel hosts | Comma-separated hostnames. |
| `CSRF_TRUSTED_ORIGINS` | prod https | empty | Comma-separated origins. |
| `DB_NAME`, `DB_USER` | yes | — | PostgreSQL database and role. |
| `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | no | `''`, `localhost`, `5432` | PostgreSQL connection. |
| `HTTPS_ONLY` | no | `False` | Enables SSL redirect, secure cookies and HSTS. |
| `SECURE_HSTS_SECONDS` | no | `3600` | HSTS max-age when `HTTPS_ONLY` is on. |
| `PAYSTACK_SECRET_KEY` | for payments | empty | Server-side Paystack key. |
| `FLUTTERWAVE_SECRET_KEY` | for payments | empty | Server-side Flutterwave key. |
| `FLUTTERWAVE_WEBHOOK_HASH` | for webhooks | empty | Verifies `verif-hash`; empty rejects all events. |
| `EMAIL_HOST` | for email | empty | SMTP host; empty prints mail to stdout. |
| `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | no | `587`, `''`, `''`, `True` | SMTP details. |
| `DEFAULT_FROM_EMAIL` | no | `flowPay <no-reply@flowpay.local>` | Sender for notifications. |

## Business approval workflow

1. A user registers a business at `/businesses/register/`; it is created with
   status `pending`.
2. Pending businesses appear in a **Pending businesses** module at the top of
   `/admin/`, oldest first.
3. In the admin, select businesses and run the **Approve** or **Suspend**
   action (or open one and change its status).
4. Approving sends a notification to the business email (falling back to the
   owner's email) and writes a `business.approved` audit entry; suspending
   writes `business.suspended`.

Only `pending`, `active` and `suspended` exist; approval is a manual,
superuser-only step. Mail uses the console backend unless `EMAIL_HOST` is set,
so in local development the approval message is printed to the server log
rather than delivered.

## Management commands

Verify pending payments against Paystack and settle any that succeeded but
never received a webhook:

```bash
PYTHONPATH=. venv/bin/python config/manage.py reconcile_payments
# single payment:
PYTHONPATH=. venv/bin/python config/manage.py reconcile_payments --reference=REF
# only payments older than N minutes (default 10):
PYTHONPATH=. venv/bin/python config/manage.py reconcile_payments --minutes=30
```

Run this on a schedule in production (every few minutes); it is the safety net
for dropped webhooks.

## Tests

```bash
PYTHONPATH=. venv/bin/python config/manage.py test apps
```

There are 46 tests, concentrated in the money paths: `webhooks`, `transfers`,
`payments`, `transactions` and `businesses`. The rest are still stubs.

Django creates a throwaway database, so the PostgreSQL role needs `CREATEDB`.
If you see `permission denied to create database`, grant it:

```sql
ALTER ROLE flowpay CREATEDB;
```

## Deployment

The repository ships `requirements.txt`, `gunicorn.conf.py` and a `Procfile`
with two processes:

```
release: PYTHONPATH=. python config/manage.py migrate --noinput
web: gunicorn config.wsgi:application -c gunicorn.conf.py
```

Any Procfile-based platform (Railway, Render, Heroku, Dokku) can run these
directly. For platforms that only offer a build command, use:

```bash
pip install -r requirements.txt
PYTHONPATH=. python config/manage.py collectstatic --noinput
```

### Pre-flight checklist

1. **Secrets:** generate a fresh `SECRET_KEY`; never reuse the dev one. Keep
   `.env` out of version control (it already is in `.gitignore`).
2. **`DEBUG=False`** and `HTTPS_ONLY=True`.
3. **`ALLOWED_HOSTS`** must list the real hostname(s) — the defaults are only
   localhost and tunnel domains.
4. **`CSRF_TRUSTED_ORIGINS`** must include the site origin
   (`https://your-domain`) or login POSTs fail with a 403.
5. **Database:** a managed PostgreSQL instance, plus `DB_*` variables. The
   `release` process runs migrations on every deploy.
6. **Email:** set `EMAIL_HOST` and friends. This is not optional —
   `manage.py check --deploy` **fails** with `mail.E001` while the console
   backend is in use.
7. **Static files:** `collectstatic` writes to `staticfiles/`. Django does not
   serve that directory in production, and WhiteNoise is **not** installed, so
   the host must serve it (or add WhiteNoise) or the admin and site CSS will
   404.
8. **Webhooks:** register `https://your-domain/webhooks/paystack/` and
   `https://your-domain/webhooks/flutterwave/` in each gateway dashboard, and
   set `FLUTTERWAVE_WEBHOOK_HASH`.
9. **Scheduling:** run `reconcile_payments` on a cron/scheduler.
10. **Version control:** this directory is not a git repository yet — run
    `git init` before connecting it to a platform.

Check production settings with:

```bash
PYTHONPATH=. DEBUG=False HTTPS_ONLY=True venv/bin/python config/manage.py check --deploy
```

The remaining warnings should be limited to HSTS tuning; anything about
`SECRET_KEY`, `DEBUG` or mail means a variable is missing.

## Known gaps

- `django-cors-headers` is installed and listed in `INSTALLED_APPS` but
  `CorsMiddleware` is **not** enabled, so no `CORS_*` setting takes effect.
- `djangorestframework-simplejwt` is installed in the venv but unused (not in
  `INSTALLED_APPS`), and is therefore not pinned in `requirements.txt`.
- Static file serving in production depends on the host or WhiteNoise.
- `/` has no view; consider redirecting it to `/login/`.
