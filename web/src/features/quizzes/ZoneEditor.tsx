import { useState } from "react";
import type { QuestionData } from "../../api/types-quizzes";
import { Diagram, ZoneShape } from "./AnswerInput";
import { imagePoint, type Zone } from "./quizUtil";

interface Props {
  src: string | null;
  data: QuestionData;
  onChange: (data: QuestionData) => void;
}

const WORD = { x: "Across", y: "Down", w: "Width", h: "Height", r: "Radius" } as const;

const num = (value: string) => (value === "" ? 0 : Number(value));

/**
 * Zones of a diagram question (item 3.01), drawn by clicking on the image: a rectangle from two corners, a
 * circle from its centre and a point on its edge. Every zone can also be typed as coordinates, in pixels of the
 * image, which is the way to do it with a keyboard.
 */
export function ZoneEditor({ src, data, onChange }: Props) {
  const width = Number(data.image_width) || 0;
  const height = Number(data.image_height) || 0;
  const labels: { id?: string; text: string }[] = data.labels ?? [];
  const zones: Zone[] = data.zones ?? [];
  const [tool, setTool] = useState<"rect" | "circle">("rect");
  const [first, setFirst] = useState<[number, number] | null>(null);
  const [label, setLabel] = useState(0);
  const labelId = (index: number) => labels[index]?.id ?? String.fromCharCode(97 + index);

  const setZones = (next: Zone[]) => onChange({ ...data, zones: next });
  const setZone = (index: number, zone: Zone) => setZones(zones.map((z, i) => (i === index ? zone : z)));

  function click(point: [number, number]) {
    if (!first) {
      setFirst(point);
      return;
    }
    const [x1, y1] = first;
    const [x2, y2] = point;
    const zone: Zone =
      tool === "rect"
        ? { label: labelId(label), shape: "rect", x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 1, h: Math.abs(y2 - y1) || 1 }
        : { label: labelId(label), shape: "circle", x: x1, y: y1, r: Math.round(Math.hypot(x2 - x1, y2 - y1)) || 1 };
    setZones([...zones, zone]);
    setFirst(null);
  }

  return (
    <fieldset className="stack">
      <legend>Zones on the image</legend>
      {!src || !width ? (
        <p className="muted">Choose the image first; then draw the zones on it.</p>
      ) : (
        <>
          <div className="form-row">
            <label>
              Draw
              <select
                value={tool}
                onChange={(e) => {
                  setTool(e.target.value as "rect" | "circle");
                  setFirst(null);
                }}
              >
                <option value="rect">A rectangle: click two corners</option>
                <option value="circle">A circle: click the centre, then the edge</option>
              </select>
            </label>
            <label>
              For the label
              <select value={label} onChange={(e) => setLabel(Number(e.target.value))}>
                {labels.map((l, i) => (
                  <option key={i} value={i}>
                    {l.text || `Label ${i + 1}`}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted small" role="status">
            {first ? `First point at ${first[0]}, ${first[1]}. Click the second point.` : "Click on the image to start a zone."}
          </p>
          <Diagram src={src} width={width} height={height} alt="The question's image" onClick={(e) => click(imagePoint(e, width, height))}>
            {zones.map((z, i) => (
              <g key={i}>
                <ZoneShape zone={z} className="zone" />
              </g>
            ))}
            {first && <circle cx={first[0]} cy={first[1]} r={Math.max(width, height) / 100} className="marker" />}
          </Diagram>
        </>
      )}
      {zones.map((z, i) => (
        <div key={i} className="zone-row">
          <strong>Zone {i + 1}</strong>
          <label>
            Label
            <select
              value={labels.findIndex((_, j) => labelId(j) === z.label)}
              onChange={(e) => setZone(i, { ...z, label: labelId(Number(e.target.value)) })}
              aria-label={`Zone ${i + 1}: label`}
            >
              {labels.map((l, j) => (
                <option key={j} value={j}>
                  {l.text || `Label ${j + 1}`}
                </option>
              ))}
            </select>
          </label>
          <label>
            Shape
            <select
              value={z.shape}
              aria-label={`Zone ${i + 1}: shape`}
              onChange={(e) => {
                const shape = e.target.value as Zone["shape"];
                const base = { label: z.label, shape, x: z.x ?? 10, y: z.y ?? 10 };
                setZone(i, shape === "rect" ? { ...base, w: 50, h: 50 } : shape === "circle" ? { ...base, r: 25 } : { label: z.label, shape, points: [[10, 10], [60, 10], [35, 50]] });
              }}
            >
              <option value="rect">Rectangle</option>
              <option value="circle">Circle</option>
              <option value="polygon">Polygon</option>
            </select>
          </label>
          {z.shape === "polygon" ? (
            <label className="grow">
              Points (across,down pairs)
              <input
                aria-label={`Zone ${i + 1}: points`}
                defaultValue={(z.points ?? []).map((p) => p.join(",")).join(" ")}
                onBlur={(e) =>
                  setZone(i, {
                    ...z,
                    points: e.target.value
                      .trim()
                      .split(/\s+/)
                      .map((pair) => pair.split(",").map(Number))
                      .filter((p) => p.length === 2 && p.every(Number.isFinite)),
                  })
                }
              />
            </label>
          ) : (
            (z.shape === "rect" ? (["x", "y", "w", "h"] as const) : (["x", "y", "r"] as const)).map((key) => (
              <label key={key} className="coord">
                {WORD[key]}
                <input type="number" min={0} aria-label={`Zone ${i + 1}: ${WORD[key].toLowerCase()}`} value={z[key] ?? 0} onChange={(e) => setZone(i, { ...z, [key]: num(e.target.value) })} />
              </label>
            ))
          )}
          <button type="button" className="secondary danger-text small-button" onClick={() => setZones(zones.filter((_, j) => j !== i))} aria-label={`Remove zone ${i + 1}`}>
            Remove
          </button>
        </div>
      ))}
      <div className="actions">
        <button type="button" className="secondary small-button" onClick={() => setZones([...zones, { label: labelId(label), shape: "rect", x: 10, y: 10, w: 50, h: 50 }])}>
          Add a zone by typing its position
        </button>
      </div>
    </fieldset>
  );
}
