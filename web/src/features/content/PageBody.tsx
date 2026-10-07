import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { documentKind, sizeInWords } from "../../api/types-content";
import { LARGE_BYTES, useDataLight } from "../media/dataLight";
import { holdPictures, wireHeldPictures } from "../media/pictures";
import { drawMaths } from "./maths";

/**
 * A page's text as the server cleaned it (courses.richtext, an allow-list), with its maths drawn by KaTeX.
 * KaTeX is fetched only when the page has a formula. In data-light mode (item 4.05) its pictures wait behind
 * a button with their size; `sizes` gives the size of each course file by its item id.
 */
export function PageBody({ html, className = "page-body", sizes }: { html: string; className?: string; sizes?: Record<number, number> }) {
  const body = useRef<HTMLDivElement>(null);
  const light = useDataLight();
  const shown = useMemo(() => (light ? holdPictures(html, sizes) : html), [html, light, sizes]);
  useEffect(() => {
    if (!body.current) return;
    drawMaths(body.current).catch(() => undefined);
    return wireHeldPictures(body.current);
  }, [shown]);
  return <div ref={body} className={className} dangerouslySetInnerHTML={{ __html: shown }} />;
}

const PdfViewer = lazy(() => import("./PdfViewer"));

interface DocumentProps {
  title: string;
  filename: string | null;
  url: string;
  /** Bytes: said beside the download in data-light mode when the file is large. */
  size?: number;
}

/**
 * A file on the course shown in the page (item 2.14): a photograph inline, a PDF in the PDF.js viewer when
 * the student asks for it (the viewer is a large download, so it is never fetched unasked), and every file
 * can be downloaded. In data-light mode a photograph too waits until it is asked for.
 */
export function DocumentView({ title, filename, url, size = 0 }: DocumentProps) {
  const kind = documentKind(filename);
  const light = useDataLight();
  const [showing, setShowing] = useState(false);
  const [picture, setPicture] = useState(!light);
  const weight = light && size >= LARGE_BYTES ? ` (${sizeInWords(size)})` : "";
  return (
    <div className="document">
      {kind === "image" && picture && <img className="document-image" src={url} alt={title} loading="lazy" />}
      <p className="document-actions">
        <a href={url}>
          Download {filename}
          {weight}
        </a>
        {kind === "image" && !picture && (
          <button type="button" className="secondary small-button" onClick={() => setPicture(true)}>
            Show the picture{size ? ` (${sizeInWords(size)})` : ""}
          </button>
        )}
        {kind === "pdf" && (
          <button type="button" className="secondary small-button" aria-expanded={showing} onClick={() => setShowing(!showing)}>
            {showing ? "Hide the document" : "Show the document here"}
          </button>
        )}
      </p>
      {kind === "pdf" && showing && (
        <Suspense fallback={<p className="loading">Opening the document viewer…</p>}>
          <PdfViewer url={url} title={title} />
        </Suspense>
      )}
    </div>
  );
}
