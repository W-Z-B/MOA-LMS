import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { OpenCatalogue } from "../../api/types-assess";
import { assessAddress } from "../../app/router";
import { fakeServer } from "../../test/fetch";
import AssessmentAndAi from "./AssessmentAndAi";
import OpenCoursesPage, { OpenConfirmScreen, PublicOpenCourses } from "./OpenCourses";

const catalogue: OpenCatalogue = {
  courses: [
    { id: 30, code: "OPEN-POULTRY", title: "Backyard poultry keeping", summary: "Housing, feed and health.", audience: "Farmers", length_hours: "6", places_left: 4, joined: false, certificate: true },
    { id: 31, code: "OPEN-SEED", title: "Saving seed", summary: "", audience: "", length_hours: null, places_left: 0, joined: true, certificate: false },
  ],
  privacy_notice: { version: 2, title: "How the GSA LMS uses your personal data", body: "What we keep, and why." },
};

describe("open short courses (item 5.07)", () => {
  it("says plainly when GSA does not offer them", async () => {
    fakeServer({ "GET /open-courses/": { status: 404, body: { code: "open_courses_off", detail: "GSA does not offer open short courses at present." } } });
    render(<PublicOpenCourses />);
    expect(await screen.findByText("GSA does not offer open short courses at present.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Register" })).not.toBeInTheDocument();
  });

  it("lists the courses and registers with the privacy notice accepted", async () => {
    const { calls } = fakeServer({
      "GET /open-courses/": { body: catalogue },
      "POST /open-courses/register/": { status: 202, body: { detail: "Thank you. If the address can receive mail, a link to finish registering is on its way." } },
    });
    const user = userEvent.setup();
    render(<PublicOpenCourses />);
    expect(await screen.findByText("For farmers · about 6 hours · 4 places left · certificate on completion")).toBeInTheDocument();
    expect(screen.getByText("full")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Privacy notice" })).toHaveTextContent("What we keep, and why.");
    await user.type(screen.getByLabelText("First name"), "Sita");
    await user.type(screen.getByLabelText("Last name"), "Persaud");
    await user.type(screen.getByLabelText("Email address"), "sita@example.org");
    await user.selectOptions(screen.getByLabelText("Course to join"), "Backyard poultry keeping");
    expect(screen.queryByRole("option", { name: "Saving seed" })).not.toBeInTheDocument();
    await user.click(screen.getByLabelText(/I have read the privacy notice/));
    await user.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Follow the link in the email");
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      first_name: "Sita",
      last_name: "Persaud",
      email: "sita@example.org",
      site: 30,
      privacy_accepted: true,
    });
  });

  it("finishes registering from the emailed link", async () => {
    const onDone = vi.fn();
    fakeServer({
      "GET /open-courses/confirm/": { body: { email: "sita@example.org", first_name: "Sita", course: "Backyard poultry keeping" } },
      "POST /open-courses/confirm/": [
        { status: 400, body: { code: "weak_password", detail: "This password is too common." } },
        { status: 201, body: { detail: "Your account is ready.", username: "sita@example.org" } },
      ],
    });
    const user = userEvent.setup();
    render(<OpenConfirmScreen token="abc_DEF-123" onDone={onDone} />);
    expect(await screen.findByText(/you will be on Backyard poultry keeping/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Choose a password"), "Password12345");
    await user.type(screen.getByLabelText("The password again"), "Password1234");
    await user.click(screen.getByRole("button", { name: "Make my account" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The two passwords are not the same.");
    await user.type(screen.getByLabelText("The password again"), "5");
    await user.click(screen.getByRole("button", { name: "Make my account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This password is too common.");
    await user.click(screen.getByRole("button", { name: "Make my account" }));
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledWith("sita@example.org"));
  });

  it("says when the link has expired", async () => {
    fakeServer({ "GET /open-courses/confirm/": { status: 400, body: { code: "link_not_valid", detail: "This link has expired or has been used. Register again." } } });
    render(<OpenConfirmScreen token="old" onDone={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Register again.");
    expect(screen.getByRole("link", { name: "Register again" })).toHaveAttribute("href", "#/open-courses");
  });

  it("lets a signed-in learner join a course and download their certificates", async () => {
    const { calls } = fakeServer({
      "GET /open-courses/": [{ body: catalogue }, { body: { ...catalogue, courses: [{ ...catalogue.courses[0], joined: true }, catalogue.courses[1]] } }],
      "GET /certificates/": { body: { count: 1, next: null, previous: null, results: [{ id: 5, reference: "GSA/LMS/2026/0007", course: "Saving seed", issued_on: "2026-10-01", status: "valid" }] } },
      "POST /open-courses/30/join/": { body: catalogue.courses[0] },
    });
    const user = userEvent.setup();
    render(<OpenCoursesPage />);
    expect(await screen.findByRole("link", { name: "Saving seed" })).toHaveAttribute("href", "/api/v1/certificates/5/download/");
    expect(screen.getByRole("link", { name: "Open the course" })).toHaveAttribute("href", "#/sites/31");
    await user.click(screen.getByRole("button", { name: "Join" }));
    expect(calls.some((c) => c.path === "/open-courses/30/join/")).toBe(true);
    expect(await screen.findAllByRole("link", { name: "Open the course" })).toHaveLength(2);
  });

  it("says when joining is refused", async () => {
    fakeServer({
      "GET /open-courses/": { body: catalogue },
      "GET /certificates/": { body: { count: 0, next: null, previous: null, results: [] } },
      "POST /open-courses/30/join/": { status: 409, body: { code: "full", detail: "The course is full." } },
    });
    const user = userEvent.setup();
    render(<OpenCoursesPage />);
    await user.click(await screen.findByRole("button", { name: "Join" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The course is full.");
    expect(screen.getByText("A certificate is issued here when you complete a course.")).toBeInTheDocument();
  });
});

describe("addresses and the guidance (items 4.13, 5.07, 6.13)", () => {
  it("reads every address of its own", () => {
    expect(assessAddress("/sites/4/assignments/12/peer-review")).toEqual({ view: "peer-review", siteId: 4, assignmentId: 12 });
    expect(assessAddress("/sites/4/peer-reviews/33/")).toEqual({ view: "peer-work", siteId: 4, reviewId: 33 });
    expect(assessAddress("/open-courses")).toEqual({ view: "open-courses" });
    expect(assessAddress("/open-courses/confirm/a-B_9")).toEqual({ view: "open-confirm", token: "a-B_9" });
    expect(assessAddress("/help/assessment-and-ai")).toEqual({ view: "help-ai" });
    expect(assessAddress("/sites/4/assignments")).toBeNull();
  });

  it("explains the two lanes, declared use, why there is no detector and how to read a report", () => {
    render(<AssessmentAndAi />);
    for (const heading of ["The two-lane approach", "Declared AI use", "Why there is no AI detector", "The similarity check, and how to read it"])
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByText(/Overlap is evidence for a person to judge, not a verdict./)).toBeInTheDocument();
  });
});
