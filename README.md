# PathGen

PathGen is a Django monolith for an adaptive Grade 7 mathematics learning study. The canonical product requirements live in `../pathgen2.0docs/documentation/`; this README contains setup and verification commands only.

## Supported runtimes

- Python 3.12–3.14 (Python 3.12 is the CI baseline)
- Node.js 22–24 and npm 10–11
- PostgreSQL

## Local setup

```text
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock
npm ci
copy .env.example .env
```

Fill the blank values in `.env` with local-only values. `DATABASE_URL` must use a `postgres://` or `postgresql://` URL. Keep `GROQ_MODEL=gpt-oss-120b` and `EMBEDDING_MODEL=text-embedding-3-small` unchanged.

## Commands

```text
python manage.py check --settings=config.settings.local
python manage.py runserver
npm run build
python manage.py collectstatic --noinput --settings=config.settings.production
pytest
```

The liveness endpoint is `GET /health/`. Generated frontend files are written to ignored `static/dist/`; collected deployment files are written to ignored `staticfiles/`.

## Railway

`Procfile` is the V1 production start-command source of truth. Railway supplies environment variables and `$PORT`. Production settings fail closed when required variables are blank or invalid. Migrations remain an explicit release step and curriculum seeding is never implicit.
