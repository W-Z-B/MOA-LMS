import { useState, type FormEvent } from "react";
import { errorMessage, patch, post } from "../../api/client";
import type { Licence } from "../../api/types";
import type { Item } from "../../api/types-content";

/** A lecture video (item 4.06) is put up once, at POST /videos/, and prepared by the server. */
type Kind = "file" | "link" | "video";

const LICENCES: { value: Licence; label: string }[] = [
  { value: "gsa_own", label: "GSA's own material" },
  { value: "open_licence", label: "Under an open licence" },
  { value: "fair_dealing", label: "Used under fair dealing (research or private study)" },
  { value: "permission_held", label: "Used with the owner's permission" },
];

const OPEN_LICENCES = [
  { value: "cc_by", label: "CC BY" },
  { value: "cc_by_sa", label: "CC BY-SA" },
  { value: "cc_by_nc", label: "CC BY-NC" },
  { value: "cc0", label: "CC0" },
  { value: "other", label: "Another open licence" },
];

interface Props {
  moduleId: number;
  kind: Kind;
  /** The file or link being changed; a new one is put up when absent. */
  item?: Item;
  onSaved: (saved: Item) => void;
  onCancel: () => void;
}

/**
 * A file or a link on the course, with whose material it is and where it comes from (item 2.20): GSA's own,
 * under an open licence (which one), used under fair dealing or with permission, with the source and credit
 * for anything that is not GSA's own.
 */
export function ItemForm({ moduleId, kind, item, onSaved, onCancel }: Props) {
  const [title, setTitle] = useState(item?.title ?? "");
  const [url, setUrl] = useState(item?.url ?? "");
  const [file, setFile] = useState<File | null>(null);
  // For a file or a link the lecturer must say whose it is: no default.
  const [licence, setLicence] = useState<Licence | "">(item?.licence && item.licence !== "unknown" ? item.licence : "");
  const [openLicence, setOpenLicence] = useState(item?.open_licence ?? "");
  const [source, setSource] = useState(item?.source ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const id = item ? `item-${item.id}` : `new-${kind}-${moduleId}`;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (kind === "video" && !item && !file) {
      setError("Choose the video to put up.");
      return;
    }
    setSaving(true);
    setError(null);
    const fields = {
      title,
      licence,
      open_licence: licence === "open_licence" ? openLicence : "",
      source: licence === "gsa_own" ? "" : source,
    };
    try {
      let saved: Item;
      if (kind === "video" && !item) {
        const form = new FormData();
        Object.entries({ ...fields, module: moduleId }).forEach(([key, value]) => form.set(key, String(value)));
        if (file) form.set("file", file);
        saved = await post<Item>("/videos/", form);
      } else if (kind === "file" && (file || !item)) {
        const form = new FormData();
        Object.entries(item ? fields : { ...fields, module: moduleId, kind }).forEach(([key, value]) => form.set(key, String(value)));
        if (file) form.set("file", file);
        saved = item ? await patch<Item>(`/content/${item.id}/`, form) : await post<Item>("/content/", form);
      } else if (kind === "link") {
        saved = item
          ? await patch<Item>(`/content/${item.id}/`, { ...fields, url })
          : await post<Item>("/content/", { ...fields, module: moduleId, kind, url });
      } else {
        saved = await patch<Item>(`/content/${item!.id}/`, fields);
      }
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, kind === "link" ? "Could not save the link." : kind === "video" ? "Could not put the video up." : "Could not save the file."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save}>
      <label>
        Title
        <input id={`${id}-title`} value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      {kind === "file" && (
        <label>
          {item ? `Replace the file (now ${item.filename})` : "File (PDF, photograph, Word, Excel or PowerPoint)"}
          <input
            id={`${id}-file`}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,.docx,.xlsx,.pptx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required={!item}
          />
        </label>
      )}
      {kind === "video" && !item && (
        <label>
          Video (MP4, MOV or WebM, put up once: the server makes a low, a standard and a sound-only copy)
          <input id={`${id}-file`} type="file" accept="video/*,.mp4,.m4v,.mov,.webm,.mkv,.3gp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      )}
      {kind === "link" && (
        <label>
          Web address
          <input id={`${id}-url`} type="url" inputMode="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} required />
        </label>
      )}
      <label>
        Whose material is this?
        <select id={`${id}-licence`} value={licence} onChange={(e) => setLicence(e.target.value as Licence)} required>
          <option value="" disabled>
            Choose…
          </option>
          {LICENCES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      {licence === "open_licence" && (
        <label>
          Which open licence
          <select id={`${id}-open`} value={openLicence} onChange={(e) => setOpenLicence(e.target.value)} required>
            <option value="" disabled>
              Choose…
            </option>
            {OPEN_LICENCES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {licence !== "" && licence !== "gsa_own" && (
        <label>
          Source and credit
          <input id={`${id}-source`} value={source} placeholder="Author, title, where it comes from" onChange={(e) => setSource(e.target.value)} required />
        </label>
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
        <button type="submit" disabled={saving}>
          {saving ? (kind === "video" && !item ? "Putting it up…" : "Saving…") : item ? "Save changes" : kind === "file" ? "Upload file" : kind === "video" ? "Put the video up" : "Add link"}
        </button>
      </div>
    </form>
  );
}
