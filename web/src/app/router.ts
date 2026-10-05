/** Hash-based routing with no dependency, shared across the GSA ecosystem front-ends. */

import { useEffect, useState } from "react";

const read = () => window.location.hash.replace(/^#/, "") || "/";

export function useHashRoute(): [string, (to: string) => void] {
  const [path, setPath] = useState<string>(read);
  useEffect(() => {
    const onChange = () => setPath(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [path, (to: string) => (window.location.hash = to)];
}

export interface NavItem {
  path: string;
  label: string;
  roles?: string[];
}

export const NAV: NavItem[] = [
  { path: "/", label: "My courses" },
  { path: "/admin", label: "Admin", roles: ["administrator", "course_admin"] },
  { path: "/account", label: "My account" },
];
