/** What a page tells the frame around it (item 2.07): the last breadcrumb, and that a decision was made. */

import { createContext, useContext, useEffect, useState } from "react";

export interface Frame {
  /** The last breadcrumb, such as the name of an open course site. Null removes it. */
  setCrumb: (label: string | null) => void;
  /** A decision was made here: the To do count in the frame is fetched again. */
  decided: () => void;
}

export const FrameContext = createContext<Frame>({ setCrumb: () => undefined, decided: () => undefined });

export const useFrame = () => useContext(FrameContext);

/** Name the item a page shows, as the breadcrumb after its section: Home / My courses / Introduction to Crop Production. */
export function useCrumb(label: string | null | undefined) {
  const { setCrumb } = useFrame();
  useEffect(() => {
    setCrumb(label || null);
    return () => setCrumb(null);
  }, [label, setCrumb]);
}

/** Phones get bottom tabs and sheets; wider screens the header. The same width as the phone rules in index.css. */
export const PHONE = "(max-width: 760px)";

const matches = () => typeof window.matchMedia === "function" && window.matchMedia(PHONE).matches;

export function usePhone(): boolean {
  const [phone, setPhone] = useState(matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(PHONE);
    const onChange = () => setPhone(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return phone;
}
