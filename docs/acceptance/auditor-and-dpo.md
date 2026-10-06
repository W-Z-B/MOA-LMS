# GSA LMS acceptance script: auditor and data protection officer

**Version 1.0, 6 October 2026, draft for GSA's review.** For: GSA's auditor and data protection officer (DPO)
testing the LMS, and the development team member who sits with them.

Read [README.md](README.md) first. You sign in as the fictional auditor or the fictional DPO, with the
username and the training password the development team gives you, and the authenticator on the phone kept
for testing. Run this script on day 3, after the other roles, so that the audit log holds what they did. The
DPO also takes part in AD-05 in [administrator.md](administrator.md) to approve a disposal.

The DPO should have the draft data protection impact assessment, `docs/privacy/dpia.md`, at hand: case DP-05
checks that the system does what it says.

**Tester:** ______________ **Role:** ______________ **Date:** ______________

---

## Auditor

### AU-01 Finding the console, and reading only

**Person and device:** the auditor; desktop. **Preconditions:** the fictional auditor account.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Sign in and type the authenticator code. | Home opens. | |
| 2 | Search for `admin` and open it. | The console opens with the sections an auditor may read. | |
| 3 | Open each of "Integration runs", "Access review", "Privacy notice", "Correction requests", "Retention and disposal" and "Breach register". | Each can be read. None offers a button that changes anything (no **Sign off the review**, no **Publish**, no **Approve the disposal**, no **Record a breach**). | |
| 4 | Open staff development and its overseer tabs ("Required training", "Certificate templates", "Certificates issued"). | Each can be read; nothing can be changed (no **Assign now**, no **Withdraw**). | |
| 5 | Open Messages. | The auditor cannot write a message. | |
| 6 | Choose **Help** at the top. | The auditor's help opens. | |

### AU-02 Following a mark through the audit log

**Person and device:** the auditor; desktop. **Preconditions:** the marks given and released on days 1 and 2
(LE-08 to LE-10), the extension in LE-07, and the coursework sent to the SRMS in LE-11.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Audit log" and use the filters to find the events of day 1 for Marlon Bacchus. | The marks given to Ria Ramdial and Andre Fung, the release, and the spreadsheet import, each with who and when. | |
| 2 | Find Ria's "Soil profile report" mark. | The mark before and after, the late penalty, and who released it. | |
| 3 | Find the extension granted to Tevin and its withdrawal. | Both are there, with who and when. | |
| 4 | Find the lecturer looking at a student's submission. | Each look at someone else's submission is logged. | |
| 5 | Choose **Check the chain now**. | The chain is whole. | |
| 6 | Choose **Export to a spreadsheet (CSV)**. | A file downloads. Open it: the events match the screen. | |
| 7 | Compare the AGR205 totals in the gradebook export (LE-11) with what was sent to the SRMS. | They match to the hundredth. | |

---

## Data protection officer

### DP-01 What waits for the DPO

**Person and device:** the DPO; desktop. **Preconditions:** Kezia's correction request (ST-16), unless the course
administrator has closed it; a disposal run waiting (AD-05 step 1).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Sign in, type the authenticator code, open **To do**. | Correction requests and disposals waiting are listed. | |
| 2 | Open "Correction requests". | The requests can be read; the DPO cannot decide them (that is the course administrator's task). | |

### DP-02 Writing and publishing the privacy notice

**Person and device:** the DPO; desktop. **Preconditions:** the notice published in AD-04.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Privacy notice", choose **Write a new version**. | The current text, to change. | |
| 2 | Change a sentence and choose **Publish**. | Published with the next version number. | |
| 3 | Sign in as Tevin. | He is asked to read the new notice before going on. | |
| 4 | As Tevin, open **My data**, then **Read the privacy notice (version N)**. | The new version, with its number. | |

### DP-03 Retention and disposal

**Person and device:** the DPO; desktop. **Preconditions:** as AD-05, with the administrator.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Retention and disposal" and the run the administrator found. | The records due, and those kept with their reasons. | |
| 2 | Choose **Keep** on one more record. | It is taken out of the run. | |
| 3 | Choose **Approve the disposal**. | Disposed of; the run is closed and in the audit log. | |
| 4 | On another run choose **Cancel the run**. | Cancelled. | |

### DP-04 The breach register

**Person and device:** the DPO; desktop. **Preconditions:** none. Use a made-up breach only.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Choose **Record a breach**, made up, involving a student under 18. | Recorded with the time. | |
| 2 | Choose **Contained now**, **Commissioner told now**, **People told now**. | Each recorded with its time. | |
| 3 | Choose **Close**. | Closed; it stays in the register for the auditor to read. | |

### DP-05 Does the system do what the impact assessment says?

**Person and device:** the DPO; desktop and phone. **Preconditions:** `docs/privacy/dpia.md`; Kezia's account.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | As Kezia, open **My data** and **Download my data**. | Her courses, submissions, released marks, completed courses, what she did and her sign-ins. | |
| 2 | Look at "What I did in the LMS". | Only sign-ins, downloads and submissions; nothing on time spent on pages (section 8 of the assessment). | |
| 3 | As Kezia, try to open Tevin's submission by changing the number in the address bar. | Refused. | |
| 4 | As Kezia, open the Gradebook tab. | Only her own row. | |
| 5 | As Marlon, open a course he does not teach by its address. | Refused: access is decided by course membership. | |
| 6 | Check the calendar address made in ST-13. | It shows titles, times and places, never marks or messages. | |
| 7 | Sign out on the phone after a field observation (see [field-and-phone.md](field-and-phone.md)). | The field copies of practical tasks are cleared from the phone. | |
| 8 | Note anything the assessment says that the screens do not do: ____________ | (For the next draft of the assessment.) | |

---

## Sign-off: auditor and data protection officer

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Auditor | | | | | | |
| Data protection officer | | | | | | |
| Development team member present | | | | | | |
