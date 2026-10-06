import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Tool } from "../../api/types-connect";
import { fakeServer } from "../../test/fetch";
import ToolsAdminScreen from "./ToolsAdminScreen";

const tool: Tool = {
  id: 3,
  name: "Crop simulator",
  description: "Grows a crop through a season.",
  client_id: "ab12",
  deployment_id: "1",
  oidc_login_url: "https://sim.example/login",
  launch_url: "https://sim.example/launch",
  deep_linking_url: "https://sim.example/choose",
  redirect_urls: [],
  jwks_url: "https://sim.example/jwks",
  public_key: "",
  share_name: false,
  share_email: false,
  grades: true,
  class_list: false,
  is_active: true,
  receives: ["An identifier for each person that means nothing outside this tool"],
  can_choose_content: true,
};

const platform = {
  issuer: "https://lms.gsa.example",
  jwks_url: "https://lms.gsa.example/api/lti/jwks/",
  auth_url: "https://lms.gsa.example/api/lti/auth/",
  token_url: "https://lms.gsa.example/api/lti/token/",
  deep_link_return_url: "https://lms.gsa.example/api/lti/deep-links/",
  launch_start: "",
};

const page = (results: Tool[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("outside tools for course administrators (item 6.07)", () => {
  it("lists the tools with what each receives and the LMS's details for makers, and switches names on", async () => {
    const { calls } = fakeServer({
      "GET /tools/": page([tool]),
      "GET /lti/platform/": { body: platform },
      "PATCH /tools/3/": [
        { body: { ...tool, share_name: true, receives: [...tool.receives, "Each person's name"] } },
        { status: 400, body: { code: "invalid", detail: "Could not." } },
      ],
    });
    const user = userEvent.setup();
    render(<ToolsAdminScreen />);
    const card = (await screen.findByRole("heading", { name: "Crop simulator" })).closest("li")!;
    expect(card).toHaveTextContent("ab12");
    expect(card).toHaveTextContent("https://sim.example/choose");
    expect(within(card).getByLabelText("Send people's names")).not.toBeChecked();
    expect(await screen.findByText("https://lms.gsa.example/api/lti/jwks/")).toBeInTheDocument();
    await user.click(within(card).getByLabelText("Send people's names"));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ share_name: true });
    expect(await within(card).findByText("Each person's name")).toBeInTheDocument();
    expect(within(card).getByRole("status")).toHaveTextContent("Send people's names: on.");
    await user.click(within(card).getByLabelText("Read class lists"));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Could not.");
  });

  it("registers a tool, and shows the server's reason when it is refused", async () => {
    const { calls } = fakeServer({
      "GET /tools/": [page([]), page([{ ...tool, is_active: false, jwks_url: "", public_key: "PEM" }])],
      "GET /lti/platform/": { status: 403, body: { detail: "No." } },
      "POST /tools/": [{ status: 400, body: { jwks_url: ["Give the tool's key set address, or paste its public key."] } }, { status: 201, body: tool }],
    });
    const user = userEvent.setup();
    render(<ToolsAdminScreen />);
    expect(await screen.findByText("No tools are registered yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Register a tool" }));
    const form = screen.getByRole("form", { name: "Register a tool" });
    await user.type(within(form).getByLabelText("Name"), "Crop simulator");
    await user.type(within(form).getByLabelText(/Login initiation address/), "https://sim.example/login");
    await user.type(within(form).getByLabelText(/Launch address/), "https://sim.example/launch");
    await user.click(within(form).getByRole("button", { name: "Register" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("jwks url: Give the tool's key set address");
    await user.type(within(form).getByLabelText(/Key set address/), "https://sim.example/jwks");
    await user.click(within(form).getByRole("button", { name: "Register" }));
    const card = (await screen.findByRole("heading", { name: /Crop simulator/ })).closest("li")!;
    expect(card).toHaveTextContent("Switched off");
    expect(card).toHaveTextContent("Public key pasted in");
    expect(calls.filter((c) => c.method === "POST").at(-1)?.body).toMatchObject({ name: "Crop simulator", jwks_url: "https://sim.example/jwks" });
    expect(screen.queryByRole("form", { name: "Register a tool" })).not.toBeInTheDocument();
  });

  it("can leave the form, and says when the tools cannot be read", async () => {
    fakeServer({ "GET /tools/": { status: 500, body: { detail: "Down" } }, "GET /lti/platform/": { body: platform } });
    const user = userEvent.setup();
    render(<ToolsAdminScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Down");
    await user.click(screen.getByRole("button", { name: "Register a tool" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Register a tool" })).toBeInTheDocument();
  });
});
