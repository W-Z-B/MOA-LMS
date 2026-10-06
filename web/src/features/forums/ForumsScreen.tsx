import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import { canTeach } from "../../api/types";
import type { Forum } from "../../api/types-talk";
import { ForumList, ReportsQueue } from "./DiscussionTab";
import { useSites } from "./shared";

/** Discussion (#/forums): the forums of every course the person is on, and for moderators the reports. */
export function ForumsScreen() {
  const sites = useSites();
  const [forums, setForums] = useState<Forum[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Forum[]>("/forums/")
      .then(setForums)
      .catch((err) => setError(errorMessage(err, "Could not load the forums.")));
  }, []);

  const moderates = sites.some((site) => canTeach(site.my_role));
  const bySite = sites
    .map((site) => ({ site, forums: (forums ?? []).filter((f) => f.site === site.id) }))
    .filter((group) => group.forums.length > 0);

  return (
    <>
      <div className="page-head">
        <h1>Discussion</h1>
      </div>
      {moderates && <ReportsQueue />}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {forums === null && !error && <p className="loading">Loading forums…</p>}
      {forums !== null && bySite.length === 0 && <p className="muted">None of your courses has a forum yet.</p>}
      {bySite.map(({ site, forums: list }) => (
        <section key={site.id} aria-labelledby={`forums-${site.id}`}>
          <h2 id={`forums-${site.id}`} className="talk-site">
            <a href={`#/sites/${site.id}/discussion`}>{site.title}</a>
          </h2>
          <ForumList forums={list} empty="" />
        </section>
      ))}
    </>
  );
}
