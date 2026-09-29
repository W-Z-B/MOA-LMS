# Hosting on Railway (staging and demonstration)

The three GSA systems share one Railway project, "GSA Ecosystem". Each system keeps its own
database and its own application service; they reach each other over the project's private network.

> **Fictional data only.** Railway's regions are outside Guyana. Personal data of GSA students and staff
> must not be loaded here unless the transfer safeguards of the Data Protection Act 2023 are in place.
> Production hosting is decided separately (in-country), and uses the Compose stack in
> `deploy/compose.prod.yml`.

## What runs

| Service | Source | Notes |
|---|---|---|
| `lms-db` | `ghcr.io/railwayapp-templates/postgres-ssl:16` | PostgreSQL 16, volume at `/var/lib/postgresql/data`, private network only |
| `lms` | this repository, `deploy/railway/Dockerfile` | Caddy, gunicorn and the job worker in one container; volume at `/srv/files` |

Railway runs one container per service and attaches a volume to one service only, so the API, the
worker and Caddy share a container here. `start.sh` gives the volume to the `app` user, then `run.sh`
migrates, seeds the reference data and starts the three processes as that user.

## Service settings

| Setting | Value |
|---|---|
| Dockerfile path | `deploy/railway/Dockerfile` |
| Healthcheck path | `/api/health/` |
| Public domain target port | `8080` |
| Restart policy | on failure |

## Variables

Secrets are generated on the operator's machine and stored in Railway; none is kept in this repository.

| Variable | Value |
|---|---|
| `PORT` | `8080` |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}},${{RAILWAY_PRIVATE_DOMAIN}},healthcheck.railway.app` |
| `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY` | secrets (`scripts/gen-secret.sh`). Losing `FIELD_ENCRYPTION_KEY` makes encrypted identifiers unreadable |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | references to `lms-db`: `${{lms-db.PGHOST}}` and so on |
| `HRMS_API_URL`, `SRMS_API_URL` | `http://${{hrms.RAILWAY_PRIVATE_DOMAIN}}:8080`, `http://${{srms.RAILWAY_PRIVATE_DOMAIN}}:8080` |
| `HRMS_API_KEY`, `SRMS_API_KEY` | secrets; the HRMS and the SRMS register their hashes by reference |
| `SMTP_*` | empty: email is written to the log |

## First administrator

Preferred, because no password is stored anywhere:

```bash
railway ssh --service lms
su app -s /bin/bash -c "cd /app && python manage.py createsuperuser"
```

Alternative: set `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD` and optionally
`DJANGO_SUPERUSER_EMAIL` on the service and redeploy; remove the password variable after the first
sign-in. Administrators enrol an authenticator app at first sign-in.

## Build the same image locally

```bash
docker build -f deploy/railway/Dockerfile -t gsa-lms-hosted .
```
