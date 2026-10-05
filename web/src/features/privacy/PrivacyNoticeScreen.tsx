import { useEffect, useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { CurrentNotice, PrivacyNotice } from "./types";

interface Props {
  /** Called once the person has read the version in force, or when none is published. Keep it stable. */
  onAcknowledged: () => void;
}

/** The privacy notice text, a blank line between paragraphs. */
export function NoticeText({ notice }: { notice: PrivacyNotice }) {
  return (
    <>
      {notice.body.split(/\n\s*\n/).map((paragraph, i) => (
        <p key={i} style={{ whiteSpace: "pre-line" }}>
          {paragraph}
        </p>
      ))}
    </>
  );
}

/** The privacy notice in force, shown at sign-in until the person has read this version (item 1.18). */
export function PrivacyNoticeScreen({ onAcknowledged }: Props) {
  const [notice, setNotice] = useState<PrivacyNotice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<CurrentNotice>("/privacy/notice/")
      .then((r) => {
        if (r.notice && !r.acknowledged) setNotice(r.notice);
        else onAcknowledged(); // nothing published, or already read: nothing to show
      })
      .catch((err) => setError(errorMessage(err, "Could not load the privacy notice.")));
  }, [onAcknowledged]);

  async function acknowledge() {
    if (!notice) return;
    setBusy(true);
    try {
      await post("/privacy/notice/acknowledge/", { version: notice.version });
      onAcknowledged();
    } catch (err) {
      setError(errorMessage(err, "Could not record that you have read the notice."));
      setBusy(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!notice) return <p className="loading">Loading the privacy notice…</p>;

  return (
    <div className="content" style={{ maxWidth: 760, margin: "0 auto" }}>
      <div className="panel">
        <h1>{notice.title}</h1>
        <p className="muted small">
          Version {notice.version}. Please read this before you continue. You can read it again at any time from My
          data.
        </p>
        <NoticeText notice={notice} />
        <button onClick={acknowledge} disabled={busy}>
          I have read this notice
        </button>
      </div>
    </div>
  );
}
