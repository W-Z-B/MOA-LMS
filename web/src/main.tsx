import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { startAutoFlush } from "./app/offlineQueue";
import { startPhotoOutbox } from "./features/practicals/photoOutbox";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Writes kept on this device without a connection are sent now, and again whenever it returns (item 4.02).
startAutoFlush();
// Photos taken in the field without signal wait in IndexedDB until their record has gone (items 3.12, 3.14).
startPhotoOutbox();

// Installable app: the service worker caches the shell only (never API data). Production builds only,
// so the Vite dev server keeps hot reload predictable.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}
