import { GlobalWorkerOptions, getDocument, type PDFDocumentLoadingTask, type PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";

GlobalWorkerOptions.workerSrc = workerUrl;

interface Props {
  url: string;
  title: string;
}

/**
 * A PDF shown in the page with PDF.js (item 2.14, ADR 0012), one page at a time, as wide as the screen allows.
 * The file is fetched with the person's session, as a download is, and handed to PDF.js as data. WebAssembly
 * is not used, so the Content-Security-Policy needs nothing new. Loaded only when someone asks to see a PDF.
 */
export default function PdfViewer({ url, title }: Props) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const frame = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    let task: PDFDocumentLoadingTask | null = null;
    fetch(url, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.arrayBuffer();
      })
      .then((data) => {
        if (!live) return null;
        task = getDocument({ data: new Uint8Array(data), useWasm: false });
        return task.promise;
      })
      .then((doc) => live && doc && setPdf(doc))
      .catch(() => live && setError("The document could not be shown. Download it instead."));
    return () => {
      live = false;
      void task?.destroy();
    };
  }, [url]);

  useEffect(() => {
    if (!pdf || !canvas.current || !frame.current) return;
    let cancelled = false;
    let task: { cancel: () => void; promise: Promise<void> } | null = null;
    pdf.getPage(page).then((sheet) => {
      if (cancelled || !canvas.current || !frame.current) return;
      const width = frame.current.clientWidth || 600;
      const scale = width / sheet.getViewport({ scale: 1 }).width;
      const ratio = window.devicePixelRatio || 1;
      const viewport = sheet.getViewport({ scale: scale * ratio });
      canvas.current.width = Math.floor(viewport.width);
      canvas.current.height = Math.floor(viewport.height);
      task = sheet.render({ canvas: canvas.current, viewport });
      task.promise.catch(() => undefined);
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, page]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  const pages = pdf?.numPages ?? 0;
  return (
    <div className="pdf-viewer" ref={frame}>
      {!pdf && <p className="loading">Opening the document…</p>}
      <canvas ref={canvas} role="img" aria-label={pdf ? `${title}, page ${page} of ${pages}` : title} />
      {pdf && (
        <div className="pdf-pages">
          <button type="button" className="secondary small-button" onClick={() => setPage(page - 1)} disabled={page <= 1}>
            Previous page
          </button>
          <span aria-live="polite">
            Page {page} of {pages}
          </span>
          <button type="button" className="secondary small-button" onClick={() => setPage(page + 1)} disabled={page >= pages}>
            Next page
          </button>
        </div>
      )}
    </div>
  );
}
