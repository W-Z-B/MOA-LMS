import { useState, type FormEvent } from "react";
import { errorMessage, post } from "../../api/client";
import type { ContentPackage } from "../../api/types-packages";
import type { StorageSummary } from "../../api/types-content";
import { LicenceFields } from "./LicenceFields";
import { NO_LICENCE, licenceFields, type LicenceValue } from "./licence";

interface Props {
  moduleId: number;
  onSaved: (saved: ContentPackage & { storage: StorageSummary }) => void;
  onCancel: () => void;
}

/**
 * Put a SCORM package or an H5P file up as an item of a module (items 5.12, 5.13). H5P exercises are not
 * written in the LMS: the form says where to make them. The package is checked on the server; what is wrong
 * with it comes back in plain words.
 */
export default function PackageForm({ moduleId, onSaved, onCancel }: Props) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [licence, setLicence] = useState<LicenceValue>(NO_LICENCE);
  const [weight, setWeight] = useState("0");
  const [attempts, setAttempts] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const id = `package-${moduleId}`;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setSaving(true);
    setError(null);
    const form = new FormData();
    const fields = { module: moduleId, title, weight, max_attempts: attempts, ...licenceFields(licence) };
    Object.entries(fields).forEach(([key, value]) => form.set(key, String(value)));
    form.set("file", file);
    try {
      onSaved(await post<ContentPackage & { storage: StorageSummary }>("/packages/", form));
    } catch (err) {
      setError(errorMessage(err, "Could not put the package up."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save} aria-label="Add a SCORM or H5P package">
      <p className="muted small">
        A SCORM 1.2 or 2004 package (.zip) or an H5P file (.h5p). H5P exercises are not written in the LMS: make them in the free
        H5P editor or the Lumi desktop app, save them with their libraries, and put the file up here.
      </p>
      <label>
        Package
        <input id={`${id}-file`} type="file" accept=".zip,.h5p" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-required="true" />
      </label>
      <label>
        Title (the package's own when left empty)
        <input id={`${id}-title`} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} />
      </label>
      <LicenceFields id={id} value={licence} onChange={setLicence} />
      <div className="form-row">
        <label>
          Weight in coursework (0: does not count)
          <input id={`${id}-weight`} type="number" inputMode="decimal" min="0" step="0.5" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </label>
        <label>
          Attempts allowed (0: no limit)
          <input id={`${id}-attempts`} type="number" inputMode="numeric" min="0" max="100" value={attempts} onChange={(e) => setAttempts(e.target.value)} />
        </label>
      </div>
      {Number(weight) > 0 && (
        <p className="muted small">
          Scores come from the learner's own browser, so a weighted package suits practice and low-stakes work.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={saving || !file}>
          {saving ? "Checking the package…" : "Put the package up"}
        </button>
      </div>
    </form>
  );
}
