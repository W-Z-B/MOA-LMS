/** Fictional packages, library items and reports for the component tests of this folder. */

import type { ContentPackage, LibraryItem, PackageAttempt } from "../../api/types-packages";
import { contents } from "../content/fixtures";

export function attempt(number: number, more: Partial<PackageAttempt> = {}): PackageAttempt {
  return {
    id: number,
    number,
    registration: `5b9e4a3c-1111-4222-8333-44445555666${number}`,
    is_preview: false,
    learner: null,
    student_no: null,
    completion: "not_attempted",
    success: "unknown",
    score: null,
    score_percent: null,
    created_at: "2026-10-01T10:00:00Z",
    last_commit_at: null,
    completed_at: null,
    ...more,
  };
}

export function pkg(more: Partial<ContentPackage> = {}): ContentPackage {
  return {
    id: 3,
    item: 12,
    title: "Soil testing",
    site: 9,
    module: 1,
    is_published: true,
    licence: "gsa_own",
    source: "",
    standard: "scorm12",
    version_label: "SCORM 1.2",
    scos: [{ id: "i1", title: "Taking a sample", href: "index.html", parameters: "" }],
    entries: 3,
    unpacked_bytes: 1200,
    weight: "2.00",
    grade_category: null,
    max_attempts: 2,
    my_attempts: [],
    attempts_left: 2,
    my_result: { fraction: null, state: "not_due" },
    activity: "https://lms.example/xapi/activities/packages/3",
    ...more,
  };
}

export const siteAs = (role: "lecturer" | "student") => contents([], role);

export function libraryItem(id: number, title: string, more: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id,
    kind: "file",
    title,
    description: "",
    body: "",
    filename: "guide.pdf",
    file_size: 1000,
    download_url: `/api/v1/library/items/${id}/download/`,
    url: "",
    package: {},
    licence: "open_licence",
    open_licence: "cc_by",
    source: "FAO e-learning Academy",
    publisher: "FAO",
    department_code: "AGRON",
    is_open_resource: true,
    tags: ["pests"],
    shared_from: null,
    may_change: true,
    created_at: "2026-10-01T10:00:00Z",
    ...more,
  };
}

export const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
