import { useEffect, useState } from "react";
import { errorMessage } from "../../api/client";
import { sizeInWords } from "../../api/types-content";
import { canKeep, describeModule, keepModule, keptModules, onKeptChange, removeModule, spaceLeft, type OfflineManifest } from "./offlineStore";
import "./media.css";

type Phase =
  | { at: "idle" }
  | { at: "asking" }
  | { at: "confirm"; manifest: OfflineManifest; room: number | null }
  | { at: "keeping"; manifest: OfflineManifest; bytes: number }
  | { at: "kept"; bytes: number };

const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "2 pages, 1 document and 1 video at low quality". */
function contents(manifest: OfflineManifest): string {
  const of = (kind: string) => manifest.files.filter((f) => f.kind === kind).length;
  const parts = [
    of("page") && count(of("page"), "page"),
    of("document") + of("picture") && count(of("document") + of("picture"), "document or picture", "documents and pictures"),
    of("video") && `${count(of("video"), "video")} at low quality`,
  ].filter(Boolean) as string[];
  if (parts.length === 0) return "the module's outline";
  return parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * "Keep to read offline" for one module (item 4.03): the space it will take is shown first, with what cannot
 * be kept (links), and the space the phone has left. Then its files are kept for the signed-in person, with
 * progress as they arrive; it can be removed here or from Downloaded under Me.
 */
export default function ModuleDownload({ moduleId, title }: { moduleId: number; title: string }) {
  const [phase, setPhase] = useState<Phase>({ at: "idle" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const look = () =>
      keptModules()
        .then((kept) => {
          const mine = kept.find((m) => m.module === moduleId);
          setPhase((now) => (mine ? { at: "kept", bytes: mine.bytes } : now.at === "kept" ? { at: "idle" } : now));
        })
        .catch(() => undefined);
    look();
    return onKeptChange(look);
  }, [moduleId]);

  if (!canKeep()) return null;

  async function ask() {
    setError(null);
    setPhase({ at: "asking" });
    try {
      const [manifest, room] = await Promise.all([describeModule(moduleId), spaceLeft()]);
      setPhase({ at: "confirm", manifest, room });
    } catch (err) {
      setPhase({ at: "idle" });
      setError(errorMessage(err, "Could not find out what the module needs. Try again when you have signal."));
    }
  }

  async function keep(manifest: OfflineManifest) {
    setPhase({ at: "keeping", manifest, bytes: 0 });
    try {
      const kept = await keepModule(manifest, (bytes) => setPhase({ at: "keeping", manifest, bytes }));
      setPhase({ at: "kept", bytes: kept.bytes });
    } catch (err) {
      setPhase({ at: "idle" });
      setError(err instanceof Error ? err.message : "Could not keep the module.");
    }
  }

  return (
    <div className="module-download">
      {phase.at === "idle" && (
        <button type="button" className="secondary small-button" onClick={ask} aria-label={`Keep “${title}” to read offline`}>
          Keep to read offline
        </button>
      )}
      {phase.at === "asking" && <p className="muted small">Finding out how much space it needs…</p>}
      {phase.at === "confirm" && (
        <div className="keep-confirm" role="group" aria-label={`Keep “${title}” to read offline`}>
          <p>
            This keeps <strong>{sizeInWords(phase.manifest.total_bytes)}</strong> on this device: {contents(phase.manifest)}.
            {phase.room !== null && ` The device has ${sizeInWords(phase.room)} free for the LMS.`}
          </p>
          {phase.manifest.left_out.length > 0 && (
            <p className="muted small">Not kept, as they need a connection: {phase.manifest.left_out.join(", ")}.</p>
          )}
          {phase.room !== null && phase.room < phase.manifest.total_bytes ? (
            <p className="error">There is not enough space on this device. Remove something under Downloaded first.</p>
          ) : null}
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setPhase({ at: "idle" })}>
              Cancel
            </button>
            <button type="button" disabled={phase.room !== null && phase.room < phase.manifest.total_bytes} onClick={() => keep(phase.manifest)}>
              Keep it
            </button>
          </div>
        </div>
      )}
      {phase.at === "keeping" && (
        <p className="muted small" role="status">
          Keeping {title}: {sizeInWords(phase.bytes)} of {sizeInWords(phase.manifest.total_bytes)}…
        </p>
      )}
      {phase.at === "kept" && (
        <p className="kept-line">
          <span className="done-mark">Kept offline</span>
          <span className="muted small">{sizeInWords(phase.bytes)}</span>
          <button type="button" className="secondary small-button" onClick={() => removeModule(moduleId)} aria-label={`Remove “${title}” from this device`}>
            Remove
          </button>
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
