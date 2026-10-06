import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Site } from "../../api/types";
import { fakeServer, offline } from "../../test/fetch";
import { MyCoursesScreen } from "./MyCoursesScreen";

const site = (over: Partial<Site>): Site => ({
  id: 1,
  code: "AGR101-2026-27-S1-MRP",
  title: "Introduction to Crop Production",
  term_code: "2026-27-S1",
  campus_code: "MRP",
  source: "srms",
  kind: "academic",
  description: "",
  is_published: true,
  coursework_weight: "40.00",
  my_role: "student",
  members: 8,
  ...over,
});

const page = (results: Site[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("My courses", () => {
  it("lists each site with the person's role on it, and opens it", async () => {
    fakeServer({
      "GET /sites/": page([
        site({}),
        site({
          id: 2,
          code: "SD-101",
          title: "Records management",
          campus_code: "",
          kind: "staff_development",
          my_role: "lecturer",
          is_published: false,
        }),
      ]),
    });
    const onNavigate = vi.fn();
    render(<MyCoursesScreen campusCode={null} onNavigate={onNavigate} />);
    const crop = await screen.findByRole("button", { name: /Introduction to Crop Production/ });
    expect(crop).toHaveTextContent("AGR101-2026-27-S1-MRP · 2026-27-S1 · MRP");
    expect(crop).toHaveTextContent("Student");
    const records = screen.getByRole("button", { name: /Records management/ });
    expect(records).toHaveTextContent("Lecturer");
    expect(records).toHaveTextContent("Not published");
    expect(records).toHaveTextContent("Staff development");
    await userEvent.click(crop);
    expect(onNavigate).toHaveBeenCalledWith("/sites/1");
  });

  it("keeps to the chosen campus, but always shows sites with no campus", async () => {
    fakeServer({
      "GET /sites/": page([
        site({}),
        site({ id: 2, title: "Soil Science", campus_code: "ESQ" }),
        site({ id: 3, title: "Records management", campus_code: "" }),
      ]),
    });
    render(<MyCoursesScreen campusCode="ESQ" onNavigate={vi.fn()} />);
    expect(await screen.findByRole("button", { name: /Soil Science/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Records management/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Crop Production/ })).not.toBeInTheDocument();
  });

  it("explains an empty list, and says when the courses cannot be loaded", async () => {
    fakeServer({ "GET /sites/": offline });
    render(<MyCoursesScreen campusCode={null} onNavigate={vi.fn()} />);
    expect(await screen.findByText("Could not load your courses.")).toBeInTheDocument();
    expect(screen.getByText(/not a member of any course yet/)).toBeInTheDocument();
  });
});
