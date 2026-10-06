# GSA LMS acceptance script: lecturer

**Version 1.0, 6 October 2026, draft for GSA's review.** For: GSA lecturers and teaching assistants testing
the LMS at Mon Repos and Essequibo (at least one of them new to online teaching), and the development team
member who sits with them.

Read [README.md](README.md) first. You sign in as the fictional lecturer Marlon Bacchus (or the fictional
Essequibo lecturer), with the username and the training password the course administrator gives you, and the
authenticator on the phone kept for testing. Teaching assistants can do everything here except send coursework
to the SRMS (LE-11).

Several student cases use what you make here, so run LE-06, LE-12 and LE-15 before the students start.

**Tester:** ______________ **Campus:** ______________ **Phone make and model:** ______________
**Connection:** ______________ **Date:** ______________

---

### LE-01 Signing in with an authenticator code

**Person and device:** a lecturer; desktop. **Preconditions:** Marlon Bacchus's account; the testing phone with
the authenticator app.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Sign in with the username and the training password. | "Authenticator code" is asked for: "Open the authenticator app on your phone and type the 6-digit code it shows for GSA LMS." | |
| 2 | Type six wrong digits and choose **Verify**. | Refused; you are not signed in. | |
| 3 | Type the code the app shows and choose **Verify**. | Home opens. | |
| 4 | Open **My account**. | "Signed-in devices" shows this device, with **Sign out everywhere else**. | |

### LE-02 Home and To do

**Person and device:** a lecturer; desktop, then phone. **Preconditions:** Marlon; Tevin's "Crop calendar for a
kitchen garden" waiting to be marked; AGR205's two late reports.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Home. | The figures "Waiting to be marked", and students "Not seen in N days" where there are any; buttons **Open** and **Add content**. | |
| 2 | Open **To do**. | The hand-ins waiting to be marked, oldest first, each with **Open it**. AGR101's hand-in is above AGR205's. | |
| 3 | Search (Ctrl and K) for `Kezia`. | A "People" group finds Kezia Persaud. | |
| 4 | Open Home on the phone. | It reads well at phone width, nothing scrolls sideways. | |

### LE-03 Building course content

**Person and device:** a lecturer; desktop. **Preconditions:** Marlon; AGR101. A PDF and a photograph of a plot
on the computer.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In AGR101's Content tab choose **New module**, name it "Acceptance week", choose **Add module**. | The module is added at the end. | |
| 2 | Choose **Move up** on it. | It moves up one place. | |
| 3 | In it choose **Add a page**. Give a "Title", write two paragraphs, a heading and a list using the toolbar. | The page editor shows them as they will look. | |
| 4 | Add a picture with **Picture** and leave its alternative text empty. Open "Accessibility check". | A finding under "Must be fixed"; saving is blocked until it is fixed. | |
| 5 | Add the alternative text, choose **Save and publish**. | Saved and published. | |
| 6 | Choose **See it as students do**. | The page as a student sees it. | |
| 7 | Choose **Upload a file**, give a "Title", choose the PDF, under "Whose material is this?" choose GSA's own, choose **Upload file**. | The file is added as a draft (pill "Draft"). | |
| 8 | Choose **Add a link** with "Web address" `https://example.org`, "Whose material is this?" an open licence, "Which open licence" and "Source and credit", choose **Add link**. | The link is added. | |
| 9 | On the file choose **Change**, then **Publish**. | The "Draft" pill goes. | |
| 10 | On the page choose **Change**, then **Duplicate**, then **Move to module** to another module and **Move**. | A copy appears in the other module. | |
| 11 | On the module choose "When students see it", set "Shown from" to tomorrow, choose **Save conditions**. | As Kezia, the module is not shown until tomorrow. | |
| 12 | On the link set "Only once this item is complete" to the page, save. | As Kezia, the link shows only after the page is marked complete. | |
| 13 | Drag an item to another place in the list. | It stays where it was dropped after the page is reloaded. | |

### LE-04 Setting up a course from last year's

**Person and device:** a lecturer; desktop. **Preconditions:** Marlon; AGR102-2025-26-S1-MRP (last year's) and
AGR102-2026-27-S1-MRP (this year's, empty and unpublished).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open this year's AGR102, then "Course setup: template, copy from another course, dates and storage". | The sections "Start from a template", "Copy from an earlier course", "Dates" and "Storage". | |
| 2 | Under "Copy from an earlier course", choose last year's AGR102 in "Course to copy from", tick "Move its dates", set "New start date" to the first day of this term, choose **Copy the course**. | The content and the assignment are copied. | |
| 3 | Open "Dates". | Every date has moved by the same number of days as the start date. | |
| 4 | Change one due date, choose **Save N changes** (N is 1). | Saved. | |
| 5 | Choose **Move every date** by seven days. | Every date moves by a week. | |
| 6 | Open "Storage". | How much of the course's storage allowance is used. | |
| 7 | Open the Content tab. | The copied content is there in its modules; last year's course is unchanged. | |

### LE-05 Publishing a course and posting an announcement

**Person and device:** a lecturer; desktop. **Preconditions:** this year's AGR102 after LE-04; AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | On this year's AGR102, choose **Publish to students**. | Published; the button now reads **Unpublish**. | |
| 2 | Choose **Unpublish**. | Students no longer see it. | |
| 3 | In AGR101's Announcements tab write a "Title" and "Message" and choose **Post and notify students**. | Posted. Kezia's bell shows it. | |

### LE-06 Setting an assignment

**Person and device:** a lecturer; desktop. **Preconditions:** Marlon; AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In the Assignments tab choose **New assignment**. | The form "Title", "Opens", "Due", "Maximum mark", "Weight", "Gradebook category", "Instructions". | |
| 2 | Title "Acceptance assignment: plot diary", opens now, due in two days, maximum mark 20, weight 1, short instructions. | Accepted. | |
| 3 | Under "Handing in" choose photographs (JPG, HEIC) and PDF, "Files in one hand-in (0 for typed answers only)" 3, allow handing in again, require the integrity statement. | Accepted. | |
| 4 | Under "Late work" tick "Accept work after the due date" and set a "Late penalty". | Accepted. | |
| 5 | Tick "Published to students" and choose **Create assignment**. | The assignment is listed; Kezia sees it on her Home. | |
| 6 | Open it again, change the instructions, choose **Save changes**. | Saved. | |

### LE-07 Giving an extension

**Person and device:** a lecturer; desktop. **Preconditions:** the assignment from LE-06.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Extensions", choose Tevin Joseph in "For", a "New due date" two days later, a "Reason", and **Grant the extension**. | Listed. Tevin sees the new due date marked "(extended for you)". Kezia's due date is unchanged. | |
| 2 | Choose **Withdraw**. | Tevin's due date returns to the original. | |
| 3 | Grant it again (it is used in the marking of late work). | Listed. | |

### LE-08 Marking and returning a submission (timed)

**Person and device:** a lecturer; desktop. **Preconditions:** Tevin's hand-in of "Crop calendar for a kitchen
garden" in AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | **Timed:** start the stopwatch on Home. Without help, open the hand-in, give a mark and a line of feedback, and return it to Tevin. Stop at the moment it is released. | Done in **under three minutes**. Time: ______ | |
| 2 | Check the marking screen. | The work is shown beside "Mark out of N" and "Feedback"; **Previous**, **Next** and **Next not marked** move between students. | |
| 3 | Mark another hand-in and choose **Save draft**. | The student does not see the mark yet. | |
| 4 | Choose **Save and release** on it. | The student sees the mark and feedback, and gets a notification. | |

### LE-09 Marking with a rubric, a late penalty and spoken feedback

**Person and device:** a lecturer; desktop with a microphone. **Preconditions:** AGR205 "Soil profile report",
handed in a day late by Ria Ramdial and Andre Fung, marked with "Soil profile report rubric", 5% a day taken
for lateness.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the assignment and choose **Mark** on Ria's hand-in. | Her PDF is shown beside the rubric levels. | |
| 2 | Choose a level for each criterion. | The mark adds up from the levels, and the late penalty is shown. | |
| 3 | Under "Feedback files and recordings" choose **Record spoken feedback**, speak, **Stop recording**, **Return this recording**. | The recording is attached. | |
| 4 | Choose **Save and release**. | Ria sees the mark after the penalty, the rubric and the spoken feedback (ST-07). | |
| 5 | Choose **Next not marked**. | Andre's hand-in opens. | |

### LE-10 The whole class: marks from a spreadsheet, releasing and downloading

**Person and device:** a lecturer; desktop. **Preconditions:** AGR205 "Soil texture test", handed in by both
students. A spreadsheet saved as CSV with the columns student number, mark, feedback, and the rows S2026911 and
S2026912 with marks out of 10.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "The whole class: release, download, marks from a spreadsheet". | **Release all marks**, **Download every hand-in (zip)**, **Choose a sample** and "Spreadsheet (CSV)". | |
| 2 | Choose the CSV under "Spreadsheet (CSV)" and **Check the file**. | Both rows are recognised. | |
| 3 | Change one student number to one not on the course, check again. | That row is refused and the reason given. | |
| 4 | With the correct file, choose **Apply N marks**. | The marks are saved as drafts, not released. | |
| 5 | Choose **Download every hand-in (zip)**. | A zip file of the hand-ins downloads. | |
| 6 | Choose **Release all marks**. | Both students see their marks. | |

### LE-11 The gradebook and sending coursework to the SRMS

**Person and device:** a lecturer; desktop. **Preconditions:** AGR205 after LE-09 and LE-10. Staging must be
connected to the SRMS test service; if it is not, mark steps 4 and 5 Not tested.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Gradebook tab. | Every student with every mark and the coursework total. | |
| 2 | Open "Categories and weights", change a weight, save. | The totals change to follow the rule. | |
| 3 | Choose **Export to a spreadsheet**, then **Print**. | A spreadsheet downloads; a page to print opens. | |
| 4 | Choose **Send coursework to the SRMS** and confirm. | Sent. The SRMS test service shows the same totals, to the hundredth. | |
| 5 | Try to change a mark on the marking screen. | Refused: it is locked after sending to the SRMS. | |
| 6 | As a teaching assistant, open the Gradebook. | No button to send to the SRMS. | |

### LE-12 Question banks and quizzes

**Person and device:** a lecturer; desktop. **Preconditions:** AGR101 and its bank "Crop production questions",
category "Week 1: What a crop needs". A Moodle XML or GIFT file of two questions.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Quizzes, then "Question banks", the bank, and **New question**. | The kinds: Multiple choice, True or false, Matching, Ordering, Short answer, Numerical, Fill in the blanks, Essay, File response, Label a diagram. | |
| 2 | Add a multiple choice, a true or false, a short answer and an essay question. | All four are in the category. | |
| 3 | Choose **Import** and the file. | The two questions are added. | |
| 4 | Choose **Export**. | A file downloads. | |
| 5 | Choose **New quiz**, title "Acceptance quiz", **Create quiz**. | The quiz opens at "Settings". | |
| 6 | Set Opens now, Closes in two days, a time limit of 10 minutes, 2 attempts, a pass mark, review options, and **Save settings**. | Saved. | |
| 7 | Under "Questions" choose **Add questions**, **From the bank**, and add the four questions. | They are in the quiz. | |
| 8 | Choose **Publish to students**. | Kezia and Tevin see it. | |
| 9 | Under "Extra time" choose **Give a student more** for Tevin, 5 minutes. | Tevin's time limit is 15 minutes (ST-08). | |
| 10 | After the students' attempts, open "Marking", mark the essay answers, choose **Release marked results**. | The students see their results. | |
| 11 | Open "Results" and "Statistics". | Every attempt; how each question was answered. | |

### LE-13 Forums

**Person and device:** a lecturer; desktop. **Preconditions:** AGR101, after ST-09 (Tevin reported a post).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In the Discussion tab choose **New forum**, kind "Graded discussion", with a participation mark and a weight. | Created. | |
| 2 | In "Questions on germination" choose **Ask a question**. | Posted. Students can answer but not start a question there. | |
| 3 | Open the reported post. | **Remove the post** and **Keep the post**. | |
| 4 | Choose **Keep the post**. | The report is closed; the post stays. | |
| 5 | Choose **Pin to the top** on a discussion, then **Lock**. | It is pinned; students see "This discussion is locked: no new replies." | |
| 6 | In the graded forum, after students post, give marks and choose **Release marks to students**. | Students see "Your participation mark". | |

### LE-14 Messages

**Person and device:** a lecturer; desktop. **Preconditions:** Kezia's message from ST-10.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Messages and Kezia's message. | Kezia's message now shows "Read" on her side. | |
| 2 | Reply in "Your message" and **Send**. | Kezia receives it. | |
| 3 | **New message**, AGR101, "Send to" **The whole course, as a notice**, send. | Every student receives it and cannot reply to it. | |
| 4 | Send one to **A group, as a notice** (Lab group A). | Only that group receives it. | |
| 5 | Send one to **People I choose** (Kezia and Tevin). | Each sees it; it shows "Read by ..." as they open it. | |

### LE-15 Classes and attendance

**Person and device:** a lecturer; desktop, with the screen shown to the students. **Preconditions:** AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In the Classes tab choose **Add a class**: "Title" "Acceptance class", "Starts" in 10 minutes, "Ends" an hour later, "Room or place", "For" the whole course, tick "Take attendance at this class". Save. | The class is listed and in the calendar. | |
| 2 | Add a second class with a "Meeting link (https)". | Students see **Join online** in the calendar. | |
| 3 | Choose **Show the check-in code in the room**. | A code, changing each minute. | |
| 4 | After students check in (ST-11), open the register. | Those who checked in are marked present. | |
| 5 | Mark one student Late and one Excused, choose **Save register (N changes)**. | Saved. | |
| 6 | Choose **Mark the rest present**, save. | Everyone without a record is present. | |
| 7 | On a third class, choose **Close register: no record means absent**. | Everyone without a record is absent. | |
| 8 | Open the attendance totals and choose **Send to the SRMS** (if staging has the SRMS test service). | Sent. | |

### LE-16 Groups

**Person and device:** a lecturer; desktop. **Preconditions:** AGR101 with "Lab group A" and "Lab group B".

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Choose **New set of groups**, then **Share students at random** into two groups. | Every student is in one group. | |
| 2 | Make another set of groups with **Sign-up**, and add a group with **New group**. | Students can join it (ST-12). | |
| 3 | Set the module from LE-03 to "Only to these groups" with Lab group A. | Only Lab group A sees it. | |

### LE-17 Practical tasks (desktop)

**Person and device:** a lecturer; desktop. The field version is in [field-and-phone.md](field-and-phone.md).
**Preconditions:** AGR101; the task "Prepare a vegetable bed" at Plot 7; framework AGR-CROP-L2.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In the Practicals tab choose **New practical task**: "Where it is done", "Location", weight, "Attempts allowed", "Opens", "Closes", "Instructions", **Create task**. | Created. | |
| 2 | **Add a criterion** "Met or not met", tick "Critical"; add a scored criterion. | Both listed; the critical one is marked. | |
| 3 | Choose **Map to competency** on the critical criterion and a performance criterion of AGR-CROP-L2. | Mapped. | |
| 4 | Add Ayesha Ramdin or another staff member under "Named assessors". | Listed. | |
| 5 | Open "Prepare a vegetable bed", choose **Mark in the field**. Under "Who are you observing?" choose Kezia. | The three criteria: "Bed formed to 1.2 m wide" (critical), "Soil worked to a fine tilth" (score out of 5, pass 3), "Tools cleaned and stored". | |
| 6 | Mark **Not met** on the critical criterion, the others met. Write "Comments for the student". **Save observation**. | Saved, with the critical criterion shown as not met. | |
| 7 | Choose **Next student** and observe Tevin, all met. | Saved. | |
| 8 | Choose **Release all (N)**. | Both students see their results (ST-14). | |

### LE-18 Competency records and logbook sign-off

**Person and device:** a lecturer; desktop. **Preconditions:** AGR101; Kezia's logbook entry from ST-15.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In the Practicals tab open the competency page, then Kezia, and choose **Record for Kezia Persaud** (the button shows her name). | The choices Competent, Not yet competent, Not assessed. | |
| 2 | Choose Not yet competent and save. | Kezia sees it under "My competency". | |
| 3 | Open the Logbook tab, "Waiting for sign-off". | Kezia's entry, with its photo and location. | |
| 4 | Choose **Return with a comment**. | It goes back to Kezia (ST-15 step 5). | |
| 5 | After she corrects it, choose **Sign off**. | Signed; Kezia can no longer change it. | |
| 6 | Open "Hours by student". | Kezia's signed hours are counted. | |

### LE-19 Rubrics

**Person and device:** a lecturer; desktop. **Preconditions:** AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Rubrics and marking guides" and choose **New rubric**; add two criteria with levels, **Save the rubric**. | Saved. | |
| 2 | Choose **Copy from the GSA library**. | A rubric from the library is copied into the course. | |
| 3 | Choose the new rubric on the LE-06 assignment under "Rubric or marking guide". | The marking screen shows its levels. | |

### LE-20 Staff development and certificates

**Person and device:** a lecturer; desktop. **Preconditions:** Marlon; SD-101 (open) and SD-102 (completed, with
a certificate).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Search for `staff development` and open it. | The tabs "Catalogue", "My learning", "Learning paths", "Certificates", "Approvals". | |
| 2 | In "Search the catalogue" type `machinery`. | SD-101 Safe use of farm machinery, with **Join the course**. | |
| 3 | Choose **Join the course**, open it, read the page. | The course is under "My learning" and "Your progress" goes up. | |
| 4 | Open "Certificates" and choose **Download (PDF)** on First aid in the field. | The certificate downloads with its reference and check code. | |

### LE-21 Help and asking for help

**Person and device:** a lecturer; desktop, then phone. **Preconditions:** Marlon.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | On the marking screen choose **Help** at the top. | The lecturer's help opens at the part about marking. | |
| 2 | Search for `extension`. | A help page on extensions is among the results. | |
| 3 | Choose **Ask for help**, send a question. | Sent, with the page you were on. The answer arrives later as a notification. | |
| 4 | Is anything in this script one you could not find without help? Write it here: ____________ | (For the development team and the help pages.) | |

---

## Sign-off: lecturer

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Lecturer | | Mon Repos | | | | |
| Lecturer | | Essequibo | | | | |
| Teaching assistant (if tested) | | | | | | |
| Development team member present | | | | | | |
