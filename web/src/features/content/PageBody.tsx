import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { documentKind } from "../../api/types-content";
import { drawMaths } from "./maths";

/**
 * A page's text as the server cleaned it (courses.richtext, an allow-list), with its maths drawn by KaTeX.
 * KaTeX is fetched only when the page has a formula.
 */
export function PageBody({ html, className = "page-body" }: { html: string; className?: string }) {
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (body.current) drawMaths(body.current).catch(() => undefined);
  }, [html]);
  return <div ref={body} className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

const PdfViewer = lazy(() => import("./PdfViewer"));

interface DocumentProps {
  title: string;
  filename: string | null;
  url: string;
}

/**
 * A file on the course shown in the page (item 2.14): a photograph inline, a PDF in the PDF.js viewer when
 * the student asks for it (the viewer is a large download, so it is never fetched unasked), and every file
 * can be downloaded.
 */
export function DocumentView({ title, filename, url }: DocumentProps) {
  const kind = documentKind(filename);
  const [showing, setShowing] = useState(false);
  return (
    <div className="document">
      {kind === "image" && <img className="document-image" src={url} alt={title} loading="lazy" />}
      <p className="document-actions">
        <a href={url}>Download {filename}</a>
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
