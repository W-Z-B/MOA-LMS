import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { Paginated, Site } from "../../api/types";

interface Props {
  campusCode: string | null;
  onNavigate: (to: string) => void;
}

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  lecturer: "Lecturer",
  assistant: "Teaching assistant",
  student: "Student",
  auditor: "Auditor",
};

/** The course sites this person belongs to. Academic sites come from the SRMS class lists. */
export function MyCoursesScreen({ campusCode, onNavigate }: Props) {
  const [sites, setSites] = useState<Site[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Paginated<Site>>("/sites/")
      .then((r) => {
        setSites(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load your courses.")));
  }, []);

  const visible = campusCode ? sites.filter((s) => !s.campus_code || s.campus_code === campusCode) : sites;

  return (
    <>
      <h1>My courses</h1>
      {error && <p className="error">{error}</p>}
      {visible.length === 0 ? (
        <p className="muted">
          You are not a member of any course yet. Academic courses appear here once the Registry enrols you in the SRMS.
        </p>
      ) : (
        <div className="cards">
          {visible.map((site) => (
            <button key={site.id} className="card" onClick={() => onNavigate(`/sites/${site.id}`)}>
              <h3>{site.title}</h3>
              <span className="muted small">
                {site.code}
                {site.term_code ? ` · ${site.term_code}` : ""}
                {site.campus_code ? ` · ${site.campus_code}` : ""}
              </span>
              <span>
                <span className="pill">{site.my_role ? ROLE_LABEL[site.my_role] : "Member"}</span>{" "}
                {!site.is_published && <span className="pill">Not published</span>}{" "}
                {site.kind === "staff_development" && <span className="pill">Staff development</span>}
              </span>
              <span className="muted small">{site.members} members</span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}
