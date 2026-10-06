# Bringing existing teaching material into the LMS

**Version 1.0, 6 October 2026, draft for GSA's review.** For: course administrators, department champions and
the administrator who runs the import. Checklist item 7.14.

Lecturers' material for the first-term courses is today on shared drives, memory sticks, in Google Classroom,
in the Moodle e-platform, or on paper. This guide says how to bring it into each course site before term, so
that every pilot course meets the GSA course-site standard by week 2 (`docs/training/course-site-standard.md`).

Where GSA's material is kept today is one of the questions in the LMS information request (decision D9). Until
it is answered, this guide covers the four likely sources.

## 1. What comes across, and what does not

| Comes across | Does not |
|---|---|
| Handouts, slides, worksheets, readings and photographs, as files | Students' past work and marks (they stay where they are, or in the SRMS) |
| The order of the weeks or topics, as modules | Discussion posts and messages from another system |
| Quiz questions from Moodle (Moodle XML) or in GIFT or QTI 2.1, through the question bank's **Import** | Videos larger than the upload limit (see decision record 0015 on video) |

Files the LMS accepts are the same as for any upload: a PDF, a photograph (JPG, PNG, WebP or HEIC), or a Word,
Excel or PowerPoint file, each up to 50 MB (`UPLOAD_LIMIT_CONTENT_MB`), within the course's storage allowance
(2 GB unless a course administrator sets another). A file whose contents do not match its name, or a Word,
Excel or PowerPoint file with macros, is refused. Anything else (old `.doc` and `.ppt` files, ZIP files,
videos) must be saved again in an accepted form first: open it and use **Save as** PDF or the modern Word,
Excel or PowerPoint format.

## 2. Getting the material ready: one folder per module

For each course, make one folder named after the course code. Inside it, make one folder for each week or topic,
named so they sort in order, and put that week's files in it:

```
AGR101/
  Course outline.pdf                 (files here go into a module called "General material")
  01 Week 1 - Introduction/
    Seed and germination.pdf
    Germination photo.jpg
  02 Week 2 - Soils/
    Soil sampling.pptx
    Lab sheets/                      (a folder inside a week is kept in the title: "Lab sheets / Soil test")
      Soil test.pdf
```

- Name files as students should see them: the title comes from the file name without its ending, with
  underscores read as spaces ("Soil_sampling.pptx" becomes "Soil sampling").
- Leave out anything students must not see: answer sheets, marked work, other students' names.
- Leave out files you do not have the right to share (see section 4). If in doubt, leave it in: every file
  arrives as a draft, and nothing is shown to students until someone has checked it.

### From each source

| Source | How to make the folder |
|---|---|
| A shared drive or memory stick | Copy the course's folder and arrange it as above. |
| Google Classroom | In Google Drive, open the "Classroom" folder, which holds a folder per class with the files lecturers attached. Download the class folder (Drive makes a ZIP file), unzip it, and arrange it by week. Google Docs, Sheets and Slides are downloaded as Word, Excel and PowerPoint files. |
| The Moodle e-platform | Ask the Moodle administrator for a course backup, or download each resource from the course page. Export the question bank as Moodle XML and bring it in through **Question banks**, **Import**. |
| Paper | Scan each handout to PDF (a phone scanning app is enough), one file per handout, and put them in the week folders. Check each scan can be read on a phone. |

## 3. Running the import

The administrator runs the import on the server, with the folder copied there (for example to `/srv/import`).
First a trial that changes nothing:

```
python manage.py import_folder AGR101-2026-27-S1-MRP /srv/import/AGR101 --dry-run
```

It lists every file with what would happen to it, and ends with a line such as
`4 would be imported, 1 refused, 1 skipped.` Fix the refused files (the list says why each was refused), then
run it for real, keeping the report:

```
python manage.py import_folder AGR101-2026-27-S1-MRP /srv/import/AGR101 --report /srv/import/AGR101-report.csv
```

What it does:

- each week folder becomes a module of the course site, after any modules the course already has;
- each file becomes a file item in its module, **as a draft**, with its licence marked **Not yet known** and a
  note saying where it came from and to check whose material it is;
- each module and item made is recorded in the audit log;
- a file already imported from the same place is skipped, so the import can be run again after fixing refused
  files, or after it was interrupted;
- system files (`Thumbs.db`, `desktop.ini`, names beginning with a dot) are skipped.

The report (a CSV file that opens in Excel) has one row per file: the file, its module, what happened
(`imported`, `refused`, `skipped`) and why.

## 4. Checking and publishing

Nothing imported is seen by students until it is published. With the lecturer, for each item:

1. Open the course's **Content** tab. Imported items show the **Draft** pill.
2. Open the item with **Change**, then **Edit details**, and set **Whose material is this?**:
   **GSA's own material**, **Under an open licence** (and which one), **Used under fair dealing (research or
   private study)**, or **Used with the owner's permission**, with the **Source and credit**.
3. If the material cannot be used (a scanned textbook chapter beyond fair dealing, for example), remove it.
4. Choose **Publish** when the item is ready, or publish the module's items together once they are checked.

Then check the course against the course-site standard, on a phone as well as a computer.

## 5. Who does what, and when

| When | Who | What |
|---|---|---|
| Six weeks before term | Department champion with each lecturer | Collect the material into folders, by course |
| Four weeks before term | Administrator | Trial import (`--dry-run`) for each course; send the reports to the champions |
| Three weeks before term | Champions and lecturers | Fix refused files |
| Two weeks before term | Administrator | Import for real; keep the reports |
| Before week 1 | Lecturers, with the champion | Check licences, publish week 1 and 2, check on a phone |
| Week 2 | Champion | Check each course against the standard; report to the pilot lead |

## 6. If something goes wrong

- **"There is no course site with the code …"**: the course has not come across from the SRMS yet, or the code
  is mistyped. The code is on the course's page in the LMS.
- **"The file's contents do not match its name"**: open the file and save it again as a PDF, or in the modern
  Word, Excel or PowerPoint format.
- **"This course has used … of its … storage allowance"**: ask a course administrator for a larger allowance
  under **Admin**, **Storage allowances**, or leave out large files such as videos.
- An item went into the wrong module: move it with **Change**, **Move to module**.
