import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { MyGroup, SiteMember } from "../../api/types-talk";
import { fakeServer } from "../../test/fetch";
import { GroupsTab } from "./GroupsTab";

const group = (over: Partial<MyGroup> = {}): MyGroup => ({
  id: 4,
  name: "Lab group A",
  groupings: ["Lab groups"],
  member: false,
  self_sign_up: true,
  open: true,
  places_left: 2,
  closes_at: "2026-10-09T16:00:00Z",
  ...over,
});

const members: SiteMember[] = [
  { membership_id: 101, person_id: 21, external_id: "S2026901", name: "Kezia Persaud", role: "student" },
  { membership_id: 102, person_id: 22, external_id: "S2026902", name: "Tevin Joseph", role: "student" },
  { membership_id: 100, person_id: 30, external_id: "E0901", name: "Marlon Bacchus", role: "lecturer" },
];

describe("a student's groups (item 4.12)", () => {
  it("shows their groups and lets them join a self-sign-up group, then leave it", async () => {
    const { calls } = fakeServer({
      "GET /sites/9/my-groups/": [
        { body: [group({ id: 3, name: "Field group 1", member: true, self_sign_up: false, open: false, places_left: null, closes_at: null }), group()] },
        { body: [group({ member: true })] },
      ],
      "POST /groups/4/join/": { body: { group: 4, member: true } },
      "POST /groups/4/leave/": { status: 409, body: { code: "closed", detail: "Sign-up for this group has closed." } },
    });
    const user = userEvent.setup();
    render(<GroupsTab siteId={9} teaching={false} />);
    const mine = await screen.findByRole("list", { name: "My groups" });
    expect(mine).toHaveTextContent("Field group 1");
    const joinable = screen.getByRole("list", { name: "Groups you can join" });
    expect(joinable).toHaveTextContent("Lab groups · Sign-up open · 2 places left · closes");
    await user.click(within(joinable).getByRole("button", { name: "Join Lab group A" }));
    expect(calls.some((c) => c.path === "/groups/4/join/")).toBe(true);
    expect(await screen.findByText("You joined Lab group A.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-up for this group has closed.");
  });

  it("says when the student is in no group", async () => {
    fakeServer({ "GET /sites/9/my-groups/": { body: [] } });
    render(<GroupsTab siteId={9} teaching={false} />);
    expect(await screen.findByText("You are not in a group on this course.")).toBeInTheDocument();
  });
});

describe("teaching staff manage groups (item 4.12)", () => {
  function server(extra: Record<string, unknown> = {}) {
    return fakeServer({
      "GET /groups/": { body: { count: 1, next: null, previous: null, results: [{ id: 4, site: 9, name: "Lab group A", members: [101] }] } },
      "GET /sites/9/my-groups/": { body: [group({ member: false })] },
      "GET /groupings/": { body: { count: 1, next: null, previous: null, results: [{ id: 1, site: 9, name: "Lab groups", description: "", groups: [4] }] } },
      "GET /sites/9/members/": { body: members },
      ...(extra as Record<string, { body?: unknown }>),
    });
  }

  it("lists the groups with their members, and makes a group by hand", async () => {
    const { calls } = server({ "POST /groups/": { status: 201, body: { id: 5 } } });
    const user = userEvent.setup();
    render(<GroupsTab siteId={9} teaching />);
    const list = await screen.findByRole("list", { name: "Groups" });
    expect(list).toHaveTextContent("Lab group A");
    expect(list).toHaveTextContent("1 member · Lab groups · Self-sign-up open");
    expect(list).toHaveTextContent("Kezia Persaud");
    expect(screen.getByText("Lab group A", { selector: ".muted.small" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New group" }));
    await user.type(screen.getByLabelText("Name"), "Lab group B");
    // Only students are offered.
    expect(screen.queryByLabelText(/Marlon Bacchus/)).not.toBeInTheDocument();
    await user.click(screen.getByLabelText(/Tevin Joseph/));
    await user.click(screen.getByRole("button", { name: "Save group" }));
    expect(calls.find((c) => c.method === "POST" && c.path === "/groups/")?.body).toEqual({ site: 9, name: "Lab group B", members: [102] });
    expect(await screen.findByText("Lab group B is saved with 1 member.")).toBeInTheDocument();
  });

  it("changes a group's members", async () => {
    const { calls } = server({ "PATCH /groups/4/": { body: {} } });
    const user = userEvent.setup();
    render(<GroupsTab siteId={9} teaching />);
    await user.click(await screen.findByRole("button", { name: "Change Lab group A" }));
    await user.click(screen.getByLabelText(/Kezia Persaud/));
    await user.click(screen.getByLabelText(/Tevin Joseph/));
    await user.click(screen.getByRole("button", { name: "Save group" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Lab group A", members: [102] });
  });

  it("shares the students at random into a number of groups in a new set", async () => {
    const { calls } = server({ "POST /sites/9/allocate-groups/": { status: 201, body: { grouping: 2, groups: [{ name: "Field 1" }, { name: "Field 2" }] } } });
    const user = userEvent.setup();
    render(<GroupsTab siteId={9} teaching />);
    await user.click(await screen.findByRole("button", { name: "Share students at random" }));
    await user.clear(screen.getByLabelText("Number of groups"));
    await user.type(screen.getByLabelText("Number of groups"), "2");
    await user.clear(screen.getByLabelText("Name the groups"));
    await user.type(screen.getByLabelText("Name the groups"), "Field");
    await user.type(screen.getByLabelText(/Put them in a new set/), "Field groups");
    await user.click(screen.getByLabelText("Groups of at most this many"));
    expect(screen.getByLabelText("Students in a group")).toBeInTheDocument();
    await user.click(screen.getByLabelText("This many groups"));
    await user.click(screen.getByRole("button", { name: "Make the groups" }));
    expect(calls.find((c) => c.path === "/sites/9/allocate-groups/")?.body).toEqual({ groups: 2, prefix: "Field", grouping: "Field groups" });
    expect(await screen.findByText("2 groups made at random.")).toBeInTheDocument();
  });

  it("opens self-sign-up with a largest size and a closing time, and stops it", async () => {
    const { calls } = server({ "PUT /groups/4/sign-up/": { body: {} }, "DELETE /groups/4/sign-up/": { status: 204 } });
    const user = userEvent.setup();
    render(<GroupsTab siteId={9} teaching />);
    await user.click(await screen.findByRole("button", { name: "Sign-up for Lab group A" }));
    // Two places left with one member: a largest size of three.
    expect(screen.getByLabelText("Largest size (empty: no limit)")).toHaveValue(3);
    await user.clear(screen.getByLabelText("Largest size (empty: no limit)"));
    await user.type(screen.getByLabelText("Largest size (empty: no limit)"), "4");
    await user.click(screen.getByRole("button", { name: "Save sign-up" }));
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ is_open: true, max_size: 4 });
    expect(await screen.findByText("Students can now join Lab group A themselves.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sign-up for Lab group A" }));
    await user.click(screen.getByRole("button", { name: "Stop self-sign-up" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("makes a set of groups", async () => {
    const { calls } = server({ "POST /groupings/": { status: 201, body: {} } });
    const user = userEvent.setup();
    render(<GroupsTab siteId={9} teaching />);
    expect(await screen.findByRole("region", { name: "Sets of groups" })).toHaveTextContent("Lab groups Lab group A");
    await user.click(screen.getByRole("button", { name: "New set of groups" }));
    await user.type(screen.getByLabelText(/Name, such as/), "Field groups");
    await user.click(screen.getByRole("checkbox", { name: "Lab group A" }));
    await user.click(screen.getByRole("button", { name: "Save set" }));
    expect(calls.find((c) => c.path === "/groupings/" && c.method === "POST")?.body).toEqual({ site: 9, name: "Field groups", groups: [4] });
  });
});
