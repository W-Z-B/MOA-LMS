# GSA LMS acceptance script: student

**Version 1.0, 6 October 2026, draft for GSA's review.** For: GSA students testing the LMS at Mon Repos and
Essequibo, and the development team member who sits with them.

Read [README.md](README.md) first: it explains the staging system, the fictional accounts and how to record a
result. You sign in as a fictional student, with the username and the training password the course
administrator gives you. Use only made-up answers and photographs of plots, plants or notebooks, never of
people.

Some cases use work the lecturer makes in [lecturer.md](lecturer.md): the assignment "Acceptance assignment:
plot diary" (LE-06), the quiz "Acceptance quiz" (LE-12) and the class "Acceptance class" (LE-15). Run those
lecturer cases first.

**Tester:** ______________ **Campus:** ______________ **Phone make and model:** ______________
**Connection:** ______________ **Date:** ______________

---

### ST-01 First sign-in from an invitation

**Person and device:** a student; desktop. **Preconditions:** the fictional new student Rohan Singh (or Priya
Bhagwandin at the second campus), whose account is open but who has not chosen a password. The development
team gives the tester the invitation link.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the invitation link. | The page "Welcome: choose your password" opens, with "New password" and "New password again". | |
| 2 | Type `password1234` in both boxes and choose **Save my password**. | Refused: the password is too common. The rule is shown: at least 12 characters, not a common password, not only numbers, not close to your name or username. | |
| 3 | Choose **Show the password**, then type a made-up password of 12 or more characters that follows the rule, in both boxes, and choose **Save my password**. | The password is saved and you can go on to sign in. | |
| 4 | Sign in with the username and the new password. | The privacy notice opens. | |
| 5 | Read it and choose **I have read this notice**. | Home opens. | |
| 6 | Open **My courses**. | "Getting started with the GSA LMS" is listed. No other course is listed unless the Registry has enrolled the student; if none, the page says "Academic courses appear here once the Registry enrols you in the SRMS." | |
| 7 | Choose the avatar at the top, then **Sign out**. Sign in again. | The privacy notice is not shown again. Home opens. | |

### ST-02 Signing in, a forgotten password and signing out

**Person and device:** a student; desktop, then phone. **Preconditions:** Kezia Persaud's account.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the staging address. | The page "Sign in" shows "Use your GSA account: staff and students alike." | |
| 2 | Type the username and a wrong password, and choose **Sign in**. | Refused. The student is not signed in. | |
| 3 | Choose **Forgot your password?**, type the username and choose **Email me a link**. | The same message is shown whether or not the account exists. It says to ask the course administrator if you have no email address on file. | |
| 4 | Choose **Back to sign in** and sign in with the training password. | Home opens. No authenticator code is asked of a student. | |
| 5 | On the phone, sign in as Kezia too. On the desktop, open the avatar menu, then **My account**. | "Signed-in devices" lists two devices, one marked "This device". | |
| 6 | Choose **Sign out** beside the phone. | The phone is signed out and must sign in again. | |

### ST-03 The orientation course

**Person and device:** a student; phone. **Preconditions:** Rohan Singh after ST-01.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open My courses, then "Getting started with the GSA LMS". | The Content tab shows four modules: "1. Finding your way", "2. Your courses", "3. Phones, the field and practice" and "4. Getting help". | |
| 2 | Open "Welcome to the GSA LMS", read it and choose **Mark complete**. | The button changes to "Complete". The count of pages read goes up ("N of M complete"). | |
| 3 | Read every other page and mark each complete, except "Help, your data and who to ask". | The count goes up each time. The course is not yet shown as complete. | |
| 4 | Open "Practice quiz: finding your way" and choose **Start the quiz**. Answer every question and choose **Finish attempt...**, then **Submit my answers**. | The attempt is marked and the result shown. It does not count towards any mark. | |
| 5 | Open "Practice: write a logbook entry" and follow it to save a practice entry. | "Entry saved" is shown. | |
| 6 | Open "Help, your data and who to ask" and choose **Mark complete**. | Every page is complete and the course is shown as complete. | |

### ST-04 Home, To do, search and notifications

**Person and device:** a student; desktop, then phone. **Preconditions:** Kezia Persaud; AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open Home. | The shortcuts "My courses", "To do" and "My data"; the figures "Due this week", "Overdue" and "New feedback"; "Field notebook check" due in three days. | |
| 2 | Open **To do**. | "Field notebook check" is listed with **Open it**, oldest first. | |
| 3 | Press Ctrl and K together, type `germ`. | The search box opens; results are grouped ("Courses", "Content", "Assignments", "Quizzes", "Pages", "Help"); "Week 2: Seed and germination" is among them. No "People" group is shown to a student. | |
| 4 | Type `zzqq`. | "Nothing matches that. Try a course code, the title of an assignment or a page." | |
| 5 | Choose the bell at the top. | "Notifications" opens with up to 15, or "Nothing yet." | |
| 6 | Open one notification. | It is marked read and opens the page it is about. | |
| 7 | On the phone, use the tabs at the bottom: "Home", "To do", "Search", "Me". | Each opens the right page. Nothing on the page needs scrolling sideways. | |

### ST-05 Reading course material

**Person and device:** a student; phone. **Preconditions:** Kezia Persaud; AGR101 with its PDF and pages.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open AGR101, then the Content tab. | The modules are listed with "N of M complete". | |
| 2 | Open "Week 2: Seed and germination". | The page opens and reads well at phone width. | |
| 3 | Choose **Mark complete**. | It changes to "Complete" and the count goes up. | |
| 4 | Open a PDF in the course. | The PDF opens inside the LMS with **Previous page** and **Next page**. | |
| 5 | Choose the download button ("Download" and the file name). | The file downloads to the phone. | |
| 6 | Open the Announcements tab. | The course's announcements are listed for reading. | |

### ST-06 Handing in work (timed)

**Person and device:** a student; desktop, then phone. **Preconditions:** Kezia Persaud; "Acceptance
assignment: plot diary" from LE-06 (typed answer, up to three photographs, integrity statement). A photograph of
a plot or plant saved on the device.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | **Timed:** start the stopwatch on Home. Without help, find the assignment and hand in a typed answer and one photograph. Stop the stopwatch at the receipt. | Done unaided in **under two minutes**. Time: ______ | |
| 2 | Look at the assignment page before handing in (repeat on the phone). | It shows "Due", "What to hand in", "Late work" and "Group work". | |
| 3 | Try to hand in without ticking the integrity statement. | Refused until it is ticked. | |
| 4 | After **Hand in**, read the receipt. | "Received:" with the date, time and a receipt code. **Print the receipt** prints it. | |
| 5 | Choose **Hand in again**, change the answer and hand in. | A new receipt. "Every hand-in and its receipt" lists both. | |
| 6 | Under **Look up a receipt**, type the first receipt code and choose **Look up**. | The first hand-in is found with its time. | |
| 7 | On the phone, choose a file of a kind the assignment does not accept (for example a Word file). | Refused, saying which kinds are accepted. | |
| 8 | Open the AGR205 "Soil profile report" as Ria Ramdial (a closed, late assignment). | The deadline has passed and it says so; the hand-in cannot be replaced. | |

### ST-07 Feedback, marks and the gradebook

**Person and device:** a student; desktop. **Preconditions:** Kezia Persaud (a marked assignment in AGR101);
Ria Ramdial after the lecturer's LE-09 (rubric, late penalty, spoken feedback).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | As Kezia, open the marked assignment. | "Marked: X out of Y" and the feedback. | |
| 2 | As Ria, open "Soil profile report". | The mark, the late penalty line (5% a day), the rubric details, the feedback and "Spoken feedback" that plays. | |
| 3 | Open the Gradebook tab. | Only your own row. "How your coursework total is worked out" explains the total. | |
| 4 | Check the total by hand from the marks and weights shown. | It matches. | |
| 5 | If the lecturer has sent coursework to the SRMS (LE-11), open the assignment again. | "Sent to the SRMS on ...: the mark is final here." | |

### ST-08 Taking a quiz

**Person and device:** a student; desktop. **Preconditions:** Kezia Persaud; "Acceptance quiz" from LE-12
(time limit, two attempts). Tevin Joseph has extra time given by the lecturer.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Quizzes tab, then the quiz. | Its opening and closing times, time limit and attempts are shown. | |
| 2 | Choose **Start the quiz**. | The first page opens with "Time left". | |
| 3 | Answer, use **Next page** and **Previous page**. | Answers are kept when moving between pages. | |
| 4 | Close the browser tab, open the quiz again. | **Continue my attempt** is offered; the answers are still there and the time has kept running. | |
| 5 | Choose **Finish attempt...**, then **Submit my answers**. | The attempt is submitted. What is shown afterwards follows the quiz's review settings. | |
| 6 | Choose **Start another attempt**, answer one question and leave it until the time runs out. | The attempt is submitted on its own when the time is up. | |
| 7 | Under "Your attempts", choose **Review**. | The attempt is shown as the review settings allow. | |
| 8 | As Tevin, start the quiz. | "Time left" includes his extra time. | |

### ST-09 Forums

**Person and device:** a student; phone. **Preconditions:** Kezia and Tevin; AGR101's forums "Questions on
germination" and "Class discussion".

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Discussion tab, then "Class discussion", and start a discussion with **Start a discussion**. | The form "Title" and "Your post". If "Rules for forums and messages" is shown, choose **I accept these rules**. | |
| 2 | Write a "Title" and "Your post" and choose **Post**. | The discussion is listed. | |
| 3 | Choose **Change** on your post, alter it and save. | Changed. (Your own post can be changed for 30 minutes.) | |
| 4 | Open "Questions on germination" as Tevin, before he has answered a question. | Other students' answers are hidden until he posts his own. | |
| 5 | As Tevin, post an answer with **Reply**, "Your reply", **Post reply**. | The other answers now show. | |
| 6 | As Tevin, choose **Report** on Kezia's post, pick a rule under "Which rule does it break?" and **Send report**. | The report is sent; the lecturer sees it (LE-13). | |
| 7 | Choose **Get notices of new posts**, then **Stop notices**. | Each takes effect. | |
| 8 | Switch on aeroplane mode and try to post. | Refused clearly: posting needs signal. | |
| 9 | Open the Discussion tab's participation section. | "Your participation mark" is shown for a graded discussion, if there is one. | |

### ST-10 Messages

**Person and device:** a student; desktop. **Preconditions:** Kezia Persaud; AGR101.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open **Messages**, then **New message**. | The form "Course", "Subject", "Message". | |
| 2 | Choose AGR101, leave "To the teaching staff (none ticked: all of them)" unticked, write a subject and message, choose **Send**. | The first time, "Rules for forums and messages" is shown and **I accept these rules** must be chosen. Then it is sent and shows "Not read yet". | |
| 3 | After the lecturer has opened it (LE-14). | It shows "Read". | |
| 4 | Open a notice the lecturer sent to the whole course. | "This is a notice from the teaching staff, so it takes no replies." with **Write to the teaching staff**. | |
| 5 | On the phone, switch on aeroplane mode, write a message and send. | "Waiting to send. It is sent when the connection returns." The header shows "1 waiting to send". | |
| 6 | Switch aeroplane mode off. | It changes to "Sent". | |

### ST-11 Checking in to a class

**Person and device:** a student; phone. **Preconditions:** Kezia Persaud; "Acceptance class" from LE-15,
starting within 15 minutes; the lecturer shows the code in the room.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Classes tab more than 15 minutes before the class. | Check-in is not yet open. | |
| 2 | Within 15 minutes of the start, choose **Check in**, type the code from the lecturer's screen in "Code on the screen", choose **Check in**. | Checked in. | |
| 3 | Type a code more than two minutes old. | Refused. | |
| 4 | Open "Your attendance". | The class is listed with your record. | |
| 5 | Switch on aeroplane mode and try to check in to another class. | Refused clearly: checking in needs signal. | |

### ST-12 Groups

**Person and device:** a student; desktop. **Preconditions:** Kezia; a sign-up set of groups from LE-16.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Groups tab. | "My groups" and "Groups you can join". | |
| 2 | Choose **Join** on a group. | It moves to "My groups". | |
| 3 | Choose **Leave**. | It moves back. | |

### ST-13 The calendar

**Person and device:** a student; desktop, then phone. **Preconditions:** Kezia Persaud.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Search for `calendar` and open it. | The month shows "Due", "Quiz closes", "Class" and other events for the courses. | |
| 2 | Choose **Agenda**, then "Course" and AGR101. | The next 28 days for AGR101 only. | |
| 3 | Open the calendar on the phone. | It opens in Agenda. | |
| 4 | Under "Your calendar on your phone", choose **Make my private address**, then **Copy address**. | An address is copied. | |
| 5 | Choose **Make a new address**, then **Make it: the old address stops working**. | A new address; the old one no longer works. | |
| 6 | Choose **Turn off**. | The address stops working. | |

### ST-14 Practicals, competency and portfolio

**Person and device:** a student; phone. **Preconditions:** Kezia, after the lecturer has observed her on
"Prepare a vegetable bed" and released the results (LE-17).

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Practicals tab. | "My practicals" lists "Prepare a vegetable bed". | |
| 2 | Open it. | "What the assessor looks for" lists the three criteria. The released result and "Comments for the student" are shown. | |
| 3 | Open "My competency". | Her record against AGR-CROP-L2 Crop Production Level 2. | |
| 4 | Open "Portfolio" and choose **Download this course (page to print)**. | A printable page of her practical record. | |
| 5 | Choose **Download as data (JSON)**. | A file downloads. | |

### ST-15 The logbook

**Person and device:** a student; phone. **Preconditions:** Kezia; AGR101's Logbook tab.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the Logbook tab and choose **Add an entry**. | The form "Date of the work", "Hours", "Where", "Which unit", "What you did", "Notes". | |
| 2 | Type 30 in "Hours". | Refused: hours are from 0.25 to 24. | |
| 3 | Fill it in with 2 hours, **Take a photo** of a plant, **Add my location**, **Save entry**. | "Entry saved", with **Add another entry** and **Back to my logbook**. | |
| 4 | Choose **Back to my logbook**. | The entry is listed, waiting for sign-off. "Hours by kind of place" includes it. | |
| 5 | After the lecturer returns it with a comment (LE-18), open it and choose **Correct and send again**, change it and choose **Send the correction**. | Sent back for sign-off. | |
| 6 | After the lecturer signs it off, open it. | It is locked and cannot be changed. | |

### ST-16 My account, my data and notifications

**Person and device:** a student; desktop. **Preconditions:** Kezia Persaud.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open **My account**, "Your password": type the current password and a new one twice, choose **Change password**. | Changed. Other devices are signed out. | |
| 2 | Open **My data** and choose **Download my data**. | A file downloads. The page lists "Courses", "Submissions", "Marks released to you", "Courses completed", "What I did in the LMS" and "Sign-ins". | |
| 3 | Check "What I did in the LMS". | Sign-ins, downloads and hand-ins are listed; time spent on pages is not. | |
| 4 | Choose **Ask for a correction**, fill "What is it about", "What is wrong", "What it should say", choose **Send the request**. | Sent. The course administrator sees it (CA-09). | |
| 5 | Choose **Read the privacy notice (version N)**. | The notice opens. | |
| 6 | Open the notification settings and choose **No email** for one kind, then **In a daily summary email** for another. | Each is saved when chosen. | |
| 7 | Leave the LMS untouched for 30 minutes, then choose any link. | You are asked to sign in again. | |

### ST-17 Help and asking for help

**Person and device:** a student; desktop. **Preconditions:** Kezia Persaud.

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | On the assignment page, choose **Help** at the top. | The student's help opens at the part about handing in. | |
| 2 | Search for `hand in`. | Help pages are among the results. | |
| 3 | Choose **Ask for help**, fill in **What do you need help with?** and **What were you trying to do, and what happened?**, and choose **Send to the course administrators**. | "Sent. The course administrators have your request"; **Send the page I was on** was ticked. | |
| 4 | After the course administrator answers (CA-02), open the bell. | The answer is there as a notification. | |

### ST-18 Using the keyboard only, and zoom

**Person and device:** a student; desktop. **Preconditions:** Kezia; "Acceptance assignment: plot diary".

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Without the mouse, using Tab, Shift and Tab, and Enter, go from Home to the assignment and hand in a typed answer. | Every control can be reached and the one in use is clearly outlined. | |
| 2 | Zoom the browser to 200% and open Home and the assignment. | Everything can still be read and used without scrolling sideways. | |

---

## Sign-off: student

| Role | Name | Campus | Date | Cases passed | Cases failed | Decision (Accept / Accept with conditions / Do not accept) |
|---|---|---|---|---|---|---|
| Student | | | | | | |
| Student | | | | | | |
| Development team member present | | | | | | |
