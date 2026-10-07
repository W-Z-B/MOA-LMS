# GSA LMS acceptance script: head of department

**Version 1.0, 6 October 2026, draft for GSA's review.** For: a GSA head of department testing the LMS, and the
development team member who sits with them.

The LMS has no separate head of department role. A head of department uses it in three ways, and this script
tests exactly those:

1. **As a lecturer** of the courses they teach. The full lecturer tests are in [lecturer.md](lecturer.md);
   HD-02 checks only that a head of department sees what any lecturer sees and no more.
2. **As the supervisor** who approves their staff's requests to join staff-development courses, and who names a
   stand-in when away. The supervisor is the line manager recorded in the HRMS.
3. **As the keeper of a department question bank**, shared with the department's teaching staff.

Read [README.md](README.md) first. You sign in as the fictional head of department, with the username and the
training password the course administrator gives you, and the authenticator on the phone kept for testing.

**Tester:** ______________ **Campus:** ______________ **Date:** ______________

**Preconditions for the whole script:** on staging, the fictional head of department teaches one course and is
recorded in the HRMS test data as the line manager of the fictional Essequibo lecturer. A second fictional
lecturer in the same department, and Marlon Bacchus in a different department, are available to sign in.

---

### HD-01 Signing in and the help for heads of department

**Person and device:** the head of department; desktop, then phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Sign in and type the authenticator code, **Verify**. | Home opens, as for a lecturer. | |
| 2 | Choose **Help** at the top, then the help for heads of department. | The help page for heads of department opens. Check that it covers approvals, stand-ins and the department question bank. | |
| 3 | Search for `stand-in`. | The help page is among the results. | |
| 4 | Open Home on the phone. | It reads well at phone width. | |

### HD-02 Teaching, and only their own courses

**Person and device:** the head of department; desktop.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open **My courses**. | Only the courses they teach. | |
| 2 | Open their course, the Gradebook tab. | Their students' marks. | |
| 3 | Open AGR101 (taught by Marlon, not by them) by its address. | Refused: a head of department sees only the courses they teach. | |

### HD-03 Approving a request to join a staff-development course

**Person and device:** the Essequibo lecturer, then the head of department; desktop. **Preconditions:** SD-102
First aid in the field, which is joined with approval, and a second fictional course joined with approval that
the development team adds on staging (for example SD-103).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | As the Essequibo lecturer, search for `staff development`, find SD-102 with "Search the catalogue", choose **Ask to join**, write "Why you want to take it", send. | The request is listed under "My requests to join". | |
| 2 | As the head of department, search for `staff development` and open "Approvals". | The request is under "Waiting for your decision", with the reason given. | |
| 3 | Choose **Approve**. | Approved. The lecturer is on SD-102 and it shows under "My learning". | |
| 4 | As the lecturer, ask to join SD-103. As the head of department, choose **Turn down** with "Comment (needed to turn it down)" left empty. | Refused: a comment is needed. | |
| 5 | Write a comment and choose **Turn down**. | Turned down; the lecturer sees the decision under "My requests to join". | |
| 6 | As the lecturer, ask to join SD-103 again, then choose **Withdraw** under "My requests to join". | Withdrawn; it no longer waits for the head of department. | |
| 7 | As the head of department, look for requests from staff they do not supervise (for example Marlon Bacchus). | None are shown. | |

### HD-04 Naming a stand-in

**Person and device:** the head of department, then the stand-in; desktop. **Preconditions:** the second
lecturer in the department, to act as stand-in; SD-103 from HD-03.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In "Approvals" choose **Name a stand-in**, **Find** the second lecturer, **Choose**. | The person is chosen. | |
| 2 | Set "From" today and "To" next week, "Why (leave, travel)" "Leave", choose **Name the stand-in**. | The stand-in is shown with the dates. | |
| 3 | As the Essequibo lecturer, ask to join SD-103 again. | The request is sent. | |
| 4 | As the stand-in, open "Approvals". | The request is under "Waiting for your decision". | |
| 5 | As the stand-in, choose **Approve**. | Approved. The lecturer is on SD-103. | |
| 6 | As the head of department, choose **End** on the stand-in. | The stand-in is no longer listed and no longer sees the head of department's requests. | |

### HD-05 The department question bank

**Person and device:** the head of department, then two lecturers; desktop. **Preconditions:** a department code
for the fictional department, from the course administrator.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In their course open Quizzes, "Question banks", choose **New bank**. | The choice of "This course" or "A department, shared with its teaching staff". | |
| 2 | Choose "A department, shared with its teaching staff", type the "Department code", name the bank, save. | The bank is made for the department. | |
| 3 | Choose **New question** and add two questions. | Both are in the bank. | |
| 4 | As the second lecturer of the same department, open Quizzes in their course, "Question banks". | The department bank is listed and its questions can be added to a quiz with **From the bank**. | |
| 5 | As Marlon (another department), open "Question banks". | The department bank is not listed. | |
| 6 | As the head of department choose **Export** on the bank. | A file downloads. | |

---

## Sign-off: head of department

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Head of department | | | | | | |
| Development team member present | | | | | | |
