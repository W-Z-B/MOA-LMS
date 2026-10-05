import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { course, page } from "../../test/staff";
import { Catalogue, CoursePage } from "./Catalogue";

const catalogue = page([
  course(),
  course({ site: 42, code: "SD-102", title: "First aid in the field", self_enrol: "approval", my_status: "completed", completed_on: "2026-10-05" }),
  course({ site: 43, code: "SD-103", title: "Leading a field day", self_enrol: "closed", length_hours: "1.0", audience: "" }),
]);

describe("the staff-development catalogue (item 5.02)", () => {
  it("lists the courses, searches by words, and narrows by how one joins and where one stands", async () => {
    const server = fakeServer({ "GET /staff-development/catalogue/": catalogue });
    const go = vi.fn();
    render(<Catalogue onNavigate={go} />);
    const list = await screen.findByRole("list", { name: "Courses" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("All farm staff · About 3 hours · Join at once");
    expect(within(list).getAllByRole("listitem")[2]).toHaveTextContent("About 1 hour · Course administrators enrol");
    expect(within(list).getByText("Completed")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("How to join"), "approval");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    await user.selectOptions(screen.getByLabelText("How to join"), "");
    await user.selectOptions(screen.getByLabelText("Show"), "new");
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector("a")?.textContent)).toEqual([
      "Safe use of farm machinery",
      "Leading a field day",
    ]);
    await user.selectOptions(screen.getByLabelText("Show"), "mine");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    await user.click(within(list).getByRole("link", { name: "First aid in the field" }));
    expect(go).toHaveBeenCalledWith("/learning/42");

    await user.type(screen.getByRole("searchbox", { name: "Words in the title or summary" }), "tractor");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(server.calls.at(-1)?.path).toBe("/staff-development/catalogue/?q=tractor");
  });

  it("says when nothing matches or the catalogue cannot be loaded", async () => {
    fakeServer({ "GET /staff-development/catalogue/": [page([]), { status: 403, body: { code: "permission_denied", detail: "The staff-development catalogue is for members of staff." } }] });
    const { unmount } = render(<Catalogue onNavigate={vi.fn()} />);
    expect(await screen.findByText("No course matches.")).toBeInTheDocument();
    unmount();
    render(<Catalogue onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("for members of staff");
  });
});

describe("a course page", () => {
  it("joins an open course at once, then opens it and shows progress", async () => {
    const server = fakeServer({
      "GET /staff-development/catalogue/41/": [{ body: course() }, { body: course({ my_status: "enrolled" }) }],
      "POST /staff-development/catalogue/41/join/": { status: 201, body: { outcome: "enrolled", request: null } },
      "GET /staff-development/catalogue/41/progress/": {
        body: { complete: false, completed_on: null, expires_on: null, rules: [{ code: "items", label: "Every item completed", met: false, done: 1, total: 2 }] },
      },
    });
    const go = vi.fn();
    render(<CoursePage site={41} onNavigate={go} />);
    expect(await screen.findByRole("heading", { name: "Safe use of farm machinery" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Why you want to take it/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Join the course" }));
    expect(await screen.findByRole("status")).toHaveTextContent("You are on the course.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "" });
    expect(await screen.findByRole("list", { name: "Completion rules" })).toHaveTextContent("Every item completed1 of 2");
    await userEvent.click(screen.getByRole("button", { name: "Open the course" }));
    expect(go).toHaveBeenCalledWith("/sites/41");
  });

  it("asks to join a course that needs approval, with a reason, and says when the request is refused", async () => {
    const server = fakeServer({
      "GET /staff-development/catalogue/42/": { body: course({ site: 42, self_enrol: "approval", places_left: 3, capacity: 10 }) },
      "POST /staff-development/catalogue/42/join/": [
        { status: 409, body: { code: "path_locked", detail: "Complete the course before it on the path first." } },
        { status: 201, body: { outcome: "requested", request: 8 } },
      ],
    });
    render(<CoursePage site={42} onNavigate={vi.fn()} />);
    expect(await screen.findByText("3")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Why you want to take it/), "I lead field days.");
    await userEvent.click(screen.getByRole("button", { name: "Ask to join" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Complete the course before it on the path first.");
    await userEvent.click(screen.getByRole("button", { name: "Ask to join" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your request has been sent.");
    expect(server.calls.filter((c) => c.method === "POST").at(-1)?.body).toEqual({ reason: "I lead field days." });
  });

  it("says why a course cannot be joined: full, or closed; and shows a completion with its dates", async () => {
    fakeServer({
      "GET /staff-development/catalogue/43/": { body: course({ site: 43, places_left: 0, capacity: 10 }) },
      "GET /staff-development/catalogue/44/": { body: course({ site: 44, self_enrol: "closed" }) },
      "GET /staff-development/catalogue/45/": { body: course({ site: 45, my_status: "completed", completed_on: "2026-10-05", expires_on: "2028-10-05" }) },
      "GET /staff-development/catalogue/45/progress/": { body: { complete: true, completed_on: "2026-10-05", expires_on: "2028-10-05", rules: [] } },
      "GET /staff-development/catalogue/46/": { status: 404, body: { code: "not_found", detail: "Not found." } },
    });
    const { unmount } = render(<CoursePage site={43} onNavigate={vi.fn()} />);
    expect(await screen.findByText(/The course is full/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /join/i })).not.toBeInTheDocument();
    unmount();
    const second = render(<CoursePage site={44} onNavigate={vi.fn()} />);
    expect(await screen.findByText(/not open to join/)).toBeInTheDocument();
    second.unmount();
    const third = render(<CoursePage site={45} onNavigate={vi.fn()} />);
    expect(await screen.findByText("Completed on 05/10/2026, valid until 05/10/2028")).toBeInTheDocument();
    expect(await screen.findByText(/A course administrator records when you have completed/)).toBeInTheDocument();
    third.unmount();
    render(<CoursePage site={46} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
