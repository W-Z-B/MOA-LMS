import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeServer } from "../../test/fetch";
import { certificate, courseAdmin, page, staff } from "../../test/staff";
import { Certificates } from "./Certificates";

describe("certificates (items 5.08 to 5.11)", () => {
  it("lists my own, each to download, with the way to check one, and offers no withdrawal", async () => {
    fakeServer({ "GET /certificates/": page([certificate(), certificate({ id: 10, status: "withdrawn", withdrawal_reason: "Issued to the wrong person." })]) });
    render(<Certificates me={staff} />);
    expect(screen.getByRole("heading", { name: "My certificates" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Certificates" });
    const [valid, gone] = within(list).getAllByRole("listitem");
    expect(valid).toHaveTextContent("GSA/LMS/2026/0001 · completed 05/10/2026 · valid until 05/10/2028");
    expect(valid).not.toHaveTextContent("Marlon Bacchus");
    expect(within(valid).getByRole("link", { name: "Download (PDF): GSA/LMS/2026/0001" })).toHaveAttribute("href", "/api/v1/certificates/9/download/");
    expect(within(gone).queryByRole("link")).not.toBeInTheDocument();
    expect(gone).toHaveTextContent("Withdrawn: Issued to the wrong person.");
    expect(screen.queryByRole("button", { name: /Withdraw/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "the certificate check page" })).toHaveAttribute("href", "/api/check-certificate/");
  });

  it("lets a course administrator see whose each is and withdraw one issued in error, saying why", async () => {
    const server = fakeServer({
      "GET /certificates/": [page([certificate()]), page([certificate({ status: "withdrawn", withdrawal_reason: "Wrong course." })])],
      "POST /certificates/9/withdraw/": { body: certificate({ status: "withdrawn" }) },
    });
    render(<Certificates me={courseAdmin} />);
    expect(screen.getByRole("heading", { name: "Certificates issued" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Certificates" });
    expect(list).toHaveTextContent("Marlon Bacchus");
    await userEvent.click(within(list).getByRole("button", { name: "Withdraw GSA/LMS/2026/0001" }));
    await userEvent.click(within(list).getByRole("button", { name: "Keep it" }));
    await userEvent.click(within(list).getByRole("button", { name: "Withdraw GSA/LMS/2026/0001" }));
    await userEvent.type(within(list).getByLabelText("Why it was issued in error"), "Wrong course.");
    await userEvent.click(within(list).getByRole("button", { name: "Withdraw GSA/LMS/2026/0001" }));
    expect(await screen.findByRole("status")).toHaveTextContent("GSA/LMS/2026/0001 is withdrawn.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "Wrong course." });
    expect(await screen.findByText("Withdrawn: Wrong course.")).toBeInTheDocument();
  });

  it("says when there are none yet", async () => {
    fakeServer({ "GET /certificates/": page([]) });
    render(<Certificates me={staff} />);
    expect(await screen.findByText(/No certificates yet/)).toBeInTheDocument();
  });
});
