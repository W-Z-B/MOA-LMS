import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import { canTeach, type SiteContents } from "../../api/types";
import type { Item } from "../../api/types-content";
import { useCrumb } from "../../app/frame";
import { PageBody } from "./PageBody";
import "./content.css";

interface Props {
  siteId: number;
  itemId: number;
}

/**
 * One page of a course, as students read it (item 2.12): the text the server cleaned, with its maths drawn.
 * Opening it records the page as complete for a student (item 2.16).
 */
export default function PageScreen({ siteId, itemId }: Props) {
  const [page, setPage] = useState<Item | null>(null);
  const [site, setSite] = useState<SiteContents["site"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb(page?.title);

  useEffect(() => {
    Promise.all([get<Item>(`/content/${itemId}/`), get<SiteContents>(`/sites/${siteId}/contents/`)])
      .then(([item, contents]) => {
        setPage(item);
        setSite(contents.site);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this page.")));
  }, [siteId, itemId]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!page || !site) return <p className="loading">Opening the page…</p>;
  return (
    <article className="page-view">
      <p className="back-link">
        <a href={`#/sites/${siteId}`}>Back to {site.title}</a>
      </p>
      <div className="page-head">
        <h1>{page.title}</h1>
        {canTeach(site.my_role) && (
          <a className="button secondary" href={`#/sites/${siteId}/pages/${itemId}/edit`}>
            Edit page
          </a>
        )}
      </div>
      {!page.is_published && <p className="notice">A draft: students do not see it until it is published.</p>}
      <PageBody html={page.body} className="page-body page-reading" />
      {page.source && <p className="muted small">Source: {page.source}</p>}
    </article>
  );
}
