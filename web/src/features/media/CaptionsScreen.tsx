import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage, get, post, remove } from "../../api/client";
import type { Item } from "../../api/types-content";
import { clock, type Cue, type Cues, type VideoInfo } from "../../api/types-media";
import { useCrumb } from "../../app/frame";
import "./media.css";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "pt", label: "Portuguese" },
  { value: "fr", label: "French" },
  { value: "nl", label: "Dutch" },
];

interface Props {
  siteId: number;
  itemId: number;
}

/**
 * Captions for a lecture video (item 4.06): put up a WebVTT file, or write and correct the captions here cue
 * by cue beside the video, and, where GSA's server is set up for it, have them written by speech recognition
 * on that server first. Teaching staff only; the server refuses anyone else.
 */
export default function CaptionsScreen({ siteId, itemId }: Props) {
  const [item, setItem] = useState<Item | null>(null);
  const [language, setLanguage] = useState("en");
  const [label, setLabel] = useState("English");
  const [cues, setCues] = useState<Cue[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const player = useRef<HTMLVideoElement>(null);
  useCrumb(item ? `Captions: ${item.title}` : null);
  const video: VideoInfo | null | undefined = item?.video;

  const loadItem = useCallback(
    () =>
      get<Item>(`/content/${itemId}/`)
        .then(setItem)
        .catch((err) => setError(errorMessage(err, "Could not open this video."))),
    [itemId],
  );
  useEffect(() => {
    void loadItem();
  }, [loadItem]);

  useEffect(() => {
    get<Cues>(`/videos/${itemId}/captions/${language}/cues/`)
      .then((found) => {
        setCues(found.cues);
        setLabel(found.label);
      })
      .catch(() => {
        setCues([]);
        setLabel(LANGUAGES.find((l) => l.value === language)?.label ?? language);
      });
  }, [itemId, language]);

  function change(index: number, part: Partial<Cue>) {
    setCues(cues.map((cue, i) => (i === index ? { ...cue, ...part } : cue)));
  }

  function addCue() {
    const at = Math.round((player.current?.currentTime ?? cues[cues.length - 1]?.end ?? 0) * 10) / 10;
    setCues([...cues, { start: at, end: Math.round((at + 3) * 10) / 10, text: "" }]);
  }

  async function act(action: () => Promise<unknown>, done: string, failed: string) {
    setError(null);
    setStatus(null);
    try {
      await action();
      setStatus(done);
      await loadItem();
    } catch (err) {
      setError(errorMessage(err, failed));
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    await act(
      async () => {
        const saved = await api<Cues>(`/videos/${itemId}/captions/${language}/cues/`, {
          method: "PUT",
          body: JSON.stringify({ label, cues }),
        });
        setCues(saved.cues);
      },
      `Saved the ${label} captions.`,
      "Could not save the captions.",
    );
  }

  async function putUp(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    form.set("language", language);
    form.set("label", label);
    await act(
      async () => {
        await post(`/videos/${itemId}/captions/`, form);
        const found = await get<Cues>(`/videos/${itemId}/captions/${language}/cues/`);
        setCues(found.cues);
      },
      `Put up ${file.name} as the ${label} captions.`,
      "Could not put the captions file up.",
    );
  }

  if (error && !item)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!item || !video) return <p className="loading">Opening the captions…</p>;
  const low = video.qualities.find((q) => q.quality === "low");
  const existing = video.captions.some((c) => c.language === language);

  return (
    <article className="captions-screen">
      <p className="back-link">
        <a href={`#/sites/${siteId}`}>Back to the course</a>
      </p>
      <h1>Captions: {item.title}</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>
      {low && (
        <video ref={player} className="video-player" controls playsInline preload="metadata" src={low.url} aria-label={item.title}>
          {video.captions.map((c) => (
            <track key={c.language} kind="captions" src={c.url} srcLang={c.language} label={c.label} />
          ))}
        </video>
      )}
      <div className="form-row">
        <label>
          Language
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
                {video.captions.some((c) => c.language === l.value) ? " (has captions)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          Name in the player
          <input value={label} maxLength={60} onChange={(e) => setLabel(e.target.value)} />
        </label>
      </div>

      {video.can_transcribe && (
        <section className="module" aria-labelledby="automatic-title">
          <h2 id="automatic-title">Write them automatically</h2>
          <p className="muted small">
            Speech recognition on GSA's own server writes a first draft; the sound never leaves the server. Check and correct it before
            students rely on it.
          </p>
          {video.transcription === "waiting" || video.transcription === "working" ? (
            <p className="notice">Being written. Come back in a few minutes.</p>
          ) : (
            <button
              type="button"
              className="secondary"
              onClick={() =>
                act(() => post(`/videos/${itemId}/transcribe/`, { language }), "Asked for captions to be written.", "Could not ask for captions.")
              }
            >
              Write {LANGUAGES.find((l) => l.value === language)?.label ?? ""} captions automatically
            </button>
          )}
          {video.transcription === "failed" && video.transcription_failure && <p className="error">{video.transcription_failure}</p>}
        </section>
      )}

      <form className="module stack" onSubmit={putUp} aria-labelledby="file-title">
        <h2 id="file-title">Put up a captions file</h2>
        <label>
          WebVTT file (.vtt)
          <input type="file" accept=".vtt,text/vtt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <div className="actions">
          <button type="submit" className="secondary" disabled={!file}>
            Put the file up
          </button>
        </div>
      </form>

      <form className="module stack" onSubmit={save} aria-labelledby="cues-title">
        <h2 id="cues-title">Write or correct them</h2>
        {cues.length === 0 && <p className="muted">No captions in this language yet.</p>}
        <ol className="cue-list">
          {cues.map((cue, index) => (
            <li key={index} className="cue">
              <div className="cue-times">
                <label>
                  From (seconds)
                  <input type="number" min={0} step={0.1} value={cue.start} onChange={(e) => change(index, { start: Number(e.target.value) })} />
                </label>
                <label>
                  To (seconds)
                  <input type="number" min={0} step={0.1} value={cue.end} onChange={(e) => change(index, { end: Number(e.target.value) })} />
                </label>
                <span className="muted small">
                  {clock(cue.start)} to {clock(cue.end)}
                </span>
              </div>
              <label>
                Caption {index + 1}
                <textarea rows={2} maxLength={500} value={cue.text} onChange={(e) => change(index, { text: e.target.value })} />
              </label>
              <button
                type="button"
                className="secondary small-button"
                aria-label={`Remove caption ${index + 1}`}
                onClick={() => setCues(cues.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </li>
          ))}
        </ol>
        <div className="actions">
          <button type="button" className="secondary" onClick={addCue}>
            Add a caption{low ? " at this point in the video" : ""}
          </button>
          {existing && (
            <button
              type="button"
              className="secondary"
              onClick={() =>
                act(
                  async () => {
                    await remove(`/videos/${itemId}/captions/${language}/`);
                    setCues([]);
                  },
                  `Removed the ${label} captions.`,
                  "Could not remove the captions.",
                )
              }
            >
              Remove these captions
            </button>
          )}
          <button type="submit" disabled={cues.length === 0}>
            Save captions
          </button>
        </div>
      </form>
    </article>
  );
}

