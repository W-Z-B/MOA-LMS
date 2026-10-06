# ADR 0021: How the similarity check compares work

**Status:** accepted, 6 October 2026, as the way to carry out [ADR 0006](0006-academic-integrity.md) (decision D4).
**Date:** 6 October 2026.

## Context

ADR 0006 decided that each submission is compared with other GSA submissions, past and present, on GSA's own
server, with the matching passages shown to teaching staff only (item 3.20). GSA hands in some thousands of
pieces of work a year, so the check must stay quick with tens of thousands of submissions held, and it must
show passages side by side, not only a score.

Two ways were weighed:

- **PostgreSQL trigram similarity (pg_trgm).** It scores how alike two whole strings are by their
  three-letter pieces. It is built for short strings such as names. Over essays almost every trigram is
  common, so the score says little; it cannot say which passages match; and a GIN index over whole essays is
  large and slow to update.
- **Fingerprints by winnowing** (Schleimer, Wilkerson and Aiken, 2003, the method of Stanford's MOSS). Each
  run of five words is hashed, and the smallest hash in every window of eight runs is kept. About a quarter
  of the hashes are kept, yet any shared passage of twelve words or more is guaranteed to leave a shared
  fingerprint. The kept hashes go in an ordinary table with a btree index on the hash.

## Decision

1. Winnowing, with K = 5 words and a window of W = 8 (`similarity.engine`). A new hand-in looks up its
   fingerprints in the index; the twenty documents that share the most are compared with it in full, run by
   run, to find every shared passage of eight words or more exactly.
2. The text is read from typed answers, PDFs (pypdf, BSD licence, pure Python) and Word and PowerPoint files
   (the standard library's zip and XML readers; any part that declares a document type or an entity is
   refused, so nothing is expanded). Photographs and scans are not read; the report says so.
3. Before comparing, passages in quotation marks are taken out, and runs of the assignment's own instructions
   are never counted.
4. One background job per hand-in (`similarity.tasks.check_attempt`), queued when the hand-in is saved.
   Teaching staff can run the check again from the report.
5. The match is kept for both sides, so an earlier piece of work's report shows a later copy of it.
6. The report is for the submission's teaching staff only. The other submission is named only to staff who
   also teach on its site; anyone else reads "Another GSA submission" and its year. The report always says
   that overlap is evidence for a person to judge, not a verdict.
7. Retention: the words compared, the fingerprints and the matches belong to the submission and are deleted
   with it. `SIMILARITY_CHECKS` (on by default) switches new checks off.

## Consequences

- Cost grows with the number of fingerprints, not the number of documents: a 3,000-word essay keeps about
  700, so 50,000 essays are some 35 million small rows, found through one index. Each check reads only its
  candidates in full.
- Reworded copying (paraphrase) is not found, nor is copying from outside GSA (ADR 0006 says so).
- The guidance for lecturers ([docs/guides/assessment-and-ai.md](../guides/assessment-and-ai.md)) explains
  how to read a report.
