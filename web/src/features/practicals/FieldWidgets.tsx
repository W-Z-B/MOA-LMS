/** The field controls shared by the checklist and the logbook: photographs from the phone's camera, the
 * place (only when asked for), and what happened to photographs kept without signal. */

import { useEffect, useMemo, useState } from "react";
import type { Photo } from "../../api/types-practicals";
import { MAX_PHOTOS } from "./helpers";
import { keepsPhotosOffline, usePhotoState } from "./photoOutbox";

function Thumb({ file, onRemove }: { file: File; onRemove: () => void }) {
  const url = useMemo(() => (typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  return (
    <li className="thumb">
      {url ? <img src={url} alt={`Photo ${file.name}`} /> : <span className="thumb-name">{file.name}</span>}
      <button type="button" className="secondary small-button" onClick={onRemove} aria-label={`Remove photo ${file.name}`}>
        Remove
      </button>
    </li>
  );
}

/**
 * Photographs for a record: "Take a photo" opens the back camera on a phone; "Choose photos" picks ones
 * already taken. Without signal they wait on the phone until the record has been sent.
 */
export function PhotoPicker({ files, onChange, idPrefix }: { files: File[]; onChange: (files: File[]) => void; idPrefix: string }) {
  const add = (list: FileList | null) => {
    if (!list) return;
    onChange([...files, ...Array.from(list)].slice(0, MAX_PHOTOS));
  };
  const full = files.length >= MAX_PHOTOS;
  return (
    <fieldset className="field-photos">
      <legend>Photos ({files.length} of at most {MAX_PHOTOS})</legend>
      <div className="big-buttons">
        <label className={full ? "file-button disabled" : "file-button"}>
          Take a photo
          <input
            id={`${idPrefix}-camera`}
            className="sr-only"
            type="file"
            accept="image/*"
            capture="environment"
            disabled={full}
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        <label className={full ? "file-button secondary disabled" : "file-button secondary"}>
          Choose photos
          <input
            id={`${idPrefix}-choose`}
            className="sr-only"
            type="file"
            accept="image/*"
            multiple
            disabled={full}
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {files.length > 0 && (
        <ul className="thumbs">
          {files.map((file, i) => (
            <Thumb key={`${file.name}-${i}`} file={file} onRemove={() => onChange(files.filter((_, j) => j !== i))} />
          ))}
        </ul>
      )}
      <p className="muted small">
        {keepsPhotosOffline
          ? "Without signal the photos stay on this phone and are sent after the record."
          : "This browser cannot keep photos without signal: keep this page open until they are sent."}
      </p>
    </fieldset>
  );
}

export interface Place {
  latitude: string;
  longitude: string;
  accuracy: number;
}

/**
 * The place, only when the person taps "Add my location". The phone is asked once, then; nothing is
 * tracked and nothing is read without the tap.
 */
export function LocationButton({ place, onChange }: { place: Place | null; onChange: (place: Place | null) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function locate() {
    if (!("geolocation" in navigator)) {
      setError("This phone cannot give a location. You can save without it.");
      return;
    }
    setBusy(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setBusy(false);
        onChange({
          latitude: pos.coords.latitude.toFixed(6),
          longitude: pos.coords.longitude.toFixed(6),
          accuracy: Math.round(pos.coords.accuracy),
        });
      },
      () => {
        setBusy(false);
        setError("The phone did not give a location. You can save without it.");
      },
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 60_000 },
    );
  }

  return (
    <fieldset className="field-place">
      <legend>Location (optional)</legend>
      <p className="muted small">
        Only if you want the place kept with this record, as evidence of where the work was done. The phone is asked once, when
        you tap; your location is never tracked.
      </p>
      {place ? (
        <div className="actions">
          <span role="status">
            Location added: {place.latitude}, {place.longitude} (to within {place.accuracy} m)
          </span>
          <button type="button" className="secondary" onClick={() => onChange(null)}>
            Remove location
          </button>
        </div>
      ) : (
        <button type="button" className="secondary" onClick={locate} disabled={busy}>
          {busy ? "Finding you…" : "Add my location"}
        </button>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </fieldset>
  );
}

/** Beside a saved record: what became of its photographs. */
export function PhotoState({ id }: { id: string | null }) {
  const state = usePhotoState(id);
  if (state === null) return null;
  if (state.state === "waiting")
    return (
      <span role="status" className="sync waiting">
        {state.count === 1 ? "1 photo" : `${state.count} photos`} waiting to send. They are sent after the record.
      </span>
    );
  if (state.state === "sent")
    return (
      <span role="status" className="sync sent">
        {state.count === 1 ? "Photo sent" : `${state.count} photos sent`}
      </span>
    );
  return (
    <span role="alert" className="sync refused">
      Photos not sent: {state.detail}
    </span>
  );
}

/** Photographs kept with a record, each opening the file itself. */
export function Gallery({ photos, label }: { photos: Photo[]; label: string }) {
  if (photos.length === 0) return null;
  return (
    <ul className="thumbs" aria-label={label}>
      {photos.map((p) => (
        <li key={p.id} className="thumb">
          <a href={p.download_url}>
            <img src={p.download_url} alt={p.filename} loading="lazy" />
          </a>
        </li>
      ))}
    </ul>
  );
}

