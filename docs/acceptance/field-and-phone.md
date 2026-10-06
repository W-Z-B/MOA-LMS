# GSA LMS acceptance script: on a phone at Essequibo, and in the field without signal

**Version 1.0, 6 October 2026, draft for GSA's review.** For: the Essequibo lecturer and students who run these
two scripts, the course administrator at Essequibo, and the development team member who goes with them.

These are the two special scripts of item 7.18. They test the plan's bar "Works in the field": every student
task and every field checklist works at 360 pixels wide on a 3G connection, common pages weigh under 500 KB,
and work done without signal is sent when it returns, with the time the person acted.

Read [README.md](README.md) first. Everyone signs in as a fictional person, with the username and the training
password the course administrator gives you. Use low-cost Android phones, 360 pixels wide. Photographs are of
plots, plants, tools and notebooks, never of people's faces.

**Preconditions for both scripts:** on staging, the Essequibo copy of AGR101 (for example
AGR101-2026-27-S1-ESQ) with the practical task "Prepare a vegetable bed", the assignment "Acceptance assignment:
plot diary" (as LE-06), the quiz "Acceptance quiz" (as LE-12) and a class with attendance; the fictional
Essequibo lecturer and three fictional Essequibo students on it.

**Phones:** lecturer ______________ student 1 ______________ student 2 ______________ student 3 ______________
**Connection at the campus:** ______________ **Date:** ______________

---

## Script 1: On a phone at Essequibo

Run on the Essequibo campus connection, as it is on a normal teaching day. Where a step says "switch the signal
off", turn on aeroplane mode; "back on" means turning it off.

### PH-01 Signing in on the campus connection

**Person and device:** an Essequibo student, then the Essequibo lecturer; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Chrome and the staging address. Start the stopwatch. | "Sign in" opens. Time: ______ | |
| 2 | Sign in as student 1. | Home opens, with the tabs "Home", "To do", "Search", "Me" at the bottom. Nothing scrolls sideways. | |
| 3 | Sign out. Sign in as the lecturer, with the authenticator code from the testing phone. | Home opens for the lecturer. Sign out again. | |

### PH-02 Putting the LMS on the home screen

**Person and device:** student 1; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | In Chrome's menu choose to install the app or add it to the home screen. | A GSA LMS icon is on the home screen. | |
| 2 | Close Chrome and open the LMS from the icon. | It opens on its own, without Chrome's address bar, still signed in. | |

### PH-03 Reading a page and a PDF

**Person and device:** student 1; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the course, the Content tab, and a page. | It opens and reads well. Time to open: ______ | |
| 2 | Choose **Mark complete**. | "Complete". | |
| 3 | Open a PDF and use **Next page**. | The pages show inside the LMS. Time to first page: ______ | |
| 4 | Switch the signal off and open the page read in step 1 again. | The page read before still opens. | |
| 5 | Switch the signal back on. | The LMS carries on as before; nothing is waiting to send. | |

### PH-04 Handing in a typed answer and a photo

**Person and device:** student 1; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | **Timed:** from Home, hand in "Acceptance assignment: plot diary" with a typed answer and, under "Files (up to N)", a photo taken there and then with the phone's camera. | "Received:" and a receipt code, in **under two minutes**. Time: ______ | |
| 2 | Switch the signal off. Choose **Hand in again**, change the typed answer, attach a photo, choose **Hand in**. | Refused clearly for the photo: "No connection. Attach the files again when you are back online." | |
| 3 | Remove the photo and hand in the typed answer alone. | It waits on the phone; the header shows "1 waiting to send". | |
| 4 | Switch the signal back on. | The answer is sent, once. A receipt is given. "Every hand-in and its receipt" shows the time it was handed in on the phone. | |
| 5 | As the lecturer, open the hand-ins. | One new hand-in from student 1, not two. | |

### PH-05 A quiz with the signal switched off part way

**Person and device:** student 2; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Switch the signal off and choose **Start the quiz**. | Refused: "No connection. A quiz needs a connection to start." | |
| 2 | Switch the signal on and choose **Start the quiz**. Answer the first page. | "Time left" counts down. | |
| 3 | Switch the signal off. Answer the next pages, using **Next page**. | The answers are kept on the phone; the header shows answers waiting to send. "Time left" keeps counting. | |
| 4 | Choose **Finish attempt...**, then **Submit my answers**, while the signal is still off. | Refused until the signal returns, because answers are still waiting. Nothing is lost. | |
| 5 | Switch the signal back on. | The waiting answers are sent. | |
| 6 | Choose **Submit my answers**. | Submitted. | |
| 7 | As the lecturer, open "Results" for student 2. | Every answer given is there, including those given without signal. | |

### PH-06 Checking in to a class

**Person and device:** student 3 and the lecturer; phones.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | The lecturer chooses **Show the check-in code in the room** on the phone. | A code, changing each minute. | |
| 2 | Student 3 opens the Classes tab, **Check in**, types the code in "Code on the screen", **Check in**. | Checked in. Time from opening the tab: ______ | |
| 3 | Student 3 switches the signal off and tries to check in again. | Refused clearly: checking in needs signal. | |

### PH-07 Page weight and time to open on a slow line

**Person and device:** the development team member, with a laptop on the same Essequibo connection, and student
1's phone. The weight is the amount the browser's developer tools show as transferred, with the browser's store
of earlier pages emptied first.

| Page | Time to open on the phone (target under 5 seconds on a 2 Mbps line) | Weight (target under 500 KB) | Result |
|---|---|---|---|
| Sign in | | | |
| Home | | | |
| To do | | | |
| A course's Content tab | | | |
| A page of content | | | |
| The assignment and its hand-in | | | |
| A quiz page | | | |
| The logbook's "Add an entry" | | | |
| The practical task's "Mark in the field" | | | |

Write down the connection speed measured at the time: ______ Mbps.

### PH-08 Asking for help without signal

**Person and device:** student 2; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the assignment, choose **Help** at the top. | The student's help opens. | |
| 2 | Switch the signal off. Choose **Ask for help**, write a question, send it. Note the time: ______ | It waits on the phone and the header shows it waiting. | |
| 3 | Switch the signal back on. | It is sent, once. | |
| 4 | The Essequibo course administrator opens "Help requests" (CA-02). | The question, the page it was asked from, and the time noted in step 2. | |
| 5 | After the answer, open the bell on the phone. | The answer is there as a notification. | |

### PH-09 Signing out on a shared phone

**Person and device:** students 1 and 2, sharing student 1's phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Student 1 signs in, switches the signal off, writes a message to the teaching staff and a typed hand-in. | Both wait; the header shows "2 waiting to send". | |
| 2 | Student 1 signs out from the avatar menu. | Signed out. If the phone warns about work still waiting, write down what it says: ______ | |
| 3 | Student 2 signs in on the same phone, then switches the signal on. | Student 2's Home, To do and Messages show nothing of student 1's. | |
| 4 | The lecturer looks at messages and hand-ins. | Nothing has arrived from either student: student 1's work is never sent while someone else is signed in. | |
| 5 | Student 2 signs out. Open the LMS from the home-screen icon. | "Sign in" is shown; nothing of either student is shown. | |
| 6 | Student 1 signs in again, with signal. | The header shows the two writes waiting, then they are sent, once each, under student 1's name with the time they were written. The lecturer sees them. | |

---

## Script 2: During a field practical without signal

Run on a farm plot with no signal, or with every phone in aeroplane mode from the moment the group reaches the
plot. Each person writes down on paper, in the table at the end, the time by the phone's clock of each thing
they do, so that the times the system records can be checked.

### FD-01 Before going out, with signal

**Person and device:** the lecturer and the three students; phones, on the campus connection.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | The lecturer opens the course, the Practicals tab, "Prepare a vegetable bed", and **Mark in the field**, with the class list. | The task, its three criteria and the class list open. | |
| 2 | The lecturer opens the register of the class that day. | The register opens with every student. | |
| 3 | Each student opens the course's Logbook tab and **Add an entry**, then goes back without saving. | The form opens. | |
| 4 | The lecturer, in aeroplane mode, tries a second practical task never opened before. | "Open it once with signal to mark it in the field." | |

### FD-02 Observing three students on the plot

**Person and device:** the lecturer; phone in aeroplane mode on the plot.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open "Prepare a vegetable bed", **Mark in the field**. | The task and the class list open without signal. | |
| 2 | Under "Who are you observing?" choose student 1. Mark each criterion **Met** or **Not met**, the score for the fine tilth, **Add a comment**, "Comments for the student". | Each is recorded on the screen. | |
| 3 | Take two photos and choose **Add my location**. | The photos and the location are attached. | |
| 4 | Choose **Save observation**. Note the time. | Saved on the phone; the header shows it waiting to send; the photos wait in the phone's outbox. | |
| 5 | Choose **Next student** and observe students 2 and 3 the same way, one with a critical criterion not met. | Each is saved on the phone. | |
| 6 | Try to add an eleventh photo to one observation. | Refused: up to 10 photos. | |

### FD-03 Students writing logbook entries

**Person and device:** the three students; phones in aeroplane mode on the plot.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Each student chooses **Add an entry**, fills "Date of the work", "Hours", "Where", "Which unit", "What you did", **Take a photo**, **Add my location**, **Save entry**. Note the time. | "Entry saved". "1 photo waiting to send. They are sent after the record." | |
| 2 | Choose **Back to my logbook**. | The entry is under "Waiting on this phone". | |
| 3 | Student 1 writes a second entry with three photos. | Saved on the phone, with the photos waiting. | |

### FD-04 Taking the register on the phone

**Person and device:** the lecturer; phone in aeroplane mode.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the register. | It opens from the copy on the phone. | |
| 2 | Mark student 1 Present, student 2 Late, student 3 Absent. Choose **Save register (N changes)**. Note the time. | Saved on the phone, waiting to send. | |
| 3 | Choose **Close register: no record means absent**. | Refused clearly: closing a register needs signal. | |

### FD-05 What must fail clearly without signal

**Person and device:** student 2; phone in aeroplane mode.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Choose **Start the quiz** on "Acceptance quiz". | "No connection. A quiz needs a connection to start." Nothing else happens. | |
| 2 | Hand in the assignment with a photo attached. | "No connection. Attach the files again when you are back online." | |
| 3 | Open the Classes tab and choose **Check in**. | Refused clearly: checking in needs signal. | |
| 4 | In each case, check the phone did not freeze and the student could go on with other work. | The LMS still works for the tasks that work without signal. | |

### FD-06 Back in signal: everything arrives once, with the right times

**Person and device:** everyone; phones, back on the campus connection; then the lecturer on a desktop.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Switch aeroplane mode off on every phone and leave the LMS open. | The "waiting to send" counts fall to nothing. Records go first, then photos. | |
| 2 | On the desktop, the lecturer opens the practical task's observations. | Three observations, one for each student, each once, with its photos and location. | |
| 3 | Check the time on each observation against the paper table. | The time is when the lecturer saved it on the plot, not when the signal returned. | |
| 4 | Open the Logbook tab, "Waiting for sign-off". | Four entries (two from student 1), each once, with photos, location and the time written on the plot. | |
| 5 | Open the register. | Present, Late and Absent as marked on the plot, each once. | |
| 6 | With signal, choose **Close register: no record means absent**. | Closed. | |
| 7 | Release the observations with **Release all (N)**. Each student opens "My practicals". | Each sees their own result and comments only. | |
| 8 | The auditor or administrator opens the audit log for the lecturer's observations. | Each recorded once, under the lecturer's name, with the time the lecturer acted. | |

### FD-07 Signing out of the field phone

**Person and device:** the lecturer; phone.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Check nothing is waiting to send, then choose **Sign out**. | Signed out. | |
| 2 | Switch the signal off and open the LMS from the home-screen icon (or Chrome). | "Sign in" is shown. Neither the task nor the class list can be opened: the field copies were cleared from the phone at sign-out. | |

### Times written on paper during the field practical

| Who | What they did | Time on the phone | Time shown in the LMS afterwards | Same? |
|---|---|---|---|---|
| Lecturer | Observation of student 1 | | | |
| Lecturer | Observation of student 2 | | | |
| Lecturer | Observation of student 3 | | | |
| Lecturer | Register saved | | | |
| Student 1 | Logbook entry 1 | | | |
| Student 1 | Logbook entry 2 | | | |
| Student 2 | Logbook entry | | | |
| Student 3 | Logbook entry | | | |

---

## Sign-off: phone and field

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Lecturer | | Essequibo | | | | |
| Student | | Essequibo | | | | |
| Student | | Essequibo | | | | |
| Student | | Essequibo | | | | |
| Course administrator | | Essequibo | | | | |
| Development team member present | | | | | | |
