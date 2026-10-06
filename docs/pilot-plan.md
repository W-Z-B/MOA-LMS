# GSA LMS: pilot plan

**Version 1.0, 6 October 2026, draft for GSA's review.** For: the Principal, the heads of department, the
pilot lead, the department champions, the course administrators, the lecturers of the pilot courses and the
development team.

This plan answers checklist item **7.19**: a pilot with a few courses for one term before all courses move to
the LMS. It says which courses, who does what, what happens each week, how success is measured, and how GSA
decides whether to move every course.

## 1. Purpose

The pilot runs a small number of real courses on the LMS for one whole term, with real lecturers and students,
so that GSA can see whether it works in daily teaching before every course depends on it. In particular it
shows:

- whether lecturers can build and teach a course in it without outside help, after the training;
- whether students use it every week, at both campuses, on their own phones;
- whether practical work in the field and work on a poor connection are recorded properly;
- what help people need, so the help pages, training and support can be put right before all courses move.

The pilot is also how GSA proves the plan's quality bar **"Used"**: *every course in the pilot has its
outline, weekly content and assessment in the LMS by week two of term, and students in it log in weekly.*

### Before the pilot can start

The pilot uses real student records, so these must be done first:

| Must be done | Where it is recorded |
|---|---|
| Acceptance testing passed and signed for Release 1 (item 7.18) | `docs/acceptance/README.md`, sign-off table |
| The data protection impact assessment signed by the DPO and the Principal | `docs/privacy/dpia.md`, section 9 |
| The live system running in Guyana, backed up daily, with the restore drill done | The hosting record |
| The pilot term's dates fixed (decision D9) | The plan's decisions table |
| Staff and student accounts coming from the HRMS and the SRMS for the pilot courses | Integration runs in the administration console |

## 2. Which courses

### How to choose them

About six courses, chosen so that between them they test every kind of teaching GSA does:

1. Courses from **at least three departments**.
2. **Both campuses**, with at least one course taught at **Essequibo**.
3. At least one course with **field practicals** (practical tasks, field checklists and the logbook).
4. At least one course with a **large class**, ideally the largest first-year class.
5. At least one course taught by a lecturer **new to online teaching**.
6. At least one course with **existing material to bring in** (from shared drives, Google Classroom or paper).
7. Lecturers who **agree** to take part, and whose head of department supports it.
8. No course where a failure would be hard to recover from (for example a final-year course whose marks are
   needed early for graduation).

### A suggested set

The course codes below are the **demonstration courses, used as examples only**. GSA replaces them with the real
courses it chooses.

| # | Example course (to be replaced by GSA) | Campus | Why it is in the set |
|---|---|---|---|
| 1 | AGR101-2026-27-S1-MRP Introduction to Crop Production | Mon Repos | Field practicals, logbook and competency; a large first-year class |
| 2 | AGR101-2026-27-S1-ESQ Introduction to Crop Production (the Essequibo offering) | Essequibo | Essequibo, phones on a poor connection, practicals on the farm plot |
| 3 | AGR205-2026-27-S1-MRP Soil Science and Fertility | Mon Repos | Marking with rubrics, late work, marks sent to the SRMS |
| 4 | AGR102-2026-27-S1-MRP Soils and Plant Nutrition | Mon Repos | Built from last year's course, with existing material brought in |
| 5 | A course from a second department (to be chosen) | Either | Taught by a lecturer new to online teaching |
| 6 | A course from a third department (to be chosen) | Either | Mostly classroom teaching, with quizzes, forums and messages |

Every student on a pilot course uses the LMS for that course only. Their other courses carry on as now.

## 3. Roles

| Role | Who | What they do | Time |
|---|---|---|---|
| **Pilot lead** | A senior member of the academic staff named by the Principal | Runs the pilot: chairs the weekly check-in, keeps the risk table, writes the mid-term review and the end-of-term report, recommends go or no-go | About half a day a week |
| **Department champions** | One lecturer in each pilot department, named by the head of department (see `docs/training/champion-role.md`) | First person to ask in the department; checks each pilot course against the course-site standard in week 2; runs the timed tasks; brings problems to the check-in | About two hours a week |
| **Course administrators** | The course administrators at Mon Repos and Essequibo | Run the training sessions; set up accounts; bring in existing material with the development team; answer help requests within two working days; run the adoption report | As needed; help requests daily |
| **Development team** | The developers of the LMS | Fix failures; watch speed and the system's health; produce the figures for the check-in; attend each check-in | One person at each check-in; fixes as needed |
| **Lecturers of the pilot courses** | The lecturers who agreed | Build and teach their course in the LMS; tell their champion what goes wrong | Their normal teaching, plus the training |
| **Heads of department** | The heads of the pilot departments | Support their lecturers; approve staff-development requests in the LMS; attend the mid-term review and the go/no-go meeting | A few hours in the term |

## 4. Timeline

The pilot term is taken as 14 weeks. "Week −8" means eight weeks before the first day of term.

| When | What happens | Who |
|---|---|---|
| Week −8 | The Principal names the pilot lead. Heads of department name champions. The pilot courses are chosen and their lecturers agree. | Principal, heads of department |
| Week −7 | Acceptance testing finished and signed. The impact assessment signed. The live system set up in Guyana. | Pilot lead, DPO, development team |
| Week −6 | **Accounts:** pilot lecturers invited ("People to invite"), each sets a password and an authenticator. **Training session 1** for each department, in small groups (`docs/training/session-plan.md`). | Course administrators, administrator |
| Week −5 | **Training session 2** (handing in and marking, timed). Lecturers gather existing material into one folder per module, as `docs/migration-guide.md` describes. | Course administrators, lecturers |
| Week −4 | **Training session 3.** **Bringing in existing material:** the course administrator runs `import_folder` with `--dry-run`, then for real; every imported file arrives as a draft with its licence "Not yet known". | Course administrators, development team |
| Weeks −3 and −2 | Lecturers **build their course sites to the course-site standard** (`docs/training/course-site-standard.md`): they check the licence of each imported file, publish what is ready, set the term's assignments, quizzes and classes. Weekly follow-up clinic. | Lecturers, champions |
| Week −1 | Champions check each site against the standard and tick the list. Students on the pilot courses are invited. The orientation course is ready. The student quick guide is printed. The help-request rota for course administrators is set. | Champions, course administrators |
| Week 1 | **Orientation.** Students sign in for the first time and are put on "Getting started with the GSA LMS". Each pilot lecturer spends ten minutes of the first class showing students the course and asking them to finish the orientation that week. First weekly check-in. | Lecturers, course administrators |
| Week 2 | **The course-site standard check.** Each champion checks that each pilot course has its outline, weekly content and assessment in the LMS, and records the result. Anything missing is put right by the end of the week. | Champions, pilot lead |
| Weeks 3 and 4 | First hand-ins and marking. **Timed tasks:** each champion times five students handing in and the lecturer marking and returning five pieces of work. Page times checked at Essequibo. | Champions, development team |
| Weeks 2 to 14 | **Weekly check-in** (section 6). | Pilot lead and the check-in group |
| Week 7 | **Mid-term review** (section 6). | Pilot lead, heads of department |
| Weeks 8 to 13 | Teaching continues. At least one field practical observed with the LMS on the farm plot. Coursework sent to the SRMS as GSA's calendar requires. | Lecturers |
| Week 14 | End of term. The adoption report is run for the whole term. A short questionnaire to pilot lecturers and students. | Course administrators |
| Weeks +1 and +2 | **End-of-term report** and the **go/no-go meeting** (section 8). | Pilot lead, Principal |

## 5. Success measures

The targets come from the plan's quality bars. Where the plan sets no number, the target shown is **proposed**
and GSA should confirm it before the pilot starts.

| Measure | Target | How it is measured | When |
|---|---|---|---|
| Each pilot course has its outline, weekly content and assessment in the LMS by week two ("Used") | Every pilot course | The champion's course-site standard check, confirmed by the adoption report | Week 2 |
| Students in each pilot course log in weekly ("Used") | Proposed: at least 90% of students sign in at least once in each teaching week, and no course below 80% | The adoption report (sign-ins by course and week) | Weekly, and for the whole term |
| A student hands in work unaided in under two minutes ("Usable by everyone") | Proposed: at least 9 in 10 timed students | Timed tasks: five students a course, stopwatch from Home to the receipt | Weeks 3 and 4 |
| A lecturer marks and returns a submission in under three minutes ("Usable by everyone") | Proposed: at least 9 in 10 timed pieces of work | Timed tasks: five pieces of work a lecturer, stopwatch from Home to release | Weeks 3 and 4 |
| Pages open in under 2 seconds on campus and under 5 seconds on a 2 Mbps line ("Fast") | 95% of pages | The development team's page timings on the live system, with spot checks by stopwatch at Essequibo | Weekly |
| No work lost to a dropped connection ("Dependable", "Works in the field") | None | Every report of lost work, from help requests or the check-in, is checked against the audit log (every hand-in, quiz answer, observation and logbook entry is recorded with its time) | Weekly |
| Help requests answered within two working days | Proposed: at least 95%, and none over five working days | The "Help requests" list (when asked and when answered) and the course administrators' To do | Weekly |
| Work marked and returned on time | Proposed: within the turnaround GSA sets for coursework | Lecturers' To do ("Waiting to be marked") and the audit log (hand-in and release times) | Weekly |
| Marks sent to the SRMS match the gradebook ("Marks are right") | Every mark, to the hundredth | The reconciliation of the gradebook against the SRMS | Each time coursework is sent |

## 6. The weekly check-in and the mid-term review

### The weekly check-in

| | |
|---|---|
| **Who** | The pilot lead (chair), the department champions, a course administrator from each campus and one member of the development team. Pilot lecturers are welcome. |
| **When** | 30 minutes, the same day and time each week, from week 1 to week 14. Essequibo joins online. |
| **Record** | One page, kept by the pilot lead in a shared folder, in the form below. |

The agenda is the same every week:

1. **The figures** (5 minutes): sign-ins by course for the week; help requests asked, answered and still open,
   and the longest wait; work waiting to be marked; page times; any work reported lost.
2. **Each course in turn** (10 minutes): one minute from each champion on anything stopping teaching.
3. **Failures and fixes** (5 minutes): new problems, what has been fixed, what is waiting.
4. **Help and training** (5 minutes): questions asked often, and help pages or training to change.
5. **Actions** (5 minutes): who does what by when. Check last week's actions.

The record of each check-in:

| Date | Present | Figures in brief | Problems (with who owns each and by when) | Decisions | Actions carried over |
|---|---|---|---|---|---|
| | | | | | |

### The mid-term review (week 7)

The pilot lead brings together the heads of the pilot departments, the champions, the course administrators
and the development team for an hour. The review looks at each success measure so far, the risk table, and a
short word from two students and two lecturers. It decides what to change for the rest of term and gives an
early view of the go/no-go decision, so that nobody is surprised at the end of term. The pilot lead writes it up
in two pages.

### The end-of-term report (weeks +1 and +2)

The pilot lead writes a report of no more than ten pages: each success measure against its target, the
adoption report, the help requests and what they were about, every failure and its fix, what lecturers and
students said, the risk table at the end of term, and a recommendation on go or no-go with any conditions.

## 7. Risks

| Risk | Likelihood | Effect | What is done about it | Who |
|---|---|---|---|---|
| Lecturers have too little time to build their course before term | Medium | High | Training before term; material brought in with `import_folder`; champions' help; the course-site standard asks only for what week 2 needs | Pilot lead, champions |
| Poor signal at Essequibo or on the farm stops students using it | Medium | High | Work without signal waits on the phone and is sent later; pages kept light; tested at Essequibo before the pilot | Development team |
| Some students have no smartphone or no data | Medium | Medium | Campus computers at set times; the lecturer accepts paper for those students and records it; numbers counted in week 1 | Lecturers, course administrators |
| Accounts or enrolments missing at the start of term | Medium | High | Invitations sent in week −1; integration runs checked daily in week 1; the Registry told at once of anyone missing | Course administrators |
| Help requests pile up in the first weeks | High | Medium | A rota of course administrators; champions answer in their department; help pages improved each week | Course administrators |
| A lecturer new to online teaching struggles and stops using it | Medium | Medium | Their champion meets them weekly in the first month; a named course administrator to call | Champions |
| Work or marks lost or wrong | Low | High | Every hand-in has a receipt; the audit log; reconciliation with the SRMS; a lost-work report checked within a day | Development team, pilot lead |
| The system is down at a busy time (a quiz or a deadline) | Low | High | Daily backups and the restore drill; a deadline is moved and students told if it happens | Development team, lecturers |
| A personal data breach | Low | High | Breach register and procedure; the DPO named; only pilot data in the system | DPO, administrator |
| A champion or pilot lecturer leaves during the term | Low | Medium | The head of department names a replacement within a week | Heads of department |
| Lecturers run paper and the LMS side by side and do the work twice | Medium | Medium | The pilot courses agree at the start that the LMS is the record for coursework | Pilot lead, heads of department |

## 8. Go or no-go for moving every course

### Must-haves

GSA moves every course to the LMS only if all of these are met at the end of the pilot term:

| Must-have | Threshold |
|---|---|
| "Used": outline, weekly content and assessment in the LMS by week two | Every pilot course, or all but one, where the reason is known and has been dealt with |
| Students log in weekly | At least the target agreed for section 5 (proposed 90%) across the pilot, and no course below 80% |
| No work lost to a dropped connection | None confirmed in the term |
| Marks are right | Every mark sent to the SRMS matched the gradebook |
| Students hand in in under two minutes; lecturers mark and return in under three | The targets agreed for section 5 (proposed 9 in 10) |
| Speed | 95% of pages under 2 seconds on campus and under 5 seconds on a 2 Mbps line |
| Help requests answered within two working days | The target agreed for section 5 (proposed 95%) |
| Failures | No failure open at the level "Stops the release"; no personal data breach left unresolved |
| People | Every department has a champion and a course administrator is available at each campus for the next term |

### Who decides

The **Principal** decides, on the pilot lead's recommendation, at a go/no-go meeting in week +2 with the heads
of department, the champions, the course administrators, the data protection officer and the lead of the
development team. The decision and its reasons are written down and kept with the end-of-term report.

### The three possible decisions

1. **Go.** Every must-have is met. All courses move from the next term, department by department, with the
   same training and course-site standard.
2. **Go with conditions.** A must-have is missed narrowly and the cause is understood and limited (for example,
   one campus's page times). All courses move, with a written condition, an owner and a date for each (for
   example "Essequibo practicals stay on paper until the page times are met in a recheck"). The pilot lead
   checks each condition by week 4 of the next term.
3. **No-go.** A must-have is missed and the cause is not limited. The problems are fixed and the pilot is
   **repeated with the same courses for another half term** (seven weeks), with the same measures. The Principal
   then decides again. The other courses stay as they are meanwhile.
