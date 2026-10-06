import type { ReactNode } from "react";
import { Crest } from "../../app/Crest";

/**
 * The frame of the pages seen before signing in (item 2.07, as the HRMS's): the School's crest and colours
 * beside the form. On a phone the crest and title sit in a band above it.
 */
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="login">
      <header className="auth-brand">
        <Crest size={140} label="Guyana School of Agriculture crest" />
        <div className="stacked">
          <p className="auth-title">Learning</p>
          <p className="auth-sub">Guyana School of Agriculture, Mon Repos and Essequibo campuses</p>
        </div>
        <p className="auth-motto">Founded September 1963 · Education is the best investment</p>
      </header>
      <main className="auth-main">
        {children}
        <p className="auth-foot">Every mark and every change to a course is written to the audit log.</p>
      </main>
    </div>
  );
}
