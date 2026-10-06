# GSA LMS acceptance script: course administrator

**Version 1.0, 6 October 2026, draft for GSA's review.** For: the GSA course administrators at Mon Repos and
Essequibo who test the LMS, and the development team member who sits with them.

Read [README.md](README.md) first. You sign in as the fictional course administrator for your campus, with the
username and the training password the development team gives you, and the authenticator on the
phone kept for testing. Several cases answer what students and lecturers did in their scripts, so run this
script in two parts: CA-01 and CA-03 to CA-08 in the morning, CA-02 and CA-09 in the afternoon.

**Tester:** ______________ **Campus:** ______________ **Date:** ______________

---

### CA-01 Signing in, Home and the campus switch

**Person and device:** a course administrator; desktop, then phone. **Preconditions:** the fictional course
administrator account; courses at both campuses on staging.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Sign in and type the authenticator code, **Verify**. | Home opens. | |
| 2 | Look at Home. | Shortcuts "Course sites", "To do", "Admin", "My account"; figures "Course sites", "Students", "Without a lecturer", "Takedown requests". | |
| 3 | At the top choose **All campuses**, then the Essequibo campus. | My courses lists only Essequibo's courses. | |
| 4 | On the phone, open the account menu. | The campus switch is there. | |
| 5 | Choose **Help** at the top. | The course administrator's help opens. | |

### CA-02 Answering help requests

**Person and device:** a course administrator; desktop. **Preconditions:** the questions sent by Kezia (ST-17),
Marlon (LE-21) and the student on the phone at Essequibo ([field-and-phone.md](field-and-phone.md), PH-08).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open **To do**. | The help requests are listed. | |
| 2 | Open it (**Open it** in To do), or search for **Help** and choose **Help requests**. | Each request with who sent it, when, and **Open the page they were on**. | |
| 3 | In Kezia's request, write in **Your answer** and choose **Send the answer**. | It is marked answered and leaves To do. Kezia gets the answer as a notification. | |
| 4 | Check the Essequibo request. | It says **Written on the phone on** the time the student wrote it, not when the signal returned; it arrived once only. | |
| 5 | Answer the others. | Nothing is left waiting. | |

### CA-03 Accommodations

**Person and device:** a course administrator; desktop. **Preconditions:** Andre Fung on AGR205; "Soil texture
test" due in two days.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Search for `accommodations` and open it. Choose **Add an accommodation** for Andre Fung. | The form "More time in quizzes (%)", "More days for each assignment", "Another format needed", "Reason (course administrators only; never shown to lecturers)", "In force". | |
| 2 | Set 25% more time, 2 more days, a reason, tick "In force", **Save**. | Saved. | |
| 3 | As Andre, open "Soil texture test". | The due date is two days later, marked "(extended for you)". | |
| 4 | As Marlon, look at Andre in AGR205. | The accommodation applies but the reason is not shown anywhere. | |

### CA-04 Templates, storage and takedowns

**Person and device:** a course administrator; desktop. **Preconditions:** the development team has added one
fictional takedown request on staging (there is no screen yet for anyone to raise one).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Admin, then "Course templates". | The templates lecturers can start from. | |
| 2 | Open "Storage allowances", **Find a course** AGR101, set "Allowance in MB", **Save allowance**. | Saved. The lecturer sees the new allowance under "Storage" in Course setup. | |
| 3 | Open "Takedown requests". | The fictional request is listed with the item. | |
| 4 | Choose **Withdraw the item**. | Students no longer see the item. | |
| 5 | Choose **Restore the item**. | Students see it again. | |

### CA-05 Bringing in existing material

**Person and device:** a course administrator with a member of the development team at the server; desktop.
**Preconditions:** a folder of sample material, one folder per module, including one file of a kind the LMS does
not accept; this year's AGR102 (or a new empty course); the steps in docs/migration-guide.md.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Run `import_folder` with the course code, the folder and `--dry-run`. | A report: every file, its module and what would happen. Nothing is changed in the course. | |
| 2 | Run it again without `--dry-run` and with `--report` to a CSV file. | The report says which files were imported and which refused, with the reason. | |
| 3 | Open the course's Content tab. | One module for each folder; every imported file is a "Draft", with its licence "Not yet known". | |
| 4 | Open the refused file in the report. | The file of the wrong kind is refused, not imported. | |
| 5 | As the lecturer, set "Whose material is this?" on one file and publish it. | Students see it. The other files stay drafts. | |
| 6 | Run the same import again. | Every file already brought in is reported as "skipped", "Already imported." Nothing is imported twice. | |

### CA-06 The GSA rubric library

**Person and device:** a course administrator; desktop. **Preconditions:** none.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Search for `rubric library` and open it. Add a rubric with **New rubric** and **Save the rubric**. | Saved in the library. | |
| 2 | As Marlon, choose **Copy from the GSA library** in AGR101's rubrics. | The new rubric is offered. | |

### CA-07 Staff development oversight and certificates

**Person and device:** a course administrator; desktop. **Preconditions:** SD-101 and SD-102; Marlon's SD-102
certificate.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open staff development, "Required training", **Require a course** SD-101 for a group of staff, then **Assign now**. | The staff are put on the course and see it under "My learning". | |
| 2 | Open "Certificate templates". | The templates are listed. | |
| 3 | Open "Certificates issued". | Marlon's certificate for First aid in the field. | |
| 4 | Open "Approvals". | Requests waiting for a decision can be approved by a course administrator too. | |
| 5 | Last, on day 3 only: choose **Withdraw** on Marlon's certificate. | It is shown as withdrawn. Checking its reference and code no longer confirms it as valid. | |

### CA-08 Importing a competency framework

**Person and device:** a course administrator; desktop. **Preconditions:** a CSV of a small fictional framework
from the development team.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Choose **Import a framework** and the CSV. | The framework is imported with its units, elements and performance criteria. | |
| 2 | Choose a CSV with a missing column. | Refused, with the reason. | |
| 3 | As Marlon, choose **Follow a framework** in a course. | The new framework is offered. | |

### CA-09 Integration runs, the access review and correction requests

**Person and device:** a course administrator; desktop. **Preconditions:** Kezia's correction request (ST-16).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Admin, "Integration runs". | The latest runs with the HRMS and the SRMS, each with its result. | |
| 2 | Open "Access review". | Everyone with a role, and the teaching staff of each course. | |
| 3 | Choose **Sign off the review**. | Signed, with your name and the date. | |
| 4 | Open "Correction requests" and Kezia's request. | What she asked for. | |
| 5 | Choose **Not changed** with a reason. | The request is closed and shows the decision. | |

---

## Sign-off: course administrator

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Course administrator | | Mon Repos | | | | |
| Course administrator | | Essequibo | | | | |
| Development team member present | | | | | | |
