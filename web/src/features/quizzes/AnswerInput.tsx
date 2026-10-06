import { useState, type MouseEvent, type ReactNode } from "react";
import type { AttemptQuestion } from "../../api/types-quizzes";
import { imagePoint, zoneCentre, type Zone } from "./quizUtil";
import { ClozeText, Rich } from "./Rich";

type Resp = Record<string, unknown>;

interface Props {
  q: AttemptQuestion;
  value: Resp | null;
  /** typing: the answer is still being typed, so it is saved after a pause rather than at every key. */
  onChange: (response: Resp, typing?: boolean) => void;
  /** A file response needs a connection: the file is sent at once. */
  onFile: (file: File) => void;
  disabled?: boolean;
}

/** The way to answer one question, by its type: always a native control a keyboard and a screen reader can use. */
export function AnswerInput({ q, value, onChange, onFile, disabled }: Props) {
  const n = q.position;
  const d = q.data;
  const v = value ?? {};
  switch (q.qtype) {
    case "multichoice": {
      const choices: { id: string; text: string }[] = d.choices ?? [];
      if (d.single)
        return (
          <fieldset className="answer-options" disabled={disabled}>
            <legend>Choose one answer</legend>
            {choices.map((c) => (
              <label key={c.id} className="option">
                <input type="radio" name={`q${n}`} checked={v.choice === c.id} onChange={() => onChange({ choice: c.id })} />
                <Rich html={c.text} inline />
              </label>
            ))}
            {v.choice != null && (
              <button type="button" className="link clear-choice" onClick={() => onChange({ choice: null })}>
                Clear my choice
              </button>
            )}
          </fieldset>
        );
      const chosen = new Set((v.choices as string[]) ?? []);
      return (
        <fieldset className="answer-options" disabled={disabled}>
          <legend>Choose one or more answers</legend>
          {choices.map((c) => (
            <label key={c.id} className="option">
              <input
                type="checkbox"
                checked={chosen.has(c.id)}
                onChange={(e) => {
                  const next = new Set(chosen);
                  if (e.target.checked) next.add(c.id);
                  else next.delete(c.id);
                  onChange({ choices: choices.map((x) => x.id).filter((id) => next.has(id)) });
                }}
              />
              <Rich html={c.text} inline />
            </label>
          ))}
        </fieldset>
      );
    }
    case "truefalse":
      return (
        <fieldset className="answer-options" disabled={disabled}>
          <legend>True or false?</legend>
          {[true, false].map((answer) => (
            <label key={String(answer)} className="option">
              <input type="radio" name={`q${n}`} checked={v.answer === answer} onChange={() => onChange({ answer })} />
              {answer ? "True" : "False"}
            </label>
          ))}
        </fieldset>
      );
    case "matching": {
      const matches = (v.matches as Record<string, string>) ?? {};
      return (
        <fieldset className="answer-options" disabled={disabled}>
          <legend>Match each item to an answer</legend>
          {(d.prompts ?? []).map((p: { id: string; text: string }, i: number) => (
            <div key={p.id} className="match-row">
              <span id={`q${n}-p${i}`}>
                <Rich html={p.text} inline />
              </span>
              <select
                aria-labelledby={`q${n}-p${i}`}
                value={matches[p.id] ?? ""}
                onChange={(e) => onChange({ matches: { ...matches, [p.id]: e.target.value || null } })}
              >
                <option value="">Choose…</option>
                {(d.answers ?? []).map((a: string) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </fieldset>
      );
    }
    case "ordering":
      return <Ordering q={q} value={v} onChange={onChange} disabled={disabled} />;
    case "shortanswer":
      return (
        <label>
          Your answer
          <input value={String(v.text ?? "")} disabled={disabled} maxLength={500} onChange={(e) => onChange({ text: e.target.value }, true)} />
        </label>
      );
    case "numerical": {
      const units: string[] = d.unit_mode !== "none" ? (d.units ?? []) : [];
      return (
        <div className="form-row">
          <label className="grow">
            Your answer (a number)
            <input
              inputMode="decimal"
              value={String(v.value ?? "")}
              disabled={disabled}
              onChange={(e) => onChange({ value: e.target.value, unit: v.unit ?? "" }, true)}
            />
          </label>
          {units.length > 0 && (
            <label>
              Unit{d.unit_mode === "optional" ? " (optional)" : ""}
              <select value={String(v.unit ?? "")} disabled={disabled} onChange={(e) => onChange({ value: v.value ?? "", unit: e.target.value })}>
                <option value="">{d.unit_mode === "optional" ? "No unit" : "Choose…"}</option>
                {units.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      );
    }
    case "essay": {
      const text = String(v.text ?? (value === null ? (d.response_template ?? "") : ""));
      const words = text.trim() ? text.trim().split(/\s+/).length : 0;
      const limits = [d.min_words ? `at least ${d.min_words}` : "", d.max_words ? `at most ${d.max_words}` : ""].filter(Boolean).join(" and ");
      return (
        <label>
          Your answer
          <textarea rows={8} value={text} disabled={disabled} onChange={(e) => onChange({ text: e.target.value }, true)} />
          <span className="muted small" style={{ fontWeight: 400 }}>
            {words} {words === 1 ? "word" : "words"}
            {limits && ` (write ${limits} words)`}
          </span>
        </label>
      );
    }
    case "file": {
      const accepts: string[] = d.allowed_extensions ?? [];
      return (
        <div className="stack">
          <label>
            Your file ({accepts.map((e) => e.toUpperCase()).join(", ")}; at most {d.max_size_mb} MB)
            <input
              type="file"
              disabled={disabled}
              accept={accepts.map((e) => `.${e}`).join(",")}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onFile(file);
              }}
            />
          </label>
          {typeof v.filename === "string" && <p className="muted small">Uploaded: {v.filename}</p>}
        </div>
      );
    }
    case "cloze": {
      const gaps = (v.gaps as Record<string, string>) ?? {};
      const set = (key: string, text: string, typing: boolean) => onChange({ gaps: { ...gaps, [key]: text } }, typing);
      return (
        <ClozeText
          html={q.text}
          gap={(key) => {
            const gap = d.gaps?.[key];
            if (gap?.kind === "choice")
              return (
                <select aria-label={`Gap ${key}`} value={gaps[key] ?? ""} disabled={disabled} onChange={(e) => set(key, e.target.value, false)}>
                  <option value="">Choose…</option>
                  {(gap.choices ?? []).map((c: string) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              );
            return (
              <input
                aria-label={`Gap ${key}`}
                className="gap-input"
                inputMode={gap?.kind === "numerical" ? "decimal" : undefined}
                value={gaps[key] ?? ""}
                disabled={disabled}
                onChange={(e) => set(key, e.target.value, true)}
              />
            );
          }}
        />
      );
    }
    case "image_label":
      return <LabelImage q={q} value={v} onChange={onChange} disabled={disabled} />;
  }
  return null;
}

function Ordering({ q, value, onChange, disabled }: { q: AttemptQuestion; value: Resp; onChange: Props["onChange"]; disabled?: boolean }) {
  const items: { id: string; text: string }[] = q.data.items ?? [];
  const order = (value.order as string[] | undefined)?.length ? (value.order as string[]) : items.map((i) => i.id);
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));
  const move = (index: number, by: number) => {
    const next = [...order];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    onChange({ order: next });
  };
  return (
    <fieldset className="answer-options" disabled={disabled}>
      <legend>Put these in order, first at the top</legend>
      <ol className="order-list">
        {order.map((id, i) => (
          <li key={id}>
            <span className="order-text">
              <span className="order-n">{i + 1}.</span> <Rich html={byId[id]?.text ?? id} inline />
            </span>
            <span className="order-moves">
              <button type="button" className="secondary small-button" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move up: item ${i + 1}`}>
                Up
              </button>
              <button
                type="button"
                className="secondary small-button"
                disabled={i === order.length - 1}
                onClick={() => move(i, 1)}
                aria-label={`Move down: item ${i + 1}`}
              >
                Down
              </button>
            </span>
          </li>
        ))}
      </ol>
      {!(value.order as string[] | undefined)?.length && (
        <button type="button" className="secondary small-button" onClick={() => onChange({ order })}>
          Keep this order as my answer
        </button>
      )}
    </fieldset>
  );
}

/** A zone drawn on the diagram, in the image's own pixels (the SVG is scaled with the image). */
export function ZoneShape({ zone, className }: { zone: Zone; className?: string }) {
  if (zone.shape === "circle") return <circle className={className} cx={zone.x} cy={zone.y} r={zone.r} />;
  if (zone.shape === "polygon") return <polygon className={className} points={(zone.points ?? []).map((p) => p.join(",")).join(" ")} />;
  return <rect className={className} x={zone.x} y={zone.y} width={zone.w} height={zone.h} />;
}

function LabelImage({ q, value, onChange, disabled }: { q: AttemptQuestion; value: Resp; onChange: Props["onChange"]; disabled?: boolean }) {
  const d = q.data;
  const labels: { id: string; text: string }[] = d.labels ?? [];
  const width = Number(d.image_width) || 1;
  const height = Number(d.image_height) || 1;
  const [placing, setPlacing] = useState<string | null>(null);
  const text = (id: string) => labels.find((l) => l.id === id)?.text ?? "";

  if (d.mode === "drop_zones") {
    const zones: Zone[] = d.zones ?? [];
    const chosen = (value.zones as Record<string, string>) ?? {};
    return (
      <div className="stack">
        <Diagram src={q.image_url} width={width} height={height} alt={`Diagram for question ${q.position}, with ${zones.length} numbered zones`}>
          {zones.map((z, i) => {
            const [cx, cy] = zoneCentre(z);
            return (
              <g key={z.id}>
                <ZoneShape zone={z} className="zone" />
                <text x={cx} y={cy} className="zone-number">
                  {i + 1}
                </text>
              </g>
            );
          })}
        </Diagram>
        <fieldset className="answer-options" disabled={disabled}>
          <legend>Choose the label for each numbered zone</legend>
          {zones.map((z, i) => (
            <label key={z.id} className="match-row">
              Zone {i + 1}
              <select value={chosen[z.id ?? ""] ?? ""} onChange={(e) => onChange({ zones: { ...chosen, [z.id ?? ""]: e.target.value || null } })}>
                <option value="">Choose…</option>
                {labels.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.text}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>
      </div>
    );
  }

  const placements = (value.placements as { label: string; x: number; y: number }[]) ?? [];
  const put = (label: string, x: number, y: number) =>
    onChange({ placements: [...placements.filter((p) => p.label !== label), { label, x, y }] });
  return (
    <div className="stack">
      <p className="muted small">
        Choose a label, then tap the diagram where it belongs. Or type its position: across and down, in pixels of the image ({width} by {height}).
      </p>
      <Diagram
        src={q.image_url}
        width={width}
        height={height}
        alt={`Diagram for question ${q.position}`}
        onClick={
          placing && !disabled
            ? (e) => {
                const [x, y] = imagePoint(e, width, height);
                put(placing, x, y);
                setPlacing(null);
              }
            : undefined
        }
      >
        {placements.map((p) => (
          <g key={p.label}>
            <circle cx={p.x} cy={p.y} r={Math.max(width, height) / 80} className="marker" />
            <text x={p.x} y={p.y} dy={-Math.max(width, height) / 50} className="zone-number">
              {text(p.label)}
            </text>
          </g>
        ))}
      </Diagram>
      <fieldset className="answer-options" disabled={disabled}>
        <legend>Labels</legend>
        {labels.map((l) => {
          const at = placements.find((p) => p.label === l.id);
          return (
            <div key={l.id} className="place-row">
              <button type="button" className={placing === l.id ? "small-button" : "secondary small-button"} aria-pressed={placing === l.id} onClick={() => setPlacing(placing === l.id ? null : l.id)}>
                {placing === l.id ? `Tap the diagram for “${l.text}”` : `Place “${l.text}”`}
              </button>
              <label className="inline">
                Across
                <input
                  type="number"
                  min={0}
                  max={width}
                  value={at?.x ?? ""}
                  onChange={(e) => e.target.value !== "" && put(l.id, Number(e.target.value), at?.y ?? 0)}
                  aria-label={`${l.text}: across`}
                />
              </label>
              <label className="inline">
                Down
                <input
                  type="number"
                  min={0}
                  max={height}
                  value={at?.y ?? ""}
                  onChange={(e) => e.target.value !== "" && put(l.id, at?.x ?? 0, Number(e.target.value))}
                  aria-label={`${l.text}: down`}
                />
              </label>
            </div>
          );
        })}
      </fieldset>
    </div>
  );
}

/** The question's image with an SVG laid over it in the image's own pixels, so zones scale with it. */
export function Diagram({
  src,
  width,
  height,
  alt,
  onClick,
  children,
}: {
  src: string | null;
  width: number;
  height: number;
  alt: string;
  onClick?: (e: MouseEvent<SVGSVGElement>) => void;
  children?: ReactNode;
}) {
  return (
    <div className="diagram" style={{ aspectRatio: `${width} / ${height}` }}>
      {src && <img src={src} alt={alt} />}
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" onClick={onClick} className={onClick ? "placing" : undefined} aria-hidden="true">
        {children}
      </svg>
    </div>
  );
}
