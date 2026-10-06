# GSA LMS acceptance script: administrator

**Version 1.0, 6 October 2026, draft for GSA's review.** For: the GSA staff member who will administer the
LMS, and the development team member who sits with them.

Read [README.md](README.md) first. You sign in as the fictional administrator Ayesha Ramdin, with the username
and the training password the development team gives you, and the authenticator on the phone kept for testing.
An administrator has everything a course administrator has: run [course-administrator.md](course-administrator.md)
CA-01 as well. Retention (AD-05) needs the data protection officer at the same time, because a disposal is
approved by a different person.

**Tester:** ______________ **Campus:** ______________ **Date:** ______________

---

### AD-01 Signing in and signing out everywhere

**Person and device:** an administrator; desktop and phone. **Preconditions:** Ayesha Ramdin's account.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Sign in on the desktop and type the authenticator code. | Home opens. | |
| 2 | Sign in on the phone too. On the desktop open **My account**, choose **Sign out everywhere else**. | The phone is signed out. The desktop stays signed in. | |
| 3 | Open Admin. | The administration console with every section, including "People to invite", "Audit log", "Privacy notice", "Retention and disposal" and "Breach register". | |
| 4 | Choose **Help** at the top. | The administrator's help opens. | |

### AD-02 Inviting people

**Person and device:** an administrator; desktop. **Preconditions:** staging is connected to the HRMS and SRMS
test services, which hold fictional people only. Emails go to a test mailbox the development team can open.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "People to invite", choose a "Campus" and a "Term code", choose **See who would be invited**. | A list of people who have no account yet. Nobody is invited yet. | |
| 2 | Check the list against the test data. | Only people of that campus and term; nobody who already has an account. | |
| 3 | Choose **Send N invitations** (N is the number listed). | The invitations are sent. Each person's email holds a link to choose a password (as in ST-01). | |
| 4 | Choose **See who would be invited** again. | The people just invited are no longer listed. | |

### AD-03 The audit log

**Person and device:** an administrator; desktop. **Preconditions:** the marks given in LE-08 to LE-10.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Audit log". | The most recent events first. | |
| 2 | Filter by Marlon Bacchus and today's date. | His mark changes and releases of the day, each with the time. | |
| 3 | Find the mark given to Tevin in LE-08. | The event shows who, what, when, and the mark before and after. | |
| 4 | Choose **Check the chain now**. | The chain is whole: no event has been changed or removed. | |
| 5 | Choose **Export to a spreadsheet (CSV)**. | A file downloads with the filtered events. | |
| 6 | Look for any button to change or remove an event. | There is none. | |

### AD-04 The privacy notice

**Person and device:** an administrator; desktop. **Preconditions:** the published notice from the demonstration
data.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Privacy notice". | The published version and its number. | |
| 2 | Choose **Write a new version**, change a sentence, **Publish**. | The new version is published with the next number. | |
| 3 | Sign in as Kezia. | She is asked to read the new notice and choose **I have read this notice** before going on. | |

### AD-05 Retention and disposal

**Person and device:** an administrator and the data protection officer, side by side; desktop. **Preconditions:**
fictional records past their retention period on staging (the development team prepares them).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Retention and disposal", choose **Find what is due**. | A run lists the records due for disposal under the schedule. | |
| 2 | Choose **Keep** on one record, with a reason. | It is taken out of the run. | |
| 3 | As the administrator who found them, try to approve the disposal. | Refused: a different person must approve it. | |
| 4 | As the data protection officer, choose **Approve the disposal**. | The records are disposed of. The run is recorded in the audit log. | |
| 5 | Start another run and choose **Cancel the run**. | Cancelled; nothing is disposed of. | |

### AD-06 The breach register

**Person and device:** an administrator; desktop. **Preconditions:** none. Use a made-up breach only.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Breach register", choose **Record a breach** with a made-up description (for example "a printed class list left in a lab"). | Recorded, with the time. | |
| 2 | Choose **Contained now**. | The time it was contained is recorded. | |
| 3 | Choose **Commissioner told now** and **People told now**. | Each is recorded with its time. | |
| 4 | Choose **Close**. | Closed. It stays in the register. | |

### AD-07 The access review

**Person and device:** an administrator; desktop. **Preconditions:** the roles on staging.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Access review". | Everyone with a role, and the teaching staff of each course. | |
| 2 | Check that the list matches who should have each role. | Any role that should not be there is written down for removal. | |
| 3 | Choose **Sign off the review**. | Signed with your name and the date. | |

---

## Sign-off: administrator

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Administrator | | | | | | |
| Development team member present | | | | | | |
