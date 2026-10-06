/**
 * The help pages (item 7.17): for each role, every task the screens support today, as short numbered steps.
 * Labels in **bold** are the words on the screen, so a reader can find the button they are told to press.
 * Kept here, loaded only when Help (or search) needs it, so the frame every page loads stays light.
 *
 * Each task has a topic: the Help link at the top of a page opens the reader's own help at the first task on
 * that topic (app/help.ts says which topic each address belongs to). Keep the steps in step with the screens:
 * a changed label is a changed step.
 */

import type { Me, Persona } from "../../api/types";

export interface HelpTask {
  /** Unique within its role page; the last part of its address, #/help/student/hand-in. */
  id: string;
  title: string;
  /** Which part of the LMS it is about, for the Help link at the top of a page. */
  topic: string;
  steps: string[];
  /** A rule or a warning that goes with the steps. */
  note?: string;
  /** Other words people may search with. */
  words?: string;
}

export interface HelpSection {
  title: string;
  tasks: HelpTask[];
}

export interface HelpRole {
  id: string;
  title: string;
  /** Who the page is for, in a sentence. */
  who: string;
  /** The Homes whose help this is first: the reader's own page. */
  personas: readonly Persona[];
  sections: HelpSection[];
}

const OFFLINE =
  "Without signal, it waits on this phone and is sent when the signal returns. The top of the screen says how many are waiting to send.";

// --- Getting started: the same for everyone, with the authenticator code only for staff who need one ---

const signIn = (staff: boolean): HelpTask[] => [
  {
    id: "sign-in",
    topic: "home",
    title: "Sign in",
    steps: [
      "Open the GSA LMS. On a phone, add it to your home screen from the browser's menu so it opens like an app.",
      "Type your **Username** and **Password**, and choose **Sign in**.",
      ...(staff
        ? [
            "Open the authenticator app on your phone and type the 6-digit code it shows for GSA LMS in **Authenticator code**, then choose **Verify**.",
          ]
        : []),
      "The first time, and whenever the privacy notice changes, read it and choose **I have read this notice**.",
    ],
    note: staff
      ? "Lecturers, anyone teaching a course, and administrators need an authenticator code. The first time, add the account to your authenticator app as the screen shows, then enter the code."
      : undefined,
    words: "log in login password authenticator code",
  },
  {
    id: "forgot-password",
    topic: "account",
    title: "Get a new password if you have forgotten it",
    steps: [
      "On the sign-in page, choose **Forgot your password?**",
      "Type your **Username or email address** and choose **Email me a link**.",
      "Open the link in the email, type the new password twice and choose **Save my password**.",
    ],
    note: "A password has at least 12 characters, is not a common password, not only numbers, and not close to your name. If you have no email address on file, ask the course administrator.",
    words: "reset forgotten password link",
  },
  {
    id: "find-things",
    topic: "search",
    title: "Find a course, a piece of work or a page",
    steps: [
      "On a computer press **Ctrl** and **K** together, or choose the search bar at the top. On a phone choose **Search** at the bottom.",
      "Type at least two letters: a course code, part of a title or the name of a page.",
      "Use the up and down arrows and press Enter, or tap the result.",
    ],
    words: "search find look up",
  },
  {
    id: "to-do",
    topic: "todo",
    title: "See what is waiting for you",
    steps: [
      "Choose **To do** at the top (or at the bottom on a phone).",
      "Everything waiting for you is listed, the oldest first. Anything past its time is marked **Overdue**.",
      "Choose **Open it** to go to where it is done.",
    ],
    words: "tasks waiting overdue",
  },
  {
    id: "notifications",
    topic: "notifications",
    title: "Read your notifications",
    steps: [
      "Choose the bell at the top. The number on it is how many you have not read.",
      "Choose a notification to open what it is about; it is then marked read.",
      "Choose **Mark all read** to clear the number.",
    ],
    words: "bell alerts",
  },
  {
    id: "email-settings",
    topic: "notification-settings",
    title: "Choose which notifications come by email",
    steps: [
      "Choose your initials at the top right, then **Notification settings**.",
      "For each kind of notification choose **An email now**, **In a daily summary email** or **No email**. It is saved at once.",
    ],
    note: "Notifications always appear in the LMS, whatever you choose for email.",
    words: "email summary daily",
  },
  {
    id: "messages",
    topic: "messages",
    title: "Send and read messages",
    steps: [
      "Choose the Messages icon at the top, then **New message**.",
      "Choose the **Course**, write a **Subject** and your **Message**, and choose **Send**.",
      "Open a conversation to read it and reply in **Your message**. Under each message you see who has read it.",
    ],
    note: `The first time, read the rules for forums and messages and choose **I accept these rules**. ${OFFLINE}`,
    words: "message write lecturer chat inbox",
  },
  {
    id: "calendar",
    topic: "calendar",
    title: "See your calendar, and put it on your phone",
    steps: [
      "Search for **Calendar** and open it. Choose **Month** or **Agenda**; **Course** shows one course only.",
      "To see it in your phone's own calendar, choose **Make my private address**, then **Copy address**, and add it to the phone's calendar as a subscription.",
      "If someone else may have the address, choose **Make a new address**: the old one stops working.",
    ],
    note: "The private address shows titles, times and places, never marks or messages. Keep it to yourself.",
    words: "dates due deadlines feed",
  },
  {
    id: "account",
    topic: "account",
    title: "Change your password, sign-in email or signed-in devices",
    steps: [
      "Choose your initials at the top right, then **My account**.",
      "To change your password, fill in **Current password**, **New password** twice, and choose **Change password**. Other devices are signed out.",
      "To change your sign-in email, type the **New email address** and **Your password**, choose **Send the link**, and follow the link in the email.",
      "Under **Signed-in devices**, choose **Sign out** beside a device you do not recognise, or **Sign out everywhere else**.",
    ],
    note: "You are signed out after 30 minutes without activity, and after 8 hours in any case.",
    words: "password email devices security",
  },
  {
    id: "my-data",
    topic: "my-data",
    title: "See your data, and ask for a correction",
    steps: [
      "Choose your initials at the top right, then **My data**.",
      "Read what the LMS holds about you, or choose **Download my data** for all of it.",
      "If something is wrong, under **Ask for a correction** choose **What is it about**, say **What is wrong** and **What it should say**, and choose **Send the request**.",
    ],
    note: "A course administrator answers within 30 days. Names, numbers and class lists are corrected in the student or staff records system and come across from there.",
    words: "privacy personal data correction download",
  },
  {
    id: "ask-for-help",
    topic: "help",
    title: "Ask for help",
    steps: [
      "Choose **Help** at the top of the page you are on, or search for **Help**.",
      "Choose **Ask for help**. The page you were on is sent with your question.",
      "Say in a few words what you need help with, then what you were trying to do and what happened, and choose **Send to the course administrators**.",
      "The answer comes back as a notification. **My help requests** lists your questions and their answers.",
    ],
    note: OFFLINE,
    words: "support stuck problem question",
  },
  {
    id: "sign-out",
    topic: "account",
    title: "Sign out, especially on a shared phone",
    steps: ["Choose your initials at the top right (**Me** on a phone), then **Sign out**."],
    note: "On a shared phone always sign out. What you left waiting to send is sent only when you sign in again, never under someone else's name.",
    words: "log out shared phone",
  },
];

// --- Students ---

const STUDENT: HelpRole = {
  id: "student",
  title: "Students",
  who: "For every student at Mon Repos and Essequibo.",
  personas: ["student"],
  sections: [
    { title: "Getting started", tasks: signIn(false) },
    {
      title: "Your courses",
      tasks: [
        {
          id: "orientation",
          topic: "courses",
          title: "Take the orientation course",
          steps: [
            "Open **My courses** and choose **Getting started with the GSA LMS**. You are put on it when you first sign in.",
            "Read each page and choose **Mark complete** at the bottom of it.",
            "Try the practice quiz on its **Quizzes** tab and write a practice entry on its **Logbook** tab.",
          ],
          note: "It takes about an hour and is complete when every page is marked complete. The practice quiz does not count towards anything.",
          words: "orientation getting started new student induction",
        },
        {
          id: "read-content",
          topic: "content",
          title: "Find and read your course material",
          steps: [
            "From Home choose **My courses**, then the course.",
            "The **Content** tab lists the weeks or topics. Open a page to read it, or a file to see it; **Download** keeps a copy.",
            "Choose **Mark complete** when you have finished an item. **N of M complete** shows how far you are.",
          ],
          note: "Some material appears only from a set date, or after you have finished an earlier item. Courses appear once the Registry enrols you.",
          words: "content notes handouts pdf week module",
        },
        {
          id: "announcements",
          topic: "announcements",
          title: "Read announcements",
          steps: ["Open the course and its **Announcements** tab. New announcements also come as notifications."],
        },
      ],
    },
    {
      title: "Handing in work",
      tasks: [
        {
          id: "hand-in",
          topic: "assignments",
          title: "Hand in an assignment",
          steps: [
            "Open the course, its **Assignments** tab, and choose **Open** beside the assignment.",
            "Read **Due**, **What to hand in** and **Late work**.",
            "Type **Your answer**, or attach your file under **Files**, or both, as the assignment asks.",
            "Tick the statement that the work is your own if the assignment asks for it, and choose **Hand in**.",
            "Keep the receipt: **Received** shows the time. **Print the receipt** prints it.",
          ],
          note: `Until the work is marked you may choose **Hand in again**; the newest copy is marked. A typed answer: ${OFFLINE} A file needs signal: attach it again when you are back in range.`,
          words: "submit upload assignment coursework receipt",
        },
        {
          id: "receipt",
          topic: "assignments",
          title: "Check a receipt",
          steps: [
            "Open the assignment. **Every hand-in and its receipt** lists them all.",
            "To check a receipt code someone gives you, use **Look up a receipt**: type the **Receipt code** and choose **Look up**.",
          ],
        },
        {
          id: "extension",
          topic: "assignments",
          title: "Ask for more time",
          steps: [
            "Before the due date, write to your lecturer from **Messages** and say why.",
            "If the lecturer grants it, the assignment shows the new date marked **(extended for you)**.",
          ],
          note: "Accommodations agreed with the course administrator, such as more time in quizzes, apply without asking each time.",
          words: "extension late deadline more time",
        },
        {
          id: "feedback",
          topic: "gradebook",
          title: "Read your mark and feedback",
          steps: [
            "You are told by a notification when a mark is released. Home lists **New feedback**; choose **Read**.",
            "The assignment shows **Marked: X out of Y**, the feedback, any spoken feedback to play, and the rubric.",
            "The **Gradebook** tab shows all your marks and **How your coursework total is worked out**.",
          ],
          words: "marks grades results gradebook",
        },
      ],
    },
    {
      title: "Quizzes",
      tasks: [
        {
          id: "take-quiz",
          topic: "quizzes",
          title: "Take a quiz",
          steps: [
            "Open the course, its **Quizzes** tab, and the quiz.",
            "Read when it closes, the time limit and how many attempts you have, then choose **Start the quiz**.",
            "Answer each question. Use **Next page** and **Previous page** to move.",
            "Choose **Finish attempt…**, then **Submit my answers**.",
          ],
          note: "Starting a quiz needs signal. After that each answer is saved as you give it; if the signal drops, carry on: answers wait on the phone and are sent when it returns. A timed quiz is submitted for you when time runs out. In some quizzes you cannot go back to an earlier page.",
          words: "test exam attempt",
        },
        {
          id: "quiz-review",
          topic: "quizzes",
          title: "Review a quiz you have taken",
          steps: ["Open the quiz. Under **Your attempts** choose **Review**."],
          note: "What you see (your score, the right answers, feedback) depends on the quiz's settings.",
        },
      ],
    },
    {
      title: "Classes, groups and discussion",
      tasks: [
        {
          id: "check-in",
          topic: "classes",
          title: "Check in to a class",
          steps: [
            "Open the course and its **Classes** tab, and choose **Check in** beside the class.",
            "Type the code shown on the screen in the room in **Code on the screen**, and choose **Check in**.",
          ],
          note: "Check-in opens 15 minutes before the class and closes when it ends. It needs signal. **Your attendance** shows your record.",
          words: "attendance register present",
        },
        {
          id: "groups",
          topic: "groups",
          title: "Join or leave a group",
          steps: ["Open the course and its **Groups** tab. Choose **Join** under **Groups you can join**, or **Leave** under **My groups**."],
          note: "You may hold one group in each set.",
        },
        {
          id: "forum",
          topic: "forums",
          title: "Take part in a discussion",
          steps: [
            "Open the course's **Discussion** tab (or search for **Discussion**) and choose a forum.",
            "Choose **Start a discussion**, give a **Title** and **Your post**, and choose **Post**. Or open a discussion and choose **Reply**.",
            "You can **Change** or **Remove** your own post for 30 minutes. **Report** a post that breaks the rules.",
          ],
          note: "Posting needs signal. In a question and answer forum you see other answers after you post yours.",
          words: "forum post reply",
        },
      ],
    },
    {
      title: "Practicals and the logbook",
      tasks: [
        {
          id: "logbook",
          topic: "logbook",
          title: "Write a logbook entry",
          steps: [
            "Open the course and its **Logbook** tab, and choose **Add an entry**.",
            "Fill in **Date of the work**, **Hours**, **Where**, **Which unit** and **What you did**, with any **Notes**.",
            "Add photos with **Take a photo** or **Choose photos**, and **Add my location** if asked.",
            "Choose **Save entry**. It waits for your supervisor to sign it off.",
          ],
          note: `Hours from a quarter of an hour to 24; up to 10 photos. ${OFFLINE} Photos are sent after the entry.`,
          words: "logbook farm field hours",
        },
        {
          id: "logbook-returned",
          topic: "logbook",
          title: "Correct an entry handed back",
          steps: ["Open the entry marked returned, choose **Correct and send again**, make the change and choose **Send the correction**."],
          note: "A correction needs signal. An entry that has been signed off cannot be changed.",
        },
        {
          id: "practicals",
          topic: "practicals",
          title: "See your practical results and portfolio",
          steps: [
            "Open the course and its **Practicals** tab. **My practicals** shows each task and **What the assessor looks for**.",
            "**My competency** shows each unit's result.",
            "**Portfolio** lets you **Download this course (page to print)** or **Download every course (page to print)**.",
          ],
          words: "practical checklist competency portfolio",
        },
      ],
    },
  ],
};

// --- Teaching staff ---

const LECTURER: HelpRole = {
  id: "lecturer",
  title: "Lecturers and teaching assistants",
  who: "For everyone who teaches a course. Teaching assistants do the same, except sending coursework to the SRMS.",
  personas: ["lecturer"],
  sections: [
    { title: "Getting started", tasks: signIn(true) },
    {
      title: "Setting up your course",
      tasks: [
        {
          id: "find-courses",
          topic: "courses",
          title: "Find the courses you teach",
          steps: [
            "From Home choose **My courses**. Every course you teach is listed, drafts too.",
            "Home also shows work **Waiting to be marked**, courses with **Nothing new this week**, and students **Not seen in N days**.",
          ],
          note: "Courses appear once the Registry gives you the class in the SRMS.",
          words: "my courses teaching home",
        },
        {
          id: "course-setup",
          topic: "setup",
          title: "Start a course from a template or last year's course",
          steps: [
            "Open the course and choose **Course setup: template, copy from another course, dates and storage**.",
            "For an empty course, choose a **Template** under **Start from a template** and **Apply template**.",
            "Or, under **Copy from an earlier course**, choose the **Course to copy from**, tick **Move its dates**, give the **New start date**, and choose **Copy the course**.",
          ],
          words: "copy template rollover last year",
        },
        {
          id: "dates",
          topic: "setup",
          title: "Change or move the course's dates",
          steps: [
            "In **Course setup**, under **Dates**, change any date and choose **Save N changes**.",
            "To move them all, use **Move every date** with a number of **Days** or a **New start date**.",
          ],
          note: "Changes are saved all together or not at all.",
        },
        {
          id: "modules",
          topic: "content",
          title: "Arrange the weeks or topics",
          steps: [
            "On the **Content** tab, type a name under **New module** and choose **Add module**.",
            "Use **Move up** and **Move down**, or drag an item to a new place.",
            "Choose **When students see it** to show a module from a date, after an earlier item, or to some groups only, and **Save conditions**.",
          ],
          words: "module week topic order",
        },
        {
          id: "write-page",
          topic: "pages",
          title: "Write a page",
          steps: [
            "In the module, choose **Add a page**.",
            "Give a **Title** and write the page. The toolbar has headings, lists, links, pictures, maths and tables.",
            "Read the **Accessibility check** beside it and fix anything it says must be fixed.",
            "Choose **Save as draft**, or **Save and publish**. **See it as students do** shows the student's view.",
          ],
          note: "Every picture needs a description of what it shows, for students who cannot see it.",
          words: "page editor write text",
        },
        {
          id: "upload-file",
          topic: "content",
          title: "Put up a file or a link",
          steps: [
            "In the module, choose **Upload a file** (or **Add a link**).",
            "Give a **Title**, choose the file (a PDF, photograph, Word, Excel or PowerPoint file) or the **Web address**.",
            "Say **Whose material is this?** and give the **Source and credit**.",
            "Choose **Upload file** (or **Add link**). Choose **Change**, then **Publish**, when students may see it.",
          ],
          note: "Files are checked: one whose contents do not match its name is refused. Material brought across from a shared drive arrives as a draft marked **Not yet known** for its licence: check it before publishing.",
          words: "upload file pdf link licence copyright",
        },
        {
          id: "publish",
          topic: "content",
          title: "Publish the course or an item to students",
          steps: [
            "For one item, choose **Change**, then **Publish** (or **Unpublish**).",
            "For the whole course, choose **Publish to students** beside its title.",
          ],
          note: "A draft is not seen by students at all. The GSA course-site standard says what every course has by week 2.",
        },
        {
          id: "announcement",
          topic: "announcements",
          title: "Post an announcement",
          steps: ["Open the **Announcements** tab, give a **Title** and **Message**, and choose **Post and notify students**."],
        },
      ],
    },
    {
      title: "Assignments and marking",
      tasks: [
        {
          id: "set-assignment",
          topic: "assignments",
          title: "Set an assignment",
          steps: [
            "Open the **Assignments** tab and choose **New assignment**.",
            "Fill in **Title**, **Opens**, **Due**, **Maximum mark**, **Weight** and **Instructions**.",
            "Under **Handing in** choose the kinds of file and how many; under **Late work** whether late work is accepted and its **Late penalty**.",
            "Under **Marking** choose a **Rubric or marking guide**, anonymous marking or second marking if needed.",
            "Tick **Published to students** and choose **Create assignment**.",
          ],
          note: "Once work has been handed in, anonymous marking and groups cannot be changed.",
          words: "assignment coursework due date",
        },
        {
          id: "extension",
          topic: "assignments",
          title: "Give a student more time",
          steps: ["Open the assignment and choose **Extensions**. Choose who it is **For**, the **New due date** and the **Reason**, then **Grant the extension**."],
          note: "**Withdraw** takes it back.",
          words: "extension deadline",
        },
        {
          id: "mark",
          topic: "marking",
          title: "Mark and return work",
          steps: [
            "Open the assignment and choose **Mark** (or open it from To do).",
            "Read the work in the viewer. Give the **Mark out of N**, or choose a level for each rubric criterion.",
            "Write the **Feedback**. To return a file or spoken feedback, use **Feedback files and recordings**.",
            "Choose **Save draft**, or **Save and release** to send it to the student now.",
            "Choose **Next not marked** to go on.",
          ],
          note: "Marks stay drafts until released. Once coursework has been sent to the SRMS, a change goes through the SRMS correction process.",
          words: "mark grade feedback rubric",
        },
        {
          id: "release-all",
          topic: "marking",
          title: "Release every mark, download the work, or mark from a spreadsheet",
          steps: [
            "On the marking screen open **The whole class: release, download, marks from a spreadsheet**.",
            "**Release all marks** sends every saved mark to the students. **Download every hand-in (zip)** keeps a copy.",
            "For a spreadsheet: save it as CSV with the student number, mark and feedback, choose it under **Spreadsheet (CSV)**, **Check the file**, then **Apply N marks**. They are saved as drafts.",
          ],
          words: "csv spreadsheet download zip release",
        },
        {
          id: "second-marking",
          topic: "marking",
          title: "Second marking and moderation",
          steps: [
            "Under **Second marking**, give **Your second mark** (you cannot be the first marker) and choose **Save the second mark**.",
            "When the markers agree, record **The agreed mark**.",
            "For a sample, give the share to check and choose **Choose a sample**.",
          ],
        },
        {
          id: "rubrics",
          topic: "rubrics",
          title: "Make or copy a rubric",
          steps: [
            "On the **Assignments** tab choose **Rubrics and marking guides**.",
            "Choose **New rubric**, or **Copy from the GSA library** and **Copy to this course**.",
            "Add criteria and levels, then **Save the rubric**.",
          ],
          note: "A rubric already used for marking cannot be changed; copy it instead.",
        },
        {
          id: "gradebook",
          topic: "gradebook",
          title: "Use the gradebook and send coursework to the SRMS",
          steps: [
            "Open the **Gradebook** tab. Choose a student to see how their total is worked out.",
            "**Categories and weights** sets how the categories count; **Export to a spreadsheet** and **Print** give copies.",
            "When marking is finished, the lecturer chooses **Send coursework to the SRMS** and confirms.",
          ],
          note: "Marks accepted by the SRMS are locked in the LMS.",
          words: "gradebook totals srms export",
        },
      ],
    },
    {
      title: "Quizzes",
      tasks: [
        {
          id: "question-bank",
          topic: "quizzes",
          title: "Write or import questions",
          steps: [
            "Open the **Quizzes** tab, then **Question banks**. Choose **New bank** if the course has none.",
            "Choose **New question** and its type, write it and choose **Save question**.",
            "Or choose **Import** for a Moodle XML, GIFT or QTI 2.1 file (at most 5 MB).",
          ],
          words: "question bank import moodle gift",
        },
        {
          id: "set-quiz",
          topic: "quizzes",
          title: "Set a quiz",
          steps: [
            "On the **Quizzes** tab choose **New quiz**, give its title and **Create quiz**.",
            "In **Settings** set **Opens**, **Closes**, the time limit, **Attempts allowed**, the pass mark and what students see after an attempt; **Save settings**.",
            "In **Questions** choose **Add questions**, then chosen or random questions **From the bank**.",
            "Choose **Publish to students**.",
          ],
          words: "quiz test exam",
        },
        {
          id: "extra-time",
          topic: "quizzes",
          title: "Give a student extra time or attempts",
          steps: ["Open the quiz, then **Extra time**, **Give a student more**: the **Student**, **Extra minutes** or **Extra attempts**, and the reason; **Save**."],
        },
        {
          id: "quiz-marking",
          topic: "quizzes",
          title: "Mark written answers and release results",
          steps: [
            "Open the quiz, then **Marking**, and choose **Mark** beside each answer waiting.",
            "Give the **Mark out of N** and a **Comment for the student**, and **Save mark**.",
            "Choose **Release marked results**. **Results** and **Statistics** show how the class did.",
          ],
        },
      ],
    },
    {
      title: "Classes, groups, discussion and messages",
      tasks: [
        {
          id: "classes",
          topic: "classes",
          title: "Add a class and take the register",
          steps: [
            "Open the **Classes** tab, choose **Add a class**, fill in **Title**, **Starts**, **Ends** and **Room or place**, tick **Take attendance at this class**, and **Add class**.",
            "In the room, open the class and choose **Show the check-in code in the room**. Students check in with it.",
            "Open the register: mark each student **Present**, **Late**, **Excused** or **Absent**, or **Mark the rest present**, and **Save register**.",
            "Choose **Close register: no record means absent** when the class is over.",
          ],
          note: "The code changes each minute and each code works for two minutes. On a phone without signal the register as last opened is shown and your changes wait to send; closing it needs signal.",
          words: "attendance register check-in",
        },
        {
          id: "groups",
          topic: "groups",
          title: "Make groups",
          steps: [
            "Open the **Groups** tab and choose **New group**, or **Share students at random** with a number of groups or a size.",
            "Choose **Sign-up** to let students join or leave themselves, with a **Largest size** and when **Sign-up closes**.",
          ],
        },
        {
          id: "forums",
          topic: "forums",
          title: "Run a forum",
          steps: [
            "On the **Discussion** tab choose **New forum** and its kind; a graded discussion has a participation mark and weight.",
            "Deal with **Reports waiting for review**: **Remove the post** or **Keep the post**. In a discussion you can **Pin to the top** or **Lock** it.",
            "In a graded forum give each **Participation marks** and **Release marks to students**.",
          ],
        },
        {
          id: "message-class",
          topic: "messages",
          title: "Send a notice to a group or the whole course",
          steps: ["In **Messages**, choose **New message**, then under **Send to** choose **A group, as a notice** or **The whole course, as a notice**."],
          note: "Students read a notice but do not reply in it; they write to you instead.",
        },
      ],
    },
    {
      title: "Practicals in the field",
      tasks: [
        {
          id: "practical-task",
          topic: "practicals",
          title: "Set a practical task and its checklist",
          steps: [
            "Open the **Practicals** tab, then **New practical task**: **Title**, **Where it is done**, **Location**, attempts, **Opens**, **Closes**, **Instructions**; **Create task**.",
            "Choose **Add a criterion** for each thing the assessor looks for, and mark any that are critical.",
            "Choose **Publish**. Name any farm or unit staff who assess under **Named assessors**.",
          ],
          words: "practical checklist field task",
        },
        {
          id: "observe",
          topic: "practicals",
          title: "Mark a student in the field",
          steps: [
            "Before you go, open the task once with signal so the phone keeps a copy of it and of the class list.",
            "Choose **Mark in the field**, then the student under **Who are you observing?**",
            "For each criterion choose **Met** or **Not met** (or a score) and add a comment if needed; add photos and **Add my location**.",
            "Choose **Save observation**, then **Next student**.",
            "Back in the office choose **Release all** to send the results to the students.",
          ],
          note: `${OFFLINE} The time you observed is kept from the phone. Photos are sent after the record.`,
          words: "observe field farm offline signal",
        },
        {
          id: "competency",
          topic: "practicals",
          title: "Record a competency decision",
          steps: [
            "Open **Practicals**, then **Competency**, and choose **Record for** the student.",
            "Read what the evidence suggests, then choose **Competent**, **Not yet competent** or **Not assessed**, add **Comments**, and record it.",
          ],
          note: "The LMS suggests; you decide.",
        },
        {
          id: "sign-logbook",
          topic: "logbook",
          title: "Sign off logbook entries",
          steps: [
            "Open the **Logbook** tab. **Waiting for sign-off** lists the entries.",
            "Choose **Sign off**, or **Return with a comment** saying **What needs correcting**.",
          ],
        },
      ],
    },
  ],
};

// --- Heads of department ---

const HEAD: HelpRole = {
  id: "head-of-department",
  title: "Heads of department",
  who: "There is no separate head of department role in the LMS: a head of department teaches as a lecturer, approves their staff's requests to join staff-development courses, and keeps the department's question bank. These are the tasks beyond a lecturer's.",
  personas: [],
  sections: [
    { title: "Getting started", tasks: signIn(true) },
    {
      title: "Your department",
      tasks: [
        {
          id: "approve",
          topic: "learning",
          title: "Approve or turn down a request to join a staff-development course",
          steps: [
            "You are told by a notification, and the request waits in **To do**.",
            "Search for **Staff development** and open **Approvals**.",
            "Under **Waiting for your decision**, read why the person wants to take it, then choose **Approve**, or write a **Comment** and choose **Turn down**.",
          ],
          note: "A comment is needed to turn a request down.",
          words: "approve approval request staff development training",
        },
        {
          id: "stand-in",
          topic: "learning",
          title: "Name a stand-in while you are away",
          steps: [
            "In **Staff development**, **Approvals**, choose **Name a stand-in**.",
            "Find the colleague by name or employee number, choose them, give the **From** and **To** dates and **Why**, and choose **Name the stand-in**.",
            "Choose **End** to stop it early.",
          ],
          words: "leave delegate deputy",
        },
        {
          id: "department-bank",
          topic: "quizzes",
          title: "Keep a question bank for the department",
          steps: [
            "In any course you teach, open **Quizzes**, then **Question banks**, then **New bank**.",
            "Under **Belongs to** choose **A department, shared with its teaching staff**, give the **Department code** and choose **Make the bank**.",
            "Every lecturer of the department can then use its questions in their quizzes.",
          ],
          words: "department shared questions",
        },
        {
          id: "standard",
          topic: "courses",
          title: "Check your department's courses against the GSA standard",
          steps: [
            "With the department champion, open each course by week 2 of term.",
            "Check it has its outline, weekly content and assessments with dates, as the GSA course-site standard lists.",
            "Ask the lecturer, or the course administrator, to fill any gap.",
          ],
          note: "Teaching staff see only the courses they teach. To see every course of the department, ask a course administrator.",
        },
      ],
    },
  ],
};

// --- Course administrators ---

const COURSE_ADMIN: HelpRole = {
  id: "course-administrator",
  title: "Course administrators",
  who: "For the course administrators who look after the course sites of a campus or of every campus.",
  personas: ["course_admin"],
  sections: [
    { title: "Getting started", tasks: signIn(true) },
    {
      title: "Course sites",
      tasks: [
        {
          id: "sites",
          topic: "courses",
          title: "Find a course site and see how it stands",
          steps: [
            "Home shows the number of **Course sites**, **Students**, those **Without a lecturer**, and **Takedown requests**.",
            "Choose **Course sites** (or **My courses**). With more than one campus, the campus switch at the top shows one campus or **All campuses**.",
            "Open a course to see it as its lecturers do.",
          ],
        },
        {
          id: "templates",
          topic: "course-admin",
          title: "Keep the course templates",
          steps: [
            "Open **Admin**, then **Course templates**, then **New template**.",
            "Give its **Name** and **What it is for**, add modules and pages, and **Save template**.",
            "Tick **The standard template, given to every new course** for the one every new course starts from.",
          ],
          words: "template standard structure",
        },
        {
          id: "import",
          topic: "course-admin",
          title: "Bring existing material into a course",
          steps: [
            "Collect the lecturer's material as one folder per week or topic, as the migration guide says.",
            "Ask the administrator to run the import for the course. Every file comes in as a draft marked **Not yet known** for its licence; files that fail the checks are listed with the reason.",
            "Go through the drafts with the lecturer: set **Whose material is this?** and publish.",
          ],
          words: "migration import shared drive google classroom",
        },
        {
          id: "storage",
          topic: "course-admin",
          title: "Change a course's storage allowance",
          steps: ["Open **Admin**, then **Storage allowances**. **Find a course**, give the **Allowance in MB** (empty for the standard), and **Save allowance**."],
        },
        {
          id: "takedowns",
          topic: "course-admin",
          title: "Decide a takedown request",
          steps: [
            "Open **Admin**, then **Takedown requests**. **Waiting** lists them.",
            "Read the reason, add a **Note on the decision**, and choose **Withdraw the item** or **Restore the item**.",
          ],
          note: "While a request waits, the item is hidden from students.",
          words: "copyright complaint remove",
        },
        {
          id: "rubric-library",
          topic: "rubrics",
          title: "Keep the GSA rubric library",
          steps: ["Search for **Rubric library**, choose **New rubric** or **Change**, and save it. Every course may copy from it."],
        },
        {
          id: "accommodations",
          topic: "accommodations",
          title: "Record an accommodation for a student",
          steps: [
            "Search for **Accommodations** and choose **Add an accommodation**.",
            "Find the **Student**, give **More time in quizzes (%)**, **More days for each assignment** or **Another format needed**, the **Reason**, and **Save**.",
          ],
          note: "The reason is seen by course administrators only, never by lecturers.",
          words: "disability extra time accommodation",
        },
      ],
    },
    {
      title: "Help, corrections and reviews",
      tasks: [
        {
          id: "help-requests",
          topic: "help",
          title: "Answer help requests",
          steps: [
            "New requests come as notifications and wait in **To do**. Or open **Help**, then **Help requests**.",
            "Read the question; **Open the page they were on** shows what they were looking at.",
            "Write the answer and choose **Send the answer**. The person is told by a notification.",
          ],
          note: "Aim to answer within two working days. You cannot answer your own request.",
          words: "support help desk questions",
        },
        {
          id: "corrections",
          topic: "admin",
          title: "Answer a correction request",
          steps: [
            "Open **Admin**, then **Correction requests**, or the request from **To do**.",
            "Choose **Corrected**, or **Not changed** with the answer saying why.",
          ],
          note: "Answer within 30 days. Nobody answers a request about themselves.",
        },
        {
          id: "access-review",
          topic: "admin",
          title: "Do the access review each term",
          steps: [
            "Open **Admin**, then **Access review**. Check every role holder and everyone teaching still needs their access.",
            "Ask the administrator to remove what is no longer needed, then choose **Sign off the review**.",
          ],
        },
        {
          id: "integration-runs",
          topic: "admin",
          title: "Check that class lists and staff come across",
          steps: ["Open **Admin**, then **Integration runs**, and look for runs with failures."],
        },
      ],
    },
    {
      title: "Staff development",
      tasks: [
        {
          id: "required-training",
          topic: "learning",
          title: "Require a course of some staff",
          steps: [
            "Search for **Staff development** and open **Required training**, then **Require a course**.",
            "Choose the **Course**, narrow it by campus, unit or post, set the days to complete it and how often it is taken again, and **Require it**.",
          ],
        },
        {
          id: "certificates",
          topic: "learning",
          title: "Keep certificate templates, and withdraw a certificate",
          steps: [
            "In **Staff development**, **Certificate templates** holds the wording; a change is saved as a new version.",
            "In **Certificates issued**, choose **Withdraw** and say why for one issued in error.",
          ],
        },
        {
          id: "framework",
          topic: "practicals",
          title: "Import a competency framework",
          steps: ["In a course's **Practicals** tab, **Competency**, use **Import a framework**: its **Code**, **Version**, **Title**, publisher and the CSV file, then **Import**."],
        },
      ],
    },
  ],
};

// --- Administrators ---

const ADMIN: HelpRole = {
  id: "administrator",
  title: "Administrators",
  who: "For the system administrators. You can also do everything on the course administrators' page.",
  personas: ["admin"],
  sections: [
    { title: "Getting started", tasks: signIn(true) },
    {
      title: "Accounts",
      tasks: [
        {
          id: "invite",
          topic: "admin",
          title: "Open accounts for new students and staff",
          steps: [
            "Open **Admin**, then **People to invite**. Choose the **Campus** and **Term code**, and **See who would be invited**.",
            "Choose **Send N invitations**. Each person gets an email with a link to choose a password.",
          ],
          note: "New students are put on the orientation course when they first sign in.",
          words: "accounts invitation new students",
        },
      ],
    },
    {
      title: "Records and privacy",
      tasks: [
        {
          id: "audit-log",
          topic: "admin",
          title: "Search the audit log and check it is intact",
          steps: [
            "Open **Admin**, then **Audit log**.",
            "Choose **Check the chain now** to confirm nothing has been changed or removed.",
            "Under **Entries** filter by what was done, who did it or about whom, and **Show the entries**; **Export to a spreadsheet (CSV)** keeps a copy.",
          ],
          words: "audit log history who changed",
        },
        {
          id: "privacy-notice",
          topic: "admin",
          title: "Publish a new version of the privacy notice",
          steps: ["Open **Admin**, then **Privacy notice**, **Write a new version**, **Save as a draft**, and when GSA has approved it **Publish**."],
          note: "Everyone reads the new version at their next sign-in.",
        },
        {
          id: "retention",
          topic: "admin",
          title: "Run retention and disposal",
          steps: [
            "Open **Admin**, then **Retention and disposal**. Confirm each period as GSA approves it.",
            "Choose **Find what is due**. Choose **Keep** (with why) for anything that must be kept.",
            "A different person chooses **Approve the disposal**.",
          ],
        },
        {
          id: "breach",
          topic: "admin",
          title: "Record a personal data breach",
          steps: [
            "Open **Admin**, then **Breach register**, **Record a breach**, fill in what happened, whose data and the risk, and **Record the breach**.",
            "As things happen, choose **Contained now**, **Commissioner told now** and **People told now**, then **Close**.",
          ],
          note: "Recording one alerts the administrators and the data protection officer.",
        },
        {
          id: "orientation-setting",
          topic: "admin",
          title: "Set up the student orientation course",
          steps: [
            "Once, on the server, run the command seed_orientation. It makes the course “Getting started with the GSA LMS”.",
            "New students are put on it at their first sign-in. Set ORIENTATION_AUTO_ENROL to 0 to stop that.",
          ],
          note: "Running it again adds only what is missing; it never changes what a course administrator has edited.",
        },
      ],
    },
  ],
};

// --- Auditors and the data protection officer ---

const OFFICE: HelpRole = {
  id: "auditor",
  title: "Auditors and the data protection officer",
  who: "For the auditor (who reads, and changes nothing) and GSA's data protection officer.",
  personas: ["office"],
  sections: [
    { title: "Getting started", tasks: signIn(true) },
    {
      title: "Reading the records",
      tasks: [
        {
          id: "open-admin",
          topic: "admin",
          title: "Open the Admin pages",
          steps: ["Search for **Admin** and open it. You see only the parts that are yours."],
        },
        {
          id: "audit-log",
          topic: "admin",
          title: "Search the audit log and check it is intact",
          steps: [
            "Open **Admin**, then **Audit log**, and choose **Check the chain now**.",
            "Filter **Entries** and choose **Show the entries**; **Export to a spreadsheet (CSV)** keeps a copy.",
          ],
          words: "audit log",
        },
        {
          id: "review",
          topic: "admin",
          title: "Read the access review, integration runs and certificates",
          steps: ["In **Admin**, open **Access review** or **Integration runs**. In **Staff development**, open **Certificates issued**."],
          note: "The auditor reads only; nothing can be changed from these pages.",
        },
      ],
    },
    {
      title: "Data protection officer",
      tasks: [
        {
          id: "dpo-notice",
          topic: "admin",
          title: "Publish the privacy notice",
          steps: ["Open **Admin**, then **Privacy notice**, **Write a new version**, **Save as a draft**, and **Publish**."],
        },
        {
          id: "dpo-retention",
          topic: "admin",
          title: "Confirm retention periods and approve disposals",
          steps: [
            "Open **Admin**, then **Retention and disposal**. Change a period's **Months**, **Save**, and **Confirm** it.",
            "Approve a disposal run that someone else proposed, or **Cancel the run**.",
          ],
        },
        {
          id: "dpo-breach",
          topic: "admin",
          title: "Keep the breach register",
          steps: ["Open **Admin**, then **Breach register**, and record or progress a breach as it is handled."],
        },
        {
          id: "dpo-corrections",
          topic: "admin",
          title: "Follow correction requests",
          steps: ["Open **Admin**, then **Correction requests**. A course administrator answers them; you can see each one and its answer."],
        },
      ],
    },
  ],
};

export const HELP_ROLES: readonly HelpRole[] = [STUDENT, LECTURER, HEAD, COURSE_ADMIN, ADMIN, OFFICE];

/** The reader's own help page: the one for their Home, students' when nothing fits. */
export function ownRole(me: Me): HelpRole {
  const persona = me.persona ?? (me.person_kind === "student" ? "student" : "lecturer");
  return HELP_ROLES.find((role) => role.personas.includes(persona)) ?? STUDENT;
}

export const roleById = (id: string) => HELP_ROLES.find((role) => role.id === id);

/**
 * The first task on a topic in the reader's own page; for staff, then in the lecturers' page (administrators
 * open course sites too). Null when neither has it: the reader's own page opens at its top.
 */
export function taskForTopic(me: Me, topic: string): { role: HelpRole; task: HelpTask } | null {
  const own = ownRole(me);
  const pages = own === STUDENT ? [own] : [own, LECTURER];
  for (const role of pages) {
    const task = role.sections.flatMap((s) => s.tasks).find((t) => t.topic === topic);
    if (task) return { role, task };
  }
  return null;
}

export interface HelpHit {
  key: string;
  title: string;
  sub: string;
  to: string;
}

/** Search the reader's own help page (and, for teaching staff, the heads of department's) for a few words. */
export function searchHelp(me: Me, words: string, limit = 6): HelpHit[] {
  const own = ownRole(me);
  return search(own === LECTURER ? [own, HEAD] : [own], words, limit);
}

/** Search every help page, for the Help page's own search field. */
export const searchAll = (words: string, limit = 12) => search(HELP_ROLES, words, limit);

function search(pages: readonly HelpRole[], words: string, limit: number): HelpHit[] {
  const terms = words.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];
  const hits: HelpHit[] = [];
  for (const role of pages)
    for (const task of role.sections.flatMap((s) => s.tasks)) {
      const text = `${task.title} ${task.words ?? ""} ${task.steps.join(" ")}`.toLowerCase();
      if (terms.every((term) => text.includes(term)))
        hits.push({ key: `help-${role.id}-${task.id}`, title: task.title, sub: `Help for ${role.title.toLowerCase()}`, to: `/help/${role.id}/${task.id}` });
    }
  return hits.slice(0, limit);
}
