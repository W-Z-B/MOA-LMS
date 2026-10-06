# Performance and the load test (item 7.08)

The gold standard asks for 95% of pages under 2 seconds on campus and under 5 seconds on a 2 Mbps line,
common pages under 500 KB, and a load test of a whole class sitting one quiz at once. This page records the
load test, what it found and what was changed, and how to run it again.

## The scenario

`loadtest/locustfile.py` (Locust, MIT, a development tool that never ships; it runs from its own image)
with the data from `python manage.py seed_load --fictional --students 90`:

- **60 students sit one quiz at once**: all sign in within about five seconds, open Home and their course,
  start the same 20-question quiz (five questions a page), save each answer after a pause of 3 to 10
  seconds, turn the pages, hand in and look at the result; then carry on as below.
- **30 other students use the course as usual**: Home, To do, the course contents, two pages, the
  announcements, notifications and the calendar, with the same pauses.
- **The lecturer watches**: signs in with an authenticator code and opens the attempts list and the
  gradebook every few seconds.

Every request is named by what it is, so the results group by page, not by address.

## Where it ran

The production configuration (`compose.yml` with `deploy/compose.prod.yml`): gunicorn behind Caddy over
TLS, PostgreSQL 16, the job worker, `DJANGO_DEBUG=0`, JSON logs. One Windows workstation running Docker
Desktop (28 logical processors, 16 GB for Docker), **shared with other build agents' test stacks running at
the same time**, so the figures are cautious: a dedicated server does better.

## Results

Run of 6 October 2026, 5 minutes, 91 users, 18,112 requests, **no failures**. Times in milliseconds.

| Request | Requests | Median | 95th percentile | 99th percentile |
|---|---:|---:|---:|---:|
| quiz: save an answer | 1,200 | 73 | 240 | 350 |
| quiz: next page | 180 | 92 | 290 | 350 |
| quiz: hand in | 60 | 330 | 540 | 810 |
| quiz: review | 60 | 130 | 390 | 420 |
| quiz: start (all 60 within seconds) | 60 | 1,300 | 1,800 | 2,400 |
| quizzes (the course's quiz list) | 61 | 1,400 | 2,100 | 2,500 |
| sign in (all 91 within five seconds) | 91 | 1,700 | 2,300 | 2,800 |
| home | 2,110 | 500 | 1,500 | 2,100 |
| to do | 2,011 | 230 | 880 | 1,300 |
| course contents | 2,001 | 250 | 860 | 1,300 |
| a page | 3,985 | 200 | 770 | 1,100 |
| announcements | 1,983 | 99 | 660 | 940 |
| notifications | 1,979 | 63 | 590 | 860 |
| calendar | 1,974 | 160 | 690 | 950 |
| lecturer: attempts list | 42 | 220 | 640 | 1,000 |
| lecturer: gradebook (90 students) | 42 | 280 | 720 | 790 |
| **All requests** | **18,112** | **200** | **990** | **1,800** |

**The 95th percentile of all requests is 0.99 seconds**, inside the 2-second objective. The slowest
requests are the moment the whole class signs in and starts the quiz together: password checking is
deliberately slow (PBKDF2, Django's default), so 91 sign-ins in five seconds queue for a second or two.
Once the class is in, saving an answer takes a quarter of a second at the 95th percentile.

## What the test found and what was changed

| Finding | Before | After | Change |
|---|---|---|---|
| The gradebook read each student's work one by one | 1,449 queries, 4.9 s for 90 students | 27 queries, 0.12 s | `assessments/preload.py`: the class's submissions, attempts, overrides, extensions, accommodations, observations, forum marks and SRMS transfers read once; used by the gradebook, its spreadsheet and the coursework send |
| The attempts list checked the lecturer's role for each attempt | 562 queries for 185 attempts | 16 | the role worked out once for the list |
| Each question's latest version read one at a time (quiz list, quiz start) | 35 and 45 queries for 20 questions | 16 and 26 | one query for all the quiz's questions |
| Handing in wrote each answer's mark separately | 20 updates | 1 | one bulk update |
| gunicorn sync workers queued requests behind database waits | p95 1.8 s (4 processes) | p95 1.3 s, then 0.99 s | 4 threads in each process (`GUNICORN_THREADS`) |
| An occasional 502 when Caddy reused a connection gunicorn had just closed | 1 in 16,000 | none | gunicorn keeps connections 75 s, Caddy 60 s |

`assessments/test_query_counts.py` keeps these from coming back: the gradebook, its spreadsheet and the
attempts list must make the same number of queries for 2 students as for 13, and quiz start, hand-in and
list the same for 2 questions as for 12.

The full run before the changes (run 1, with the same machine also running a test suite) had a 95th
percentile of 2.5 seconds overall, the gradebook at 3.6 seconds and saving an answer at 4.7 seconds.

## Page weight

The web app's shell is checked on every build (`npm run check:bundle`, budget 160 KB) and every screen
loads lazily; API answers for the pages above are a few kilobytes. On a 2 Mbps line, 160 KB takes about
0.7 seconds before the first answer.

## Running it again

```sh
# 1. A production-like stack with fictional data (never on a database with real records).
docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build db api worker caddy
docker compose -f compose.yml -f deploy/compose.prod.yml exec api python manage.py migrate
docker compose -f compose.yml -f deploy/compose.prod.yml exec \
  -e LOAD_USER_PASSWORD=... -e LOAD_TOTP_SECRET=... api python manage.py seed_load --fictional --students 90
# 2. Locust from its own image, on the stack's network, against Caddy (the cookies are Secure).
docker run --rm --network <project>_default --add-host lms.localhost:<caddy address> \
  -e LOAD_USER_PASSWORD=... -e LOAD_TOTP_SECRET=... -v "$PWD/loadtest:/mnt/locust" \
  locustio/locust:2.37.10 -f /mnt/locust/locustfile.py --headless -u 91 -r 20 -t 5m \
  --host https://lms.localhost --csv /mnt/locust/results
```

Run it again after any change to quizzes, the gradebook or Home, and on GSA's own server before go-live,
with `WEB_CONCURRENCY` set to about two processes a core.
