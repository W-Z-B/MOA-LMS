# Administrator's runbook

**Version 1.0, 6 October 2026,** checklist item 7.11. For the people who run the GSA LMS on its server: the
LMS administrators and GSA's IT Officer. It says how to install, upgrade, back up and restore the system,
look after terms and storage, answer the alerts, change the keys, and respond to an incident. Every command
here was checked against the code on branch `feature/finish-operations`; where something is not built yet,
this page says so and lists it under [Open actions](#open-actions).

For a developer's machine, read [SETUP.md](SETUP.md) instead. For what each role does on screen, read the
quick guides in [training/](training/).

## Contents

1. [The first hour of an incident](#the-first-hour-of-an-incident)
2. [Install](#install)
3. [Upgrade](#upgrade)
4. [Backup and restore](#backup-and-restore)
5. [Terms: closing, appeals and archiving](#terms-closing-appeals-and-archiving)
6. [Storage](#storage)
7. [Scheduled jobs](#scheduled-jobs)
8. [Monitoring](#monitoring), with what to do for each alert
9. [Keys](#keys)
10. [Incident response](#incident-response-1)
11. [Open actions](#open-actions)

Throughout, commands are run on the server from the LMS's folder (`/opt/gsa-lms` below), as a user that
may use Docker, with this short name for the production stack:

```sh
cd /opt/gsa-lms
alias dc='docker compose -f compose.yml -f deploy/compose.prod.yml'
# Once monitoring is installed, add it, so that every command sees the whole stack:
# alias dc='docker compose -f compose.yml -f deploy/compose.prod.yml -f deploy/monitoring/compose.monitoring.yml'
```

## The first hour of an incident

Use this when something is badly wrong: the LMS is down, data may have been seen by the wrong people, the
audit log alert has fired, or a key or password may be in someone else's hands.

1. **Write down the time** and what you saw, and keep writing: what you did, when, and why.
2. **Tell the others.** The other LMS administrator, GSA's IT Officer and, if personal data may be
   involved, the Data Protection Officer (DPO). Do not discuss details by WhatsApp or other personal chat.
3. **Keep the evidence before changing anything.** Copy the logs, then take a separate backup (both in
   [Incident response](#incident-response-1), step 2). A container's logs are lost when it is recreated,
   for example by `dc up -d` after a change. Do not restore over a database whose audit log has been
   altered.
4. **Stop the harm.** Close the account that is being misused, switch off the outside tool or the AI
   assistance involved, or take the LMS off line (`dc stop caddy`) if data is leaking now.
5. **Record it in the breach register the same day** if personal data may have been lost, changed, seen
   or made unavailable: Admin, **Breach register**, **Record a breach**. This alerts the administrators and
   the DPO. The DPO decides who must be told and when (see [Incident response](#incident-response-1)).
6. **Change what may be known to someone else**: the passwords and keys in [Keys](#keys).
7. **Do not close the incident** until it is contained, recorded, and its cause understood.

## Install

The server runs Ubuntu (a supported long-term release) with Docker Engine and its Compose plugin, Git, and
for backups `age` (BSD licence) and `rclone` (MIT). Keep its clock right with NTP (`chrony`, or
`systemd-timesyncd`): the audit log and every deadline depend on it. GSA's choice of host (item 7.04)
decides the firewall: only ports 80 and 443 should be reachable from outside, and SSH only from GSA's
network.

### 1. Get the code and write the settings

```sh
sudo git clone <repository-url> /opt/gsa-lms && cd /opt/gsa-lms
git checkout <release tag, for example v1.0.0>
cp .env.example .env && chmod 600 .env
sh scripts/gen-secret.sh          # prints DJANGO_SECRET_KEY and FIELD_ENCRYPTION_KEY: paste both into .env
```

Then edit `.env` (`.env.example` explains each line):

| Setting | Production value |
|---|---|
| `DJANGO_DEBUG` | `0` |
| `DOMAIN` | The LMS's address, for example `lms.gsa.edu.gy` |
| `DJANGO_ALLOWED_HOSTS` | `lms.gsa.edu.gy,localhost,api`: the address, plus `localhost` for the container's own health check and `api` for the monitoring |
| `PUBLIC_ORIGINS` | `https://lms.gsa.edu.gy` |
| `DB_PASSWORD` | A long random value (for example the output of `openssl rand -base64 32`) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | GSA's mail relay. Empty means email is only written to the log |
| `METRICS_TOKEN` | A long random value, if the monitoring will be installed |
| `HRMS_API_URL`, `HRMS_API_KEY`, `SRMS_API_URL`, `SRMS_API_KEY` | From the HRMS and SRMS administrators ([Keys](#keys)) |
| `TZ` | `America/Guyana` |

Leave the optional settings at their defaults unless GSA has decided otherwise. Settings that wait for a
decision by GSA are off by default and stay off until GSA says so: `TERMS_FROM_SRMS`, `AI_ENABLED`,
`SRMS_COMPETENCY_PUSH`, `MESSAGING_STUDENT_TO_STUDENT`, push notices (`VAPID_*`) and automatic captions
(`VIDEO_TRANSCRIBE_COMMAND`). Never set `DEMO_USER_PASSWORD` or `DEMO_TOTP_SECRET` on a real server.

**Before going further, put a copy of `.env` in the sealed envelope with the backup keys** ([Keys](#keys)).
Without `FIELD_ENCRYPTION_KEY`, no backup can be fully used: authenticator secrets, accommodation reasons
and other encrypted values cannot be read, and the audit log cannot be checked.

### 2. Start the stack

Three things in the production configuration need a change before go-live (see [Open actions](#open-actions)):
it still publishes Caddy on ports 8082 and 8445 rather than 80 and 443; it still mounts the `api` source
folder from the host over the image's code, in the API and the job worker; and nothing serves the admin
site's style sheets, so the admin site works but looks plain. Until the first two are fixed in the
repository, correct them in a file of this server's own, `deploy/compose.site.yml`, before the first start:

```yaml
# This server's corrections, until deploy/compose.prod.yml has them (runbook, "Open actions").
services:
  caddy:
    ports: !override ["80:80", "443:443"]
  api:
    volumes: !override ["files:/srv/files"]
  worker:
    volumes: !override ["files:/srv/files"]
```

and add `-f deploy/compose.site.yml` to the `dc` alias and to `COMPOSE` in the backup settings.

```sh
dc up -d --build                                   # database, API, job worker, web bundle, Caddy
dc exec api python manage.py migrate
dc exec api python manage.py seed --country GY     # roles, campuses, retention schedule, draft privacy notice
dc exec api python manage.py check --deploy --fail-level WARNING
curl -s https://lms.gsa.edu.gy/api/health/         # {"status": "ok", "database": true, "storage": true, "queue": true}
```

`seed` can be run again at any time: it adds what is missing and leaves alone what GSA has changed. The
production override builds the API without development tools and copies the web app into the volume Caddy
serves; Caddy then asks Let's Encrypt for a certificate (or uses `tls internal` or GSA's own certificate,
set in `deploy/Caddyfile.prod`).

### 3. The first administrator

```sh
dc exec api python manage.py createsuperuser
```

Sign in at the LMS's address with that account: it asks you to set up an authenticator app at once. This
account can do everything; keep it for emergencies, with its password in the sealed envelope. Give each LMS
administrator a named account of their own instead:

1. People's accounts come from the HRMS and SRMS records. Run the first exchange
   (`dc exec api python manage.py sync_ecosystem --staff`), then invite people from Admin,
   **People to invite** (or `dc exec api python manage.py invite_people --campus MRP`). Each person chooses
   a password through the emailed link.
2. Give roles in the admin site (`https://<address>/admin/`, open only after an authenticator code):
   **Role scopes**, **Add**, choose the account, the role and, for campus roles, the campus. Giving or taking
   a role is written to the audit log and signs that person out everywhere, so they sign in again with the
   new role. The admin site opens only for accounts with **Staff status**, and only after an authenticator
   code; keep that to the LMS administrators. Everyday administration is in the web app's **Admin** page.
3. Give the SRMS its key into the LMS; the key is shown once. Hand it over in person or through GSA's
   password manager:

   ```sh
   dc exec api python manage.py create_service_client --name srms --scopes sites:read
   ```
4. Enter the term calendar ([Terms](#terms-closing-appeals-and-archiving)) and make the orientation course
   (`dc exec api python manage.py seed_orientation`).
5. Set up [backups](#backup-and-restore) and [monitoring](#monitoring) before any real record is loaded.

## Upgrade

Only install a release whose pipeline is green. Every pull request and release tag runs the gates in
`.github/workflows/ci.yml`: lint and formatting, Django's checks including the production security check,
the API documentation check, the tests with at least 90% coverage, the licence policy and known
vulnerabilities for the API; lint, tests, build, page weight, licences and vulnerabilities for the web app;
the browser journeys with accessibility checks; a secret scan over the whole history; a build of every
production image; and the software bills of materials, which a release tag (`v*`) attaches to the release
with `THIRD-PARTY-NOTICES.md`.

1. **Choose the time.** Not during a quiz, a hand-in deadline or the nightly jobs ([Scheduled
   jobs](#scheduled-jobs)). Tell people the LMS will be away for about 15 minutes.
2. **Back up first**, and wait for `done`:
   `scripts/backup.sh` (as the backup user; [Backup and restore](#backup-and-restore)).
3. **Fetch and install:**

   ```sh
   git fetch --tags && git checkout <new tag>
   dc build
   dc stop worker
   dc run --rm api python manage.py migrate --noinput
   dc up -d
   dc exec api python manage.py seed --country GY        # adds any new roles or retention rules
   dc exec api python manage.py check --deploy --fail-level WARNING
   ```

4. **Check:** the health address answers `ok`; you can sign in; Admin, **Audit log**, **Check the chain
   now** says the log is whole; `dc logs --since 15m api worker` shows no errors; no alert has fired.
5. **If it goes wrong:** check out the previous tag, `dc build`, and restore the backup taken in step 2
   (`scripts/restore.sh --yes <stamp>`). Migrations are not undone one by one: the backup is the way back.

Read the release notes for anything to do by hand, such as a new setting in `.env.example`.

## Backup and restore

Each night `scripts/backup.sh` copies the database and the file store, encrypts both with `age` before
anything is written to disk, keeps them in a rotation, and copies them off site with `rclone`. The
objectives agreed for the LMS are a **recovery point of 24 hours** (at most a day's work lost) and a
**recovery time of 8 hours** (back in service within a working day).

### What a backup holds

A folder named by the time it was made in UTC, for example `/var/backups/gsa-lms/20261006T051500Z/`:

| File | What it is |
|---|---|
| `database.dump.age` | The whole database (`pg_dump` custom format), encrypted |
| `files.tar.age` | The whole file store: course files, submissions, evidence photographs, certificates, video, archives (not the `.health` folder), encrypted |
| `manifest.json` | The code's version, and the number of rows in the main tables and of files, for checking a restore |
| `SHA256SUMS` | Fingerprints of the three files above |

`.env` is **not** in the backup. Keep it apart, with the keys ([Keys](#keys)).

### Setting up the nightly backup

1. **Make the backup keys, away from the server.** On each key holder's own computer, not the server:

   ```sh
   age-keygen -o gsa-lms-backup-<name>.key     # prints "Public key: age1..."
   ```

   GSA names **two key holders** (for example the IT Officer and an LMS administrator), each with their own
   key, and keeps a **third copy off line** (printed, or on a USB stick, in the sealed envelope in GSA's
   safe). **The private keys never go on the server**: the server only encrypts, so whoever takes the server
   cannot read the backups.

2. **Put the public keys on the server**, one a line, in `/etc/gsa-lms/age-recipients.txt`. A backup can be
   read with any one of them.

3. **Name the off-site copy.** Configure an `rclone` remote for the backup user (`rclone config`), on storage
   in Guyana that GSA controls (another GSA server or a provider GSA has agreed with; the impact assessment
   says personal data stays in Guyana). Give that account only the folder for LMS backups.

4. **Write the settings** in `/etc/gsa-lms/backup.env` (mode 600, read by the scripts as shell lines):

   ```sh
   BACKUP_DIR=/var/backups/gsa-lms
   AGE_RECIPIENTS=/etc/gsa-lms/age-recipients.txt
   RCLONE_REMOTE=gsa-offsite:lms-backups
   BACKUP_METRICS_FILE=/var/lib/prometheus/node-exporter/lms_backup.prom
   COMPOSE="docker compose -f compose.yml -f deploy/compose.prod.yml"
   # Rotation (these are the defaults): newest of each of the last 14 days, 8 weeks and 12 months
   # BACKUP_KEEP_DAILY=14  BACKUP_KEEP_WEEKLY=8  BACKUP_KEEP_MONTHLY=12
   ```

   `BACKUP_METRICS_FILE` must be in the text-file folder of the host's `node_exporter`, which the monitoring
   reads (on Ubuntu's `prometheus-node-exporter` package, `/var/lib/prometheus/node-exporter/`).
   `BACKUP_ENCRYPT=gpg` with `GPG_RECIPIENT` is possible where GSA already uses GnuPG keys; `age` is the
   default.

5. **Run it once by hand** and read the last line, `done in N s`:

   ```sh
   /opt/gsa-lms/scripts/backup.sh
   ```

6. **Schedule it** in the backup user's crontab (`crontab -e`). The time is the server's own time zone:

   ```text
   15 1 * * *  /opt/gsa-lms/scripts/backup.sh >> /var/log/gsa-lms-backup.log 2>&1
   ```

The script stops with an error at the first thing that fails (the dump, the archive, the encryption, the
copy off site), and an unfinished backup never joins the rotation. Without `RCLONE_REMOTE` it fails on
purpose, because a backup on the same server is not a backup; `BACKUP_OFFSITE=0` allows it on a test stack
only. The rotation is applied on the server and off site in the same way, and it never empties either: the
off-site copy is never "synchronised", so a lost local folder cannot wipe it.

In the local drill on a test stack with about 40 MB of data, a backup took **26 seconds**.

### Restoring

A restore **replaces** the database and the file store of the stack it is run against. Tell people the LMS
is away; the job worker and Caddy are stopped while it runs.

1. Bring **one** private key to the server from a key holder (for example on a USB stick), and say where it
   is: `export AGE_IDENTITY=/root/restore.key`. Use the `.env` from the sealed envelope if the server's own
   was lost: the restore needs the same `FIELD_ENCRYPTION_KEY` as when the backup was made.
2. Check the backup without changing anything (it compares the fingerprints and says what it would do):

   ```sh
   scripts/restore.sh 20261006T051500Z                 # a backup in BACKUP_DIR
   scripts/restore.sh /mnt/usb/20261006T051500Z        # a backup folder anywhere
   scripts/restore.sh remote:20261006T051500Z          # fetched from the off-site copy first
   ```

3. Restore it: the same command with `--yes` first, for example `scripts/restore.sh --yes 20261006T051500Z`.
4. **Remove the key from the server** (`shred -u /root/restore.key`) and give it back.

The script then checks the restored system and stops with an error if any check fails:

- the API answers its health check with the database and the file store working;
- Django's own checks pass (`manage.py check`);
- the audit log's chain of fingerprints is whole (`manage.py verify_audit_chain`), which also proves the
  right `FIELD_ENCRYPTION_KEY` is in use;
- the number of accounts, people, course sites, submissions, quiz attempts and audit entries, and of files,
  are exactly those the manifest recorded when the backup was made, and no migration is missing.

Then it starts the whole stack. Work done after the backup was made is lost: tell teaching staff the time of
the backup so that they can ask for work handed in after it.

### The restore drill (each term)

A backup that has never been restored is a hope, not a backup. Once a term, a key holder runs the drill with
a backup **from the off-site copy**:

```sh
export AGE_IDENTITY=/root/restore.key
scripts/restore-drill.sh remote:<stamp>     # or with no argument: the newest backup on this server
```

It restores into a separate scratch stack beside production (Compose project `gsa-lms-drill`, its own
volumes, only the database and the API started, no ports published), runs every check above, times it
against the 8-hour objective, writes a report to `BACKUP_DIR/drills/<time>.txt`, and removes the scratch
stack. Production is never touched. `KEEP=1` leaves the scratch stack running to look at; remove it afterwards
with `docker compose -p gsa-lms-drill down -v`. The report ends `Result: passed` or `Result: FAILED`; file it
with the term's access review. In the local drill (test stack, about 40 MB), the drill **passed in 1 minute
40 seconds**. On the real server, with a term's video and submissions, expect longer; the objective is 8 hours.

## Terms: closing, appeals and archiving

Code: `api/terms/`. Course administrators keep the term calendar in Admin, **Terms** (`#/admin/terms`);
administrators can too, and auditors can read it.

**The calendar.** Each term has the code the SRMS gives its offerings (for example `2026-27-S1`), a name,
the first and last days of teaching, the **close date** (the last day work is handed in), and optionally its
own **grace** in days (empty means `TERM_GRACE_DAYS`, 2 by default). A course site belongs to the term
named by its term code.

**What happens to a site.** Its phase is worked out from the calendar whenever it is needed, so a site
closes at the exact moment, whether or not the nightly job has run:

| Phase | When | What people can do |
|---|---|---|
| Open | Until the end of the close date | Everything, as usual |
| Grace | For the grace days after the close date | Still takes work (late rules apply) |
| Closed | After the grace | Read-only for appeals. Only a course administrator or an administrator can change anything, and each change is audited as usual (`terms/guard.py`). Messages, forum subscriptions and certificate checks still work |
| Archived | Once the retention period for course sites has passed | Read-only for everyone; a read-only export is kept |

**For an appeal**, the course administrator makes the change on the closed site themselves (a mark, a
submission accepted); teaching staff cannot.

**The nightly job** `terms.lifecycle` ([Scheduled jobs](#scheduled-jobs)) records each term that has closed
and tells its teaching staff, then archives the sites of terms closed for longer than the retention rule
**course-sites** says (12 months proposed, to be confirmed by GSA in Admin, **Retention and disposal**;
`TERM_ARCHIVE_MONTHS` is used only if that rule is missing). Archiving destroys nothing: records are only
ever removed by a disposal run that one person proposes and a second approves.

**Archives** are zip files in the file store under `/srv/files/archives/<term code>/`: every record of the
site as the audit log shows it (encrypted values masked), every stored file, and a manifest; their SHA-256
is recorded. Download one from the term's list of sites on the Terms screen; each download is written to
the audit log.

**Each term, before the close date**, open the Terms screen and look for the notice "These term codes have
courses but no dates, so their courses never close": sites whose term code is not in the calendar **never
close**. Add the term (the notice has a button for each), or correct the site's code in the SRMS.

**From the SRMS.** `TERMS_FROM_SRMS` is off: the SRMS does not yet offer its calendar. When GSA and the SRMS
agree it, turning it on makes the nightly job take each term's code, name and dates from the SRMS, with the
close date `TERM_CLOSE_AFTER_DAYS` (28) after teaching ends; a close date or grace set in the LMS is kept.

## Storage

Everything people put up lives in one Docker volume, `files`, seen inside the containers as `/srv/files`:
course files, students' submissions, practical evidence (photographs and scans), feedback recordings,
certificates, lecture video and its copies, and the term archives. The database is in the volume `pgdata`.

```sh
df -h /var/lib/docker                          # room left on the disk that holds the volumes
dc exec api sh -c 'du -sh /srv/files/* | sort -h'   # what takes the room, folder by folder
```

- **Site allowances.** Each course site may keep up to `SITE_STORAGE_ALLOWANCE_MB` (2 GB) of course files;
  a course administrator can give one site more in **Storage allowances** (`#/admin/storage`). Teaching
  staff are warned at 80% and refused at 100%. Students' submissions and evidence do not count against it;
  they are limited per file (20 MB a hand-in, 15 MB a photograph, 50 MB a course file; Caddy refuses anything
  over 60 MB).
- **Video.** One upload may be up to `UPLOAD_LIMIT_VIDEO_MB` (1024 MB). The job worker makes a low copy (240
  lines, about 300 kbit/s), a standard copy (480 lines, about 1 Mbit/s) and a sound-only copy (64 kbit/s), and
  removes the original unless `VIDEO_KEEP_ORIGINAL` is set. As a guide, **an hour of lecture takes about
  600 MB** in all (about 135 MB low, 450 MB standard, 30 MB sound), and counts against the site's allowance.
  Converting uses the processor heavily for a while: several long videos at once can slow the pages.
- **Archives.** An archived site's zip holds a second copy of its files until the retention schedule's
  disposal removes the originals, so the store grows by roughly the size of each archived term until then.
  Plan the disk for at least two years of terms plus their archives.
- **Backups** are on another disk or server; see [Backup and restore](#backup-and-restore).
- **The `.health` folder** in the file store is where the health check writes and removes a small file every
  few seconds to prove the store takes writes. It is left out of backups and file counts. Do not remove it
  while the API runs (it is recreated if you do).
- **Logs.** Docker keeps container logs on the same disk. Limit them in `/etc/docker/daemon.json`
  (`"log-driver": "json-file", "log-opts": {"max-size": "50m", "max-file": "10"}`) and restart Docker in a
  quiet hour.

There is no disk-space alert yet ([Open actions](#open-actions)); look at `df -h` weekly until there is.

## Scheduled jobs

The job worker runs these by itself. **The scheduler reads each time as UTC** (checked against
Procrastinate 3.10, which the LMS uses), although several of the code's comments were written as if it were
Guyana time; Guyana is UTC−4 all year. Until that is corrected ([Open actions](#open-actions)), these are the
real times:

| Job | Schedule in the code | UTC | Guyana time | What it does |
|---|---|---|---|---|
| `integration.sync_staff` | `45 1 * * *` | 01:45 daily | 21:45 the evening before | Staff records from the HRMS |
| `integration.sync_srms` | `0 2 * * *` | 02:00 daily | 22:00 | Course sites and class lists from the SRMS |
| `insights.sync_outcomes` | `10 2 * * *` | 02:10 daily | 22:10 | Learning outcomes from the SRMS course outlines |
| `staffdev.completion_sweep` | `15 2 * * *` | 02:15 daily | 22:15 | Staff development completions worked out |
| `integration.push_marks` | `30 2 * * *` | 02:30 daily | 22:30 | Coursework totals to the SRMS |
| `integration.push_training` | `45 2 * * *` | 02:45 daily | 22:45 | Training completions to the HRMS |
| `insights.push_competency` | `50 2 * * *` | 02:50 daily | 22:50 | Competency results to the SRMS, only if `SRMS_COMPETENCY_PUSH` is on |
| `audit.verify_chain` | `30 3 * * *` | 03:30 daily | 23:30 | Checks the audit log's chain of fingerprints |
| `privacy.retention_purge` | `0 4 * * *` | 04:00 daily | 00:00 | Removes old sign-in attempts, password-link requests, certificate checks, notifications and AI-help records |
| `insights.early_alerts` | `15 4 * * *` | 04:15 daily | 00:15 | Early alerts about students who may need help |
| `terms.lifecycle` | `30 4 * * *` | 04:30 daily | 00:30 | Closes terms and archives old ones |
| `iam.access_review_reminder` | `0 6 * * 1` | 06:00 Mondays | 02:00 Mondays | Reminds the reviewers when the term's access review is due |
| `staffdev.required_training` | `30 6 * * *` | 06:30 daily | 02:30 | Required training: who must do what, and reminders |
| `approvals.chase_decisions` | `0 7 * * 1-5` | 07:00 weekdays | 03:00 weekdays | Chases decisions that have waited too long |
| `assessments.due_reminders` | `5 * * * *` | 5 past each hour | 5 past each hour | Reminders of work coming due |
| `notifications.daily_summary` | `0 17 * * *` | 17:00 daily | 13:00 | The daily summary email for those who chose one |

The jobs from 21:45 to 23:30 Guyana time run on the evening before the UTC date, so the night's exchanges
with the HRMS and SRMS finish before midnight in Guyana. The nightly backup is a `cron` line on the server,
not a job of the worker: it runs at 01:15 by the server's own clock, which on a server set to Guyana time is
after all of them. To run a job now, for example after fixing a fault:
`dc exec api python manage.py procrastinate defer integration.sync_srms`.

## Monitoring

Code: `api/config/observability.py`, `api/config/views.py`, `deploy/monitoring/`.

**What the LMS gives.**

- **A health address**, `/api/health/`, for anyone: `{"status", "database", "storage", "queue"}`, each yes or
  no. It answers 503 when the database or the file store fails, and `degraded` with 200 when no job worker
  has reported within `QUEUE_HEARTBEAT_SECONDS` (120).
- **Metrics** at `/api/metrics`, in the Prometheus format, only to a caller sending
  `Authorization: Bearer <METRICS_TOKEN>`; without `METRICS_TOKEN` the address does not exist, and Caddy
  refuses it from outside in any case. They count requests, times and server errors by route, unhandled
  errors by group, the job queue and workers, the HRMS and SRMS runs, and the audit chain's last check.
- **Logs** on standard output, one JSON object a line when `DJANGO_DEBUG=0`: `time`, `level`, `logger`,
  `message`, `request_id`, and for each request `method`, `route` (the address's name, never its ids),
  `status`, `duration_ms` and `user_id`. Never a query string, a body or a password.

**Installing the monitoring.** Prometheus and Alertmanager (both Apache 2.0) run as two more containers:

1. Put the same value as `METRICS_TOKEN` in `deploy/monitoring/metrics_token`, and the mail relay's password
   in `deploy/monitoring/smtp_password` (both mode 600; git ignores both).
2. Edit `deploy/monitoring/alertmanager.yml`: who receives alerts (at least both LMS administrators), the
   sender and the mail relay.
3. Install `node_exporter` on the server (Ubuntu package `prometheus-node-exporter`), listening on port 9100,
   for the backup's result and, later, the disk. Keep port 9100 closed to the outside in the firewall.
4. Start it: `docker compose -f compose.yml -f deploy/compose.prod.yml -f deploy/monitoring/compose.monitoring.yml up -d`,
   and change the `dc` alias to include the monitoring file.
5. Prometheus is not published. To look at it, tunnel to it from your own computer:
   `ssh -L 9090:<prometheus container address>:9090 <you>@<server>` (the address from
   `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <prometheus container>`),
   then open `http://localhost:9090`. **Status, Targets** must show `lms-api` and `lms-host` up; **Alerts**
   lists every rule.

**Finding something in the logs.** When someone reports an error, they see a **reference** (the request's
id). Every line of that request carries it:

```sh
dc logs --since 24h api | grep '"request_id": "<reference>"'
```

Every unhandled error carries a **group**: twelve characters naming the kind of fault (its type and the
function of the LMS's own code it came from), the same however often it happens. To see every occurrence:

```sh
dc logs --since 7d api | grep '"group": "<group>"'
dc logs --no-log-prefix --since 7d api | jq -cR 'fromjson? | select(.error.group == "<group>") | {time, request_id, message}'
```

The job worker logs the same way: use `worker` in place of `api`.

The sections below are the ones each alert names in its `runbook` annotation.

### The service is down

Alert **LmsDown** (critical): Prometheus has not been able to read `/api/metrics` for 5 minutes.

1. `dc ps`: is `api` running and healthy? Is `db`?
2. `curl -s https://<address>/api/health/`, and `dc logs --tail 200 api`.
3. If the database is down: `dc logs --tail 200 db`. A full disk is the usual cause (`df -h`).
4. Restart what has stopped: `dc up -d`. If the API keeps stopping, look for the error group in its log
   ([Errors](#errors)) and call the development team.
5. If the LMS answers people but the alert stays: the token in `deploy/monitoring/metrics_token` no longer
   matches `METRICS_TOKEN` (the API answers 401 and Prometheus counts that as down), or `api` was removed
   from `DJANGO_ALLOWED_HOSTS`.
6. If the database is damaged and will not start, restore the last backup ([Restoring](#restoring)).

### Slow pages

Alert **LmsSlowPages** (warning): for 15 minutes, the slowest 5% of requests have taken more than 2 seconds
(the objective of item 7.08 is 95% under 2 seconds).

1. Is the server busy? `docker stats --no-stream`. Video conversion in the worker uses the processor
   heavily; several long videos at once can slow the pages for a while.
2. Which pages? In Prometheus:

   ```text
   histogram_quantile(0.95, sum by (le, route) (rate(lms_http_request_duration_seconds_bucket[10m])))
   ```

3. Is the database waiting on something?

   ```sh
   dc exec db psql -U lms -d lms -c "select pid, now() - query_start as running_for, state, left(query, 80)
     from pg_stat_activity where state <> 'idle' order by 2 desc"
   ```

4. A whole class signing in or starting a quiz at once is slow for a minute or two by design (passwords are
   checked slowly on purpose): see `docs/performance.md`. If it lasts, raise `WEB_CONCURRENCY` (about two
   processes a processor core) and `dc up -d api`.

### Errors

Alert **LmsServerErrors** (warning): more than 1% of requests have failed with a server error for 10
minutes. Alert **LmsNewErrorGroup** (information): an error group not seen in the previous day has
appeared.

1. Find the groups: in Prometheus, `increase(lms_unhandled_errors_total[1h])` gives each `group`.
2. Find the occurrences in the log by group (above) and read the `error.trace` of one.
3. Send the development team the group, two or three request ids and the times. Do not paste whole log
   lines into email or chat: they may name an account.
4. If the errors began with an upgrade, consider going back ([Upgrade](#upgrade), step 5).

### The job queue

Alerts **LmsNoJobWorker** (critical, no worker for 10 minutes), **LmsJobBacklog** (a job has waited more than
15 minutes), **LmsFailedJobs** (one or more jobs have failed) and **LmsAuditChainNotChecked** (the nightly
check of the audit log has not run for two days, which usually means the worker was down).

1. `dc ps worker` and `dc logs --tail 200 worker`; start it with `dc up -d worker`.
2. See the failed jobs and their errors:
   `dc exec api python manage.py procrastinate shell list_jobs status=failed details`.
3. Once the cause is fixed, run a failed job again with
   `dc exec api python manage.py procrastinate shell retry <job id>`. A failed job stays counted, and the
   alert stays on, until it is retried or removed. Remove the failed jobs you have dealt with (here, those
   that ended more than three days ago):

   ```sh
   dc exec api python manage.py procrastinate defer procrastinate.builtin_tasks.remove_old_jobs \
     '{"max_hours": 72, "remove_failed": true}'
   ```

4. After **LmsAuditChainNotChecked**, run the check now (Admin, **Audit log**, **Check the chain now**, or
   `dc exec api python manage.py verify_audit_chain`).

### HRMS and SRMS runs

Alerts **LmsSiblingSyncFailing** (the latest run of a kind did not finish cleanly, for an hour) and
**LmsSiblingSyncStale** (no run of a kind for two days). The `kind` says which: staff from the HRMS, training
to the HRMS, coursework totals to the SRMS, outcomes from the SRMS, competency results to the SRMS.

1. Admin, **Integration runs**: open the run and read its errors. Each refused row names its record.
2. "Could not be reached": is the other system up? Is its address right in `.env`? A 401 or 403 means the
   key was changed on one side ([Keys](#keys)).
3. Rows refused one by one usually mean data to correct in the HRMS or SRMS: send the list to its
   administrator.
4. Run it again once fixed: `dc exec api python manage.py sync_ecosystem --staff`, `--push-marks`
   (optionally `--site <code>`) or `--push-training`.

The nightly copy of **course sites and class lists from the SRMS** (`integration.sync_srms`) is not yet
recorded as a run, so these alerts do not cover it ([Open actions](#open-actions)). Look for
`integration.sync_srms failed` in the worker's log if class lists seem out of date.

### Incident response

Alert **LmsAuditChainBroken** (critical): the audit log no longer matches its chain of fingerprints, so an
entry was changed or removed. Treat it as a security incident: follow [Incident response](#incident-response-1)
below, from step 1. The administrators and auditors have also been told in the LMS.

### Backup

Alert **LmsBackupMissing** (critical): no backup has finished successfully for more than 26 hours.

1. Read the end of `/var/log/gsa-lms-backup.log`: the line starting `FAILED` says what stopped it.
2. Usual causes: the disk is full; the stack was down; `AGE_RECIPIENTS` is missing or unreadable; the
   off-site copy could not be reached (the local copy is then made, but the backup counts as failed, on
   purpose); the cron line was removed.
3. If the log shows `done` but the alert stays: `BACKUP_METRICS_FILE` is not in node_exporter's text-file
   folder, or node_exporter has stopped (Prometheus, **Targets**, `lms-host`).
4. Once fixed, run `scripts/backup.sh` by hand and wait for `done`.

If node_exporter is not running at all, this alert cannot fire ([Open actions](#open-actions)): check the
backup log weekly until a rule for a missing metric is added.

## Keys

Every secret the LMS uses, who holds it, and how to change it. Keep the current `.env` and one copy of a
backup private key in a **sealed envelope in GSA's safe**, opened only by two people together, and write each
opening in the safe's log. Never put a key in email, chat, a ticket or the repository.

| Secret | Where it is | Holder |
|---|---|---|
| `DJANGO_SECRET_KEY` | `.env` | Server, sealed envelope |
| `FIELD_ENCRYPTION_KEY` | `.env` | Server, sealed envelope |
| Database password (`DB_PASSWORD`) | `.env`, and in PostgreSQL | Server, sealed envelope |
| SMTP password | `.env`; `deploy/monitoring/smtp_password` | Server |
| `METRICS_TOKEN` | `.env` and `deploy/monitoring/metrics_token` | Server |
| `HRMS_API_KEY`, `SRMS_API_KEY` | `.env` (keys the HRMS and SRMS issued to the LMS) | Server; the other system keeps only a fingerprint |
| Keys the LMS issued (for the SRMS) | Only a SHA-256 in the LMS; the key itself in the SRMS's settings | The SRMS |
| LTI platform key | In the database, encrypted with `FIELD_ENCRYPTION_KEY` | Server |
| `VAPID_PRIVATE_KEY` (push notices) | `.env` | Server |
| Backup keys (age) | Public keys on the server; private keys with the two holders and in the envelope | Two named people |
| First administrator's password | Sealed envelope | |

### DJANGO_SECRET_KEY

Signs sessions and password links. Changing it: make a new value with `scripts/gen-secret.sh`, put it in
`.env`, and `dc up -d --force-recreate api worker`. Expect that **everyone is signed out**, every invitation
and password link already sent stops working (send them again), and the **candidate numbers of
anonymous marking change** (they are made from this key, `assessments/rules.py`), so change it only when no
assignment with names hidden is being marked. Change it at once if it may be known to someone else.

### FIELD_ENCRYPTION_KEY

Encrypts authenticator secrets, accommodation reasons, calendar feed addresses, certificate check codes, the
LTI platform key and push subscriptions (`core/crypto.py`), and is the source of the audit chain's key, the
audit log's fingerprints of hidden values and the attendance check-in codes.

**It cannot be changed yet.** The LMS reads one key only: with a new one, every encrypted value stops
reading (no one could sign in with an authenticator code), and every audit entry already written fails the
chain check. Changing it needs two things that are not built ([Open actions](#open-actions)): reading with
the old key while writing with the new (a list of keys), with a command that re-encrypts every value; and a
chain check that knows which key sealed which entries. Until then:

- keep it secret and keep it in the envelope; a restore needs the key that was in use when the backup was
  made;
- if it may be known to someone else, that is an incident: record it, and ask the development team for the
  re-encryption step before anything else.

### The audit log and its chain

The audit log (`audit_auditlog`) records who did what, when, from where, and the before and after. **Never
change or remove an entry**, even to correct one; a correction is a new action that is itself recorded. The
database refuses to change or delete an entry (a trigger), and each entry carries a fingerprint (HMAC-SHA256)
of its own content and of the entry before it, under a key made from `FIELD_ENCRYPTION_KEY` that is never
stored in the database (`audit/chain.py`). Changing any entry, or removing one, breaks every fingerprint from
there on, and whoever did it cannot recompute them without that key.

The check walks every entry in order and finds the first that no longer fits; it also confirms that the
newest entry seen at the last good check is still there, so removing the latest entries shows too. It runs
every night (`audit.verify_chain`), on request (Admin, **Audit log**, **Check the chain now**, which is
itself audited), and from the command line (`dc exec api python manage.py verify_audit_chain`, which ends
with an error when the chain is broken). Each result is kept; a broken chain tells the administrators and
the auditor in the LMS, and the monitoring raises **LmsAuditChainBroken**.

### Database password

```sh
dc exec db psql -U lms -d lms -c "ALTER USER lms WITH PASSWORD '<new>'"
# then the same value as DB_PASSWORD in .env, and:
dc up -d --force-recreate api worker
```

### Service keys for the HRMS and SRMS

- **Keys the LMS holds** (`HRMS_API_KEY`, `SRMS_API_KEY`): ask the other system's administrator for a new
  key, put it in `.env`, `dc up -d --force-recreate api worker`, then ask them to withdraw the old one. Check
  the next run in Admin, **Integration runs**.
- **Keys the LMS issued**: `dc exec api python manage.py create_service_client --name srms --scopes sites:read`
  makes a new key for that name and the old one **stops at once**; the key is shown once. Agree a time with the
  SRMS administrator and hand it over in person. Each key's last use is shown in the admin site, **Service
  clients**; switch one off there to stop it at once.

Change them once a year, and at once when someone who knew one leaves or it may have been seen.

### METRICS_TOKEN

Make a new value (`openssl rand -base64 32`), put it in both `.env` and `deploy/monitoring/metrics_token`,
then `dc up -d --force-recreate api` and `dc restart prometheus`.

### The LTI platform key

The LMS signs what it sends to outside tools with its own RSA key pair, kept in the database encrypted with
`FIELD_ENCRYPTION_KEY` (`api/lti/keys.py`). To change it:

```sh
dc exec api python manage.py shell -c "from lti.keys import make_key; make_key()"
```

The new key signs from then on; the old one stays in the published key set (`/api/lti/jwks/`) so that
messages already sent still check, and tools need do nothing. There is no command yet to remove retired keys
from the set, and the change is not written to the audit log ([Open actions](#open-actions)); record it in
the change log. **Tools' own keys** are changed by the tool's maker. If the tool was registered with a
key-set address, the LMS keeps the set it read for an hour (`LTI_JWKS_CACHE_SECONDS`), so the maker should
publish a new key an hour before signing with it. If its key was pasted in, a course administrator pastes
the new one in Admin, **Outside tools**, at the moment the maker changes over.

### Push notice keys (VAPID)

Push notices to the installed app are off until both keys are set. Make them with
`dc exec api python manage.py vapid_keys`, put the two printed lines in `.env`, and
`dc up -d --force-recreate api worker`. Changing them means everyone who turned push on must turn it on
again, so change them only if the private key may have been seen.

### Backup keys (age)

When a key holder leaves or a private key may have been seen: make a new key pair as when setting up, replace
the old public key in `/etc/gsa-lms/age-recipients.txt`, and run a backup. Backups made before are still
encrypted to the old key: keep the old private key in the envelope until those have left the rotation (12
months for the monthly ones), or, if it was seen, treat the old backups as exposed and record it.

### Resetting someone's authenticator

When someone has lost the phone with their authenticator app, **check who they are as carefully as when the
account was first given**: in person with their GSA or national identity card, or by a video call with the
card and a call back to the number the HRMS holds. Never on the strength of an email or a message alone.
Then, in the admin site, **Authenticator devices**, delete their device: the removal is written to the audit
log as `authenticator_reset`. Write in the change log how you checked their identity. At their next sign-in
they set up a new authenticator, and the LMS tells them by notification and email that one was set up.
GSA to approve this procedure (item 2.5.7 of the security review).

## Incident response

For a suspected breach of personal data, an altered audit log, a key in the wrong hands, or an account
being misused.

1. **Start a record**: who found it, when, what was seen. Keep it until the incident is closed and filed.
2. **Keep the evidence** before anything else is changed:

   ```sh
   cd /opt/gsa-lms
   case=/root/incident-$(date -u +%Y%m%dT%H%MZ) && mkdir -m 700 "$case"
   dc logs --no-log-prefix --since 30d api worker caddy > "$case/logs.jsonl"
   # A backup of its own, kept out of the rotation and not copied off site:
   sed -e "s|^BACKUP_DIR=.*|BACKUP_DIR=$case/backup|" -e 's|^RCLONE_REMOTE=.*|RCLONE_REMOTE=|' \
     -e '/^BACKUP_METRICS_FILE=/d' /etc/gsa-lms/backup.env > "$case/backup.env"
   BACKUP_ENV_FILE="$case/backup.env" BACKUP_OFFSITE=0 scripts/backup.sh
   ```

   Export the audit log for the period from Admin, **Audit log** (spreadsheet) into the same folder. Do not
   restore, re-run migrations or clean anything up until these copies exist. A container's logs are lost
   when it is recreated, so copy them first.
3. **Record it in the breach register** if personal data may be involved: Admin, **Breach register**,
   **Record a breach** (or `POST /api/v1/privacy/breaches/`). Give when it was found, what happened, what data
   and whose, how many people, whether **students under 18** are among them, and the risk. Recording it
   alerts the administrators and the DPO at once.
4. **Contain it**, and record the time in the register (**Contained now**):
   - an account misused: in the admin site, untick **Active** on the account and remove its role scopes;
     the person's sessions end;
   - an outside tool involved: switch it off in Admin, **Outside tools** (every launch and every token stops);
   - AI assistance involved: `AI_ENABLED=0` in `.env`, `dc up -d --force-recreate api worker`;
   - a key or password seen: change it ([Keys](#keys));
   - data leaking now: take the LMS off line with `dc stop caddy` until it is contained.
5. **Decide who must be told.** The DPO decides, using the register. The draft data processing agreement
   (`docs/privacy/data-processing-agreement-draft.md`, clause 11) proposes that whoever runs the LMS tells
   GSA's DPO **within 24 hours** of becoming aware, so that GSA can tell the Data Protection Commissioner
   within the **72 hours** the summary of the Data Protection Act gives; GSA's legal adviser is to confirm both
   periods. Record when the Commissioner and the people affected were told (**Commissioner told now**,
   **People told now**).
6. **When the audit chain is broken**: do not restore over the database, and do not write to it more than
   the LMS must. Note the entry the check names. Run the drill on recent backups (`KEEP=1
   scripts/restore-drill.sh <stamp>`) to find the last backup whose chain is whole; compare the entries
   around the broken one between that copy and production. Who could reach the database at the time is the
   question to answer: the LMS has no way to change an entry, so it was done in the database directly, by
   someone or something holding its password.
7. **Close it** in the register (**Close**, which needs the containment time) once it is contained, the
   people who must be told have been, and the cause is understood. Keep the incident record and the copies
   with the register, for 7 years as the retention schedule proposes.

## Open actions

Found while writing this runbook; each is a change to the code or configuration, not to this page.

| Action | Why it matters | Where |
|---|---|---|
| Production ports 80 and 443; no host source mounted over the image; serve the admin site's style sheets | The override keeps the development ports (8082, 8445) and the `./api` mount; with `DJANGO_DEBUG=0` nothing serves `/static/` | `deploy/compose.prod.yml` (`ports: !override`, `volumes: !override` for `api` and `worker`); `collectstatic` in `api/Dockerfile` and a static file server |
| Make the scheduled times mean what the comments say (Guyana time), or correct the comments | The daily summary goes at 13:00, not 17:00; the approvals chase at 03:00, not 07:00 | `api/*/tasks.py` |
| Record the SRMS site and class-list copy as an integration run | A failing nightly copy raises no alert | `api/integration/tasks.py` `sync_srms`, `integration/runs.py` |
| A list of encryption keys (`MultiFernet`), a re-encryption command, and a chain check that knows each entry's key | Without them `FIELD_ENCRYPTION_KEY` can never be changed | `api/core/crypto.py`, `api/audit/chain.py` |
| A command to change the LTI platform key and remove retired ones, written to the audit log | Retired keys stay published for ever; the change leaves no audit entry | `api/lti/keys.py` |
| Alerts for disk space and for a missing backup metric (`absent(...)`) | A full disk stops the database; a stopped node_exporter hides a missing backup | `deploy/monitoring/alerts.yml` |
| Remove finished and dealt-with jobs regularly | Procrastinate keeps every job; the table grows for ever | A periodic `procrastinate.builtin_tasks.remove_old_jobs` |
| Changes made in the Django admin site to marks, submissions, memberships, sites, people and accounts | Only roles and authenticators are written to the audit log there | `api/*/admin.py` (use `AuditedAdmin`, or remove those models from the admin) |
| Logs kept off the server, and the clock checked | ASVS 1.7.2, 7.3.4 | Hosting (item 7.04) |

## Next review

At each release that changes the stack, the backups or the alerts, and after each restore drill. Owner:
the Technical Lead, with GSA's IT Officer.
