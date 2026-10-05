import { useEffect, useRef, useState } from "react";
import { errorMessage, post, remove } from "../../api/client";
import type { FeedbackFile, WorkSubmission } from "../../api/types-marking";
import { FeedbackList } from "../assignments/Feedback";

interface Props {
  submission: WorkSubmission;
  locked: boolean;
  onChanged: (submission: WorkSubmission) => void;
}

const canRecord = () =>
  typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

/**
 * Feedback files and spoken feedback returned with the mark (item 2.24). A recording made on a phone is
 * uploaded like any file; where the browser can record, the marker may record here instead.
 */
export function FeedbackFiles({ submission, locked, onChanged }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [take, setTake] = useState<{ file: File; url: string } | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => (take ? URL.revokeObjectURL(take.url) : undefined), [take]);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("file", file);
      onChanged(await post<WorkSubmission>(`/submissions/${submission.id}/feedback-files/`, body));
      setTake(null);
      if (input.current) input.current.value = "";
    } catch (err) {
      setError(errorMessage(err, "Could not return the file."));
    } finally {
      setBusy(false);
    }
  }

  async function takeBack(file: FeedbackFile) {
    try {
      await remove(`/feedback-files/${file.id}/`);
      onChanged({ ...submission, feedback_files: submission.feedback_files.filter((f) => f.id !== file.id) });
    } catch (err) {
      setError(errorMessage(err, "Could not take the file back."));
    }
  }

  async function record() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const parts: Blob[] = [];
      rec.ondataavailable = (e) => parts.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const type = rec.mimeType || "audio/webm";
        const blob = new Blob(parts, { type });
        const file = new File([blob], `spoken-feedback.${type.includes("ogg") ? "ogg" : "webm"}`, { type });
        setTake({ file, url: URL.createObjectURL(blob) });
      };
      rec.start();
      recorder.current = rec;
      setRecording(true);
    } catch {
      setError("The microphone could not be used. Record on your phone and upload the recording instead.");
    }
  }

  function stop() {
    recorder.current?.stop();
    recorder.current = null;
    setRecording(false);
  }

  return (
    <section className="stack" aria-label="Feedback files">
      <h3 className="small-heading">Feedback files and recordings</h3>
      <FeedbackList files={submission.feedback_files} onRemove={locked ? undefined : takeBack} />
      {!locked && (
        <>
          <label>
            Return a file or a recording
            <input
              ref={input}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.docx,.xlsx,.pptx,.m4a,.mp4,.mp3,.ogg,.oga,.opus,.webm"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void send(file);
              }}
            />
          </label>
          {canRecord() && (
            <div className="actions">
              {!recording && !take && (
                <button type="button" className="secondary" onClick={record}>
                  Record spoken feedback
                </button>
              )}
              {recording && (
                <button type="button" className="danger" onClick={stop}>
                  Stop recording
                </button>
              )}
              {take && (
                <>
                  <audio controls src={take.url} aria-label="The recording" />
                  <button type="button" disabled={busy} onClick={() => send(take.file)}>
                    Return this recording
                  </button>
                  <button type="button" className="secondary" onClick={() => setTake(null)}>
                    Discard
                  </button>
                </>
              )}
            </div>
          )}
          <p className="muted small">The student sees these once the mark is released.</p>
        </>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
