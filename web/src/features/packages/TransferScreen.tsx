import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { SiteContents } from "../../api/types";
import type { ImportReport } from "../../api/types-packages";
import { useCrumb } from "../../app/frame";
import { Said, Section } from "../admin/kit";
import "./packages.css";

/**
 * Moving a course's content in and out (item 6.08): download it as an IMS Common Cartridge, or bring in a
 * cartridge or a Moodle course backup. What comes in is added as drafts after the course's own modules, and
 * the report says what was brought in and what was not, and why.
 */
export default function TransferScreen({ siteId }: { siteId: number }) {
  const [site, setSite] = useState<SiteContents["site"] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useCrumb(site?.title);

  useEffect(() => {
    get<SiteContents>(`/sites/${siteId}/contents/`)
      .then((contents) => setSite(contents.site))
      .catch((err) => setError(errorMessage(err, "Could not open this course.")));
  }, [siteId]);

  async function bring(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    const form = new FormData();
    form.set("file", file);
    try {
      setReport(await post<ImportReport>(`/sites/${siteId}/import-content/`, form));
    } catch (err) {
      setError(errorMessage(err, "Could not import the file."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="transfer-view">
      <p className="back-link">
        <a href={`#/sites/${siteId}`}>Back to {site?.title ?? "the course"}</a>
      </p>
      <div className="page-head">
        <h1>Import and export content</h1>
      </div>
      <Section
        title="Export"
        intro="The course's modules, pages, files, links and packages, its assignments as pages, and quiz questions that QTI can carry, as an IMS Common Cartridge for another learning system. Never people or marks."
      >
        <div className="actions">
          <a className="button" href={`/api/v1/sites/${siteId}/export-cartridge/`}>
            Download as a Common Cartridge (.imscc)
          </a>
        </div>
      </Section>
      <Section
        title="Import"
        intro="A Common Cartridge (.imscc), or a Moodle course backup (.mbz) for its content: sections, pages, labels, links, files and quiz questions. Everything comes in as a draft; say whose material each file is before publishing it."
      >
        <form className="stack" onSubmit={bring}>
          <label>
            File to import
            <input type="file" accept=".imscc,.zip,.mbz" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-required="true" />
          </label>
          <Said error={error} />
          <div className="actions">
            <button type="submit" disabled={busy || !file}>
              {busy ? "Importing…" : "Import into this course"}
            </button>
          </div>
        </form>
        {report && <Report report={report} siteId={siteId} />}
      </Section>
    </div>
  );
}

function Report({ report, siteId }: { report: ImportReport; siteId: number }) {
  const from = report.format === "moodle_backup" ? "the Moodle backup" : "the cartridge";
  return (
    <div className="stack" aria-label="What was imported">
      <p role="status" className="notice good">
        From {from}: {report.modules} modules, {report.items} items and {report.questions} questions, all as drafts.{" "}
        <a href={`#/sites/${siteId}`}>Open the course</a>
      </p>
      {report.warnings.length > 0 && (
        <>
          <h3>To check</h3>
          <ul className="report-list">
            {report.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </>
      )}
      {report.skipped.length > 0 && (
        <>
          <h3>Not imported ({report.skipped.length})</h3>
          <ul className="report-list">
            {report.skipped.map((s, index) => (
              <li key={`${s.title}-${index}`}>
                <span className="strong">{s.title}</span>: {s.reason}
              </li>
            ))}
          </ul>
        </>
      )}
      {report.imported.length > 0 && (
        <details>
          <summary>Imported ({report.imported.length})</summary>
          <ul className="report-list">
            {report.imported.map((i, index) => (
              <li key={`${i.title}-${index}`}>
                {i.module}: {i.title}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
