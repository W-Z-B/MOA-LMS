# AI assistance

Checklist items 6.11 and 6.12, within decision D5 ([ADR 0007](adr/0007-ai-assistance.md)). Code:
`api/assist/`. The privacy position is in the impact assessment, section 7b (`docs/privacy/dpia.md`).

## Off until GSA switches it on

| Setting | Default | Meaning |
|---|---|---|
| `AI_ENABLED` | `False` | Nothing below works, and no screen shows it, until this is on |
| `AI_OLLAMA_URL` | empty | The address of GSA's own Ollama server, such as `http://ollama.gsa.internal:11434` |
| `AI_MODEL` | empty | The model for text, such as `llama3.1:8b` |
| `AI_VISION_MODEL` | empty | A model that reads pictures, for alternative text, such as `llava:7b`; empty hides that |
| `AI_TIMEOUT_SECONDS` | `60` | How long to wait for the model |
| `AI_HELPER_OFF_DURING_ASSIGNMENTS` | `True` | The study helper is off while an assignment is open to the student, as for quizzes |

Then each course has two switches of its own, **drafts** and **study helper**, both off until the course's
teaching staff turn them on (the course's **AI help** tab).

The LMS speaks only Ollama's HTTP API (`POST /api/generate`; Ollama is MIT licensed and runs open models
on GSA's own server). **No outside AI service is implemented.** The provider interface
(`assist.providers.Provider`) would take another implementation, but using a service outside GSA would send
data out of Guyana and needs a new decision and its own impact assessment first.

## Drafts for lecturers (6.11)

- **Questions** from one of the lecturer's own pages, or Word or PowerPoint files: multiple-choice drafts,
  each checked against the question rules so it can be saved; the lecturer edits each one and saves it into a
  question bank of the course.
- **Rubric wording**: the lecturer names the criteria and the number of levels; the model words each level.
  The lecturer edits it and saves it as a rubric of the course.
- **Alternative text** for a picture put up on the course, suggested in the page editor's picture dialog.

A draft is only ever shown back to the lecturer. Nothing is saved until the lecturer saves it through the
usual form, and that save is then recorded in the audit log as **"Saved from an AI draft"**
(`ai_draft_saved`, naming the draft); the draft itself is recorded as `ai_drafted`.

## The study helper (6.12)

- Answers only from the course's own **published pages that the student can see** (release conditions
  apply). The pages are found with PostgreSQL's built-in full-text search; no extension is needed.
- When no page matches, it says so **without asking the model**. The model is told to answer only from the
  numbered passages and to say when they do not answer; that too is shown as "not in the material".
- Every answer lists its **sources**, each a link to the page.
- It is **switched off** while the student has a quiz attempt in progress, a quiz open to them (published,
  not practice, open now, attempts left), or an assignment open to them (published, open, not yet handed
  in, before their due date with any extension). The API refuses (`assessment_open`) and the screen hides it.
- **The prompt carries only the question and the course's material**: never the student's name, number,
  marks or anything else about them.
- **Nothing of the conversation is kept**: only when a question was asked, by whom, whether it was answered
  and which pages were used, removed after 1 year by the nightly retention purge (rule `ai-exchanges`, as
  the activity logs). Questions never go in the audit log, which is never purged.

## Addresses

| Address | Who | What |
|---|---|---|
| `GET /api/v1/sites/<id>/ai/` | Members | What is on, and whether the helper may be used now, with the reason |
| `PATCH /api/v1/sites/<id>/ai/` | Teaching staff | Switch drafts or the helper on or off for the course |
| `POST /api/v1/sites/<id>/ai/drafts/questions/` | Teaching staff | `{item, count}` |
| `POST /api/v1/sites/<id>/ai/drafts/rubric/` | Teaching staff | `{title, task, criteria, levels}` |
| `POST /api/v1/sites/<id>/ai/drafts/alt-text/` | Teaching staff | `{item}` |
| `POST /api/v1/ai/drafts/<draft>/saved/` | The lecturer who asked | `{record: question, rubric or content, id}` |
| `POST /api/v1/sites/<id>/ai/ask/` | Members | `{question}`; answer, sources, or a refusal |

Each person may make at most 30 requests a minute to the model.
