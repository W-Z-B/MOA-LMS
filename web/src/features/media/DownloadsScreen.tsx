import { useEffect, useState } from "react";
import { sizeInWords } from "../../api/types-content";
import { dmy } from "../../app/format";
import { chosen, setDataLight, suggested, useDataLight } from "./dataLight";
import { canKeep, keptModules, onKeptChange, removeModule, spaceLeft, type KeptModule } from "./offlineStore";
import "./media.css";

/**
 * Downloaded, under Me (items 4.03 and 4.05): the modules kept on this device to read offline, each with its
 * size and a way to remove it, and data-light mode for this device. What is kept belongs to the person signed
 * in and is removed when they sign out.
 */
export default function DownloadsScreen() {
  const light = useDataLight();
  const [mode, setMode] = useState<"auto" | "on" | "off">(() => {
    const own = chosen();
    return own === null ? "auto" : own ? "on" : "off";
  });
  const [kept, setKept] = useState<KeptModule[] | null>(null);
  const [room, setRoom] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      keptModules()
        .then(setKept)
        .catch(() => setKept([]));
      spaceLeft().then(setRoom);
    };
    load();
    return onKeptChange(load);
  }, []);

  function choose(value: "auto" | "on" | "off") {
    setMode(value);
    setDataLight(value === "auto" ? null : value === "on");
  }

  async function remove(module: KeptModule) {
    await removeModule(module.module);
    setStatus(`Removed “${module.title}” from this device.`);
  }

  const total = (kept ?? []).reduce((sum, m) => sum + m.bytes, 0);

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Downloaded</h1>
          <p className="muted">Modules kept on this device to read without signal, and how much data the LMS uses here.</p>
        </div>
      </div>
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>

      <section className="module" aria-labelledby="data-light-title">
        <h2 id="data-light-title">Data-light mode</h2>
        <p className="muted small">
          Pictures and video load only when you ask for them, and large files say how big they are. It is {light ? "on" : "off"} on this device now.
        </p>
        <fieldset className="kind-choices">
          <legend className="sr-only">Data-light mode</legend>
          <label className="inline">
            <input type="radio" name="data-light" checked={mode === "auto"} onChange={() => choose("auto")} />
            As the device suggests ({suggested() ? "on" : "off"} here)
          </label>
          <label className="inline">
            <input type="radio" name="data-light" checked={mode === "on"} onChange={() => choose("on")} />
            Always on
          </label>
          <label className="inline">
            <input type="radio" name="data-light" checked={mode === "off"} onChange={() => choose("off")} />
            Off
          </label>
        </fieldset>
      </section>

      <section className="module" aria-labelledby="kept-title">
        <h2 id="kept-title">Kept to read offline</h2>
        {!canKeep() && <p className="muted">This browser cannot keep modules offline.</p>}
        {kept?.length === 0 && (
          <p className="muted">
            Nothing yet. Open a course and choose <strong>Keep to read offline</strong> on a module.
          </p>
        )}
        {kept && kept.length > 0 && (
          <>
            <p className="muted small">
              {sizeInWords(total)} kept{room !== null ? `; ${sizeInWords(room)} free for the LMS on this device` : ""}. Removed when you sign out.
            </p>
            <ul className="kept-list">
              {kept.map((m) => (
                <li key={m.module}>
                  <div className="stacked">
                    <a href={`#/sites/${m.site}`}>{m.title}</a>
                    <span className="muted small">
                      {m.siteTitle} · {sizeInWords(m.bytes)} · kept {dmy(m.keptAt)}
                    </span>
                  </div>
                  <button type="button" className="secondary small-button" onClick={() => remove(m)} aria-label={`Remove “${m.title}”`}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
