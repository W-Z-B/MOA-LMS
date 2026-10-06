import { useEffect, useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import { sizeInWords, type Item } from "../../api/types-content";
import { clock, type VideoInfo, type VideoQuality } from "../../api/types-media";
import { useDataLight } from "./dataLight";
import "./media.css";

const QUALITY_KEY = "gsa-lms.video-quality";
const POLL_MS = 20_000;

function rememberedQuality(): VideoQuality | null {
  try {
    const value = localStorage.getItem(QUALITY_KEY);
    return value === "low" || value === "standard" || value === "audio" ? value : null;
  } catch {
    return null;
  }
}

function remember(quality: VideoQuality) {
  try {
    localStorage.setItem(QUALITY_KEY, quality);
  } catch {
    /* a convenience of this device only */
  }
}

interface Props {
  item: Item;
  siteId: number;
  teaching: boolean;
}

/**
 * A lecture video in the course (items 4.06, 4.07): played in the quality the student chooses, each with
 * its size, captions on when there are any. In data-light mode (item 4.05) the low copy is chosen and
 * nothing, not even the poster frame, is fetched until Play is pressed. While the video is being prepared it
 * says so, and teaching staff can ask again when it could not be.
 */
export default function VideoItem({ item, siteId, teaching }: Props) {
  const light = useDataLight();
  const [info, setInfo] = useState<VideoInfo | null>(item.video ?? null);
  const [chosen, setChosen] = useState<VideoQuality | null>(rememberedQuality);
  const [error, setError] = useState<string | null>(null);
  const preparing = info?.status === "waiting" || info?.status === "converting";

  useEffect(() => {
    if (!preparing) return;
    const handle = setInterval(() => {
      get<VideoInfo>(`/videos/${item.id}/`)
        .then(setInfo)
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(handle);
  }, [preparing, item.id]);

  if (!info) return null;
  if (preparing)
    return (
      <p className="notice video-state" role="status">
        Being prepared for phones: a low and a standard copy and one with sound only. It will be ready in a few minutes.
      </p>
    );
  if (info.status === "failed")
    return (
      <div className="video-state">
        <p className="error" role="alert">
          {teaching ? `This video could not be prepared. ${info.failure ?? ""}` : "This video is not ready yet."}
        </p>
        {teaching && (
          <button
            type="button"
            className="secondary small-button"
            onClick={() =>
              post<VideoInfo>(`/videos/${item.id}/convert/`)
                .then(setInfo)
                .catch((err) => setError(errorMessage(err, "Could not ask again.")))
            }
          >
            Prepare it again
          </button>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    );

  const copies = info.qualities;
  // Data-light chooses the low copy; otherwise the standard one. A choice the person made is kept.
  const fallback = light ? copies[0] : (copies.find((c) => c.quality === "standard") ?? copies[0]);
  const playing = copies.find((c) => c.quality === chosen) ?? fallback;
  if (!playing) return null;
  const name = `quality-${item.id}`;

  return (
    <div className="video-item">
      {playing.quality === "audio" ? (
        <audio key={playing.url} className="video-player" controls preload="none" src={playing.url} aria-label={`${item.title}, sound only`} />
      ) : (
        <video
          key={playing.url}
          className="video-player"
          controls
          playsInline
          preload={light ? "none" : "metadata"}
          poster={light ? undefined : (info.poster_url ?? undefined)}
          src={playing.url}
          aria-label={item.title}
        >
          {info.captions.map((c, index) => (
            <track key={c.language} kind="captions" src={c.url} srcLang={c.language} label={c.label} default={index === 0} />
          ))}
        </video>
      )}
      <fieldset className="video-qualities">
        <legend>
          Quality{info.duration_seconds ? ` (${clock(info.duration_seconds)} long)` : ""}
        </legend>
        {copies.map((copy) => (
          <label className="inline" key={copy.quality}>
            <input
              type="radio"
              name={name}
              checked={copy.quality === playing.quality}
              onChange={() => {
                setChosen(copy.quality);
                remember(copy.quality);
              }}
            />
            {copy.label}, {sizeInWords(copy.size)}
          </label>
        ))}
      </fieldset>
      {info.captions.length === 0 && <p className="muted small">No captions yet.</p>}
      {teaching && (
        <p className="document-actions">
          <a className="button secondary small-button" href={`#/sites/${siteId}/videos/${item.id}/captions`}>
            Captions
          </a>
        </p>
      )}
    </div>
  );
}
