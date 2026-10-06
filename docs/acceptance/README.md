# GSA LMS: acceptance testing

**Version 1.0, 6 October 2026, draft for GSA's review.** For: the GSA lecturers, students, course
administrators, administrator, auditor and data protection officer who test the LMS before it goes live,
the head of department who tests the supervisor's tasks, and the development team who prepare the system
and fix what fails.

This folder answers checklist item **7.18**: acceptance tests by role at both campuses, including a phone
at Essequibo and a field practical. A release goes live only when GSA has run these scripts and signed the
table at the end of this page.

## What acceptance testing is

Acceptance testing is GSA's own check that the LMS does what GSA needs, done by the people who will use it,
on the tasks they will do in a real term. The development team has already tested the system with automatic
tests. Acceptance is different: GSA staff and students follow a written script, step by step, and say for
each step whether the screen did what the script says it should.

## Who tests

| Who | How many | Campus | Script |
|---|---|---|---|
| Lecturers (one of them new to online teaching) | At least 2 at Mon Repos and 1 at Essequibo | Both | [lecturer.md](lecturer.md) |
| Students (one under 18 if possible, with a guardian's agreement) | At least 3 at Mon Repos and 2 at Essequibo | Both | [student.md](student.md) |
| Course administrators | 1 at each campus | Both | [course-administrator.md](course-administrator.md) |
| An administrator | 1 | Mon Repos | [administrator.md](administrator.md) |
| The auditor and the data protection officer | 1 each | Mon Repos | [auditor-and-dpo.md](auditor-and-dpo.md) |
| A head of department | 1 | Either | [head-of-department.md](head-of-department.md) |
| A lecturer and a student on a phone at Essequibo, and a lecturer with three students on a farm plot | 1 lecturer, 3 students | Essequibo, and a farm plot | [field-and-phone.md](field-and-phone.md) |

A member of the development team sits with each group, prepares the system, answers questions about the
script (not about how to do the task: if the tester cannot find the way unaided, that is a result) and
writes down failures. Staff and students are not paid to test, but students' time should be agreed with
their lecturers.

## Where: the staging system, with fictional data only

- All testing is on the **staging system**, never on the live system. The development team gives each group
  its address on the day.
- Only **fictional data** is used: invented people, invented courses and invented work. No real student
  record, mark or photograph of a real person's face goes into staging. Photographs taken in the tests are of
  plots, plants, tools and notebooks.
- You sign in as a **fictional person**, not as yourself. The course administrator gives you the username and
  **the training password the course administrator gives you**. Never use your own GSA password on staging.
- Staff accounts need an authenticator code. The development team sets up the authenticator on a phone kept
  for testing, so testers do not put the training accounts on their own phones.
- The day before each test day the development team reloads the demonstration data
  (`seed_journeys --fictional`), because the dates in it (work due in three days, a hand-in two hours late)
  are counted from the day it is loaded.

### The fictional accounts and courses

From the demonstration data:

| Person | Kind | What they have |
|---|---|---|
| Marlon Bacchus | Lecturer | Teaches AGR101-2026-27-S1-MRP Introduction to Crop Production, AGR205-2026-27-S1-MRP Soil Science and Fertility, and both offerings of AGR102 Soils and Plant Nutrition (last year's 2025-26 one to copy from and this year's, empty and unpublished). Has completed the staff-development course SD-102 First aid in the field and holds its certificate. |
| Kezia Persaud | Student, AGR101 | "Field notebook check" due in three days, not handed in; a marked assignment |
| Tevin Joseph | Student, AGR101 | Has handed in "Crop calendar for a kitchen garden", waiting to be marked |
| Ria Ramdial, Andre Fung | Students, AGR205 | Each handed in "Soil profile report" (a PDF) a day late, and "Soil texture test" |
| Ayesha Ramdin | Administrator | The whole administration console |
| Rohan Singh, Priya Bhagwandin | New students | Accounts open but no password chosen yet; each has an invitation link |

AGR101 also has course material (for example "Week 2: Seed and germination"), two forums ("Questions on
germination" and "Class discussion"), three classes, two lab groups ("Lab group A" and "Lab group B"), the
practical task "Prepare a vegetable bed" at Plot 7 with a three-point checklist, the competency framework
AGR-CROP-L2 Crop Production Level 2, and the question bank "Crop production questions". The staff-development
catalogue has SD-101 Safe use of farm machinery (open to join) and SD-102 First aid in the field (join with
approval). The course "Getting started with the GSA LMS" is on the system for new students.

To be added on staging by the development team before testing (all fictional; the demonstration data has
only Mon Repos accounts):

| Account or course | Why |
|---|---|
| A course administrator for each campus | Course administrator script |
| An auditor and a data protection officer | Auditor and DPO script |
| A head of department, who teaches one course and is recorded in the HRMS test data as the line manager of the Essequibo lecturer | Head of department script |
| A lecturer and three students at Essequibo, on a copy of AGR101 for Essequibo (for example AGR101-2026-27-S1-ESQ) with the practical task and three classes | Phone and field scripts |
| A folder of sample material, one folder per module, for the import test | Course administrator script |
| A second staff-development course joined with approval (for example SD-103), and a second lecturer in the head of department's department | Head of department script |
| One takedown request, fictional records past their retention period, and a CSV of a small competency framework | Course administrator, administrator and DPO scripts |

## Devices

Each test case names its device. Every task a student does in the field is tested on a phone.

| Device | What it is | Where |
|---|---|---|
| Desktop | Any GSA computer with a current Chrome, Edge or Firefox, on the campus network | Both campuses |
| Phone | A low-cost Android phone, screen 360 pixels wide, of the kind GSA students commonly own, current Chrome, on a 3G connection or poorer | Both campuses; the Essequibo campus connection; a farm plot |
| Slow line | A computer or phone limited to 2 Mbps (the development team sets this up) | For the timed page checks |

Write down the phone's make and model and the connection (for example "3G, one bar") at the top of each
script.

## What is covered

| Area | What is tested | Scripts |
|---|---|---|
| **Release 1: teaching a whole term** | | |
| Course sites | Publishing a site, templates, copying last year's course with its dates moved, storage | Lecturer, course administrator |
| Content | Modules, pages, files, links, licence of material, release conditions, accessibility check, reading and marking complete, PDFs | Lecturer, student, phone |
| Assignments | Setting work, extensions, handing in typed answers, files and photos, receipts, late work | Lecturer, student, phone |
| Marking | Marking screen, rubrics, spoken feedback, late penalties, marks from a spreadsheet, releasing marks | Lecturer |
| Gradebook | Categories and weights, export, the student's view of the total, sending coursework to the SRMS | Lecturer, student |
| Quizzes | Question banks (course and department), quizzes, extra time, accommodations, taking a quiz, losing signal in a quiz, results | Lecturer, student, head of department, phone |
| Forums and messages | Forums of each kind, moderation, messages to staff and to a class, notices, read receipts | Lecturer, student |
| Classes and attendance | Classes, check-in codes, the register, attendance totals | Lecturer, student, phone, field |
| Calendar and notifications | Calendar, the private phone calendar address, the bell, email settings | Student, lecturer |
| Accounts and privacy | Invitations, choosing a password, authenticator codes, signed-in devices, My data, corrections, the privacy notice, the audit log, retention, breaches, the access review | Every script |
| **Release 2: the parts already built** | | |
| Practical tasks and field checklists | Tasks, criteria, observing in the field without signal, releasing results | Lecturer, student, field |
| Competency | Frameworks, competency records, the student's competency and portfolio | Lecturer, student, course administrator |
| Logbook | Entries with photos and location, sign-off, returning for correction | Student, lecturer, field |
| Staff development | Catalogue, joining, approvals, stand-ins, required training | Lecturer, head of department, course administrator |
| Certificates | Downloading, templates, withdrawing | Lecturer, course administrator |
| **Help and orientation** | | |
| Help pages | The "Help" link at the top of every page, the help page for each role, help in search | Every script |
| Asking for help | "Ask for help" from a page, with and without signal; "Help requests" for course administrators; the answer as a notification | Student, course administrator, phone |
| Student orientation | "Getting started with the GSA LMS" on every new student at first sign-in, its practice quiz and practice logbook entry | Student |

## The order of testing

Some tests use what an earlier one made, so run them in this order:

1. **Day 1, Mon Repos, morning.** Administrator, course administrator (cases up to the import), then
   lecturer (building content, the quiz, the assignment, the class).
2. **Day 1, afternoon.** Students (handing in, the quiz, checking in while the lecturer shows the code),
   then the lecturer's marking, then the course administrator's help requests and accommodations.
3. **Day 2, Essequibo.** "On a phone at Essequibo", the Essequibo lecturer and students, and "During a
   field practical without signal" on a farm plot.
4. **Day 3, Mon Repos.** Head of department, then the auditor and the data protection officer, who look
   in the audit log for what the others did on days 1 and 2. Retests of anything that failed.

## How to record a result

Each step has a **Result** column. Write one of:

| Result | When |
|---|---|
| **Pass** | The screen did what the "Expected result" says. Small differences in wording are a pass if the meaning is the same; note them. |
| **Fail** | Anything else: a different result, an error, a step you could not do, a step that needed help to find, or work that went missing. Write a short note of what happened and take a screenshot (on Android, press the power and volume-down buttons together). |
| **Not tested** | You could not run the step (for example, no signal at all when signal was needed). Write why. |

Write the time beside any step marked **Timed**, using a phone's stopwatch. At the end of each test case, sign
your initials.

## When something fails

1. **Raise it.** The development team member writes it on the failure list straight away, with: the test case
   and step (for example ST-06 step 4), what happened, what was expected, the device and connection, the time,
   and the screenshot.
2. **Agree how serious it is**, with the tester:

   | Level | Meaning | Example |
   |---|---|---|
   | Stops the release | Work or marks lost or wrong, someone sees another person's data, or a main task cannot be done | A quiz answer lost when signal drops |
   | Fix before go-live | The task can be done but is wrong or confusing in a way that matters | A wrong message after handing in |
   | Can wait | Wording, appearance, or a rare case with an easy way round | A label that could be clearer |

3. **Fix and retest.** The development team fixes it on staging and says which version has the fix. The
   **same tester, on the same device, runs the whole test case again**, not only the failed step, and records
   the retest as a new result with the date. A failure is closed only by a passing retest.
4. **Report.** The failure list, with every failure, its level and its retest, is attached to the sign-off.

## Sign-off

The release is accepted when every test case has passed, or every failure still open is at the level "Can
wait" and the person deciding for GSA has agreed to it in writing. Each script ends with a sign-off for its
role. This table is the sign-off for the whole release.

**Release:** ________________ **Staging version tested:** ________________

| Role | Name | Campus | Date | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|
| Lecturer | | Mon Repos | | |
| Lecturer | | Essequibo | | |
| Student | | Mon Repos | | |
| Student | | Essequibo | | |
| Course administrator | | Mon Repos | | |
| Course administrator | | Essequibo | | |
| Administrator | | | | |
| Head of department | | | | |
| Auditor | | | | |
| Data protection officer | | | | |
| Development team lead (all failures listed and retested) | | | | |
| Principal, or the person the Principal names, accepting the release for GSA | | | | |

**Conditions, if any:** ______________________________________________________________

**Failures still open at sign-off (each "Can wait"):** ________________________________
