import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fakeCaches } from "../../test/caches";
import { fakeServer } from "../../test/fetch";
import DownloadsScreen from "./DownloadsScreen";
import ModuleDownload from "./ModuleDownload";
import { setOfflineOwner, type OfflineManifest } from "./offlineStore";
import { isDataLight, setDataLight } from "./dataLight";

const MB = 1024 * 1024;
const weekOne: OfflineManifest = {
  module: 1,
  title: "Week 1: Soils",
  site: 9,
  site_title: "Introduction to Crop Production",
  files: [
    { url: "/auth/me/", kind: "data", title: "Who is signed in", size: 4096 },
    { url: "/content/11/", kind: "page", title: "Soil texture", size: 6000 },
    { url: "/content/14/download/", kind: "document", title: "Handout", size: 2 * MB },
    { url: "/videos/12/play/low/", kind: "video", title: "Soil profiles", size: 9 * MB },
  ],
  total_bytes: 11 * MB + 10096,
  left_out: ["Ministry guide"],
};

const files = {
  "GET /offline/modules/1/": { body: weekOne },
  "GET /auth/me/": { body: { id: 7 } },
  "GET /content/11/": { body: { id: 11 } },
  "GET /content/14/download/": { body: "pdf" },
  "GET /videos/12/play/low/": { body: "video" },
};

describe("keeping a module to read offline (item 4.03)", () => {
  beforeEach(async () => {
    fakeCaches();
    await setOfflineOwner(7);
  });
  afterEach(() => setOfflineOwner(null));

  it("shows the space it will take first, then keeps it and offers to remove it", async () => {
    const { calls } = fakeServer(files);
    render(<ModuleDownload moduleId={1} title="Week 1: Soils" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Keep “Week 1: Soils” to read offline" }));
    const confirm = await screen.findByRole("group", { name: "Keep “Week 1: Soils” to read offline" });
    expect(confirm).toHaveTextContent("This keeps 11 MB on this device: 1 page, 1 document or picture and 1 video at low quality.");
    expect(confirm).toHaveTextContent("Not kept, as they need a connection: Ministry guide.");
    expect(calls.filter((c) => c.path.includes("offline=1"))).toHaveLength(0); // nothing kept yet
    await user.click(within(confirm).getByRole("button", { name: "Keep it" }));
    expect(await screen.findByText("Kept offline")).toBeInTheDocument();
    expect(calls.filter((c) => c.path.includes("offline=1"))).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "Remove “Week 1: Soils” from this device" }));
    expect(await screen.findByRole("button", { name: "Keep “Week 1: Soils” to read offline" })).toBeInTheDocument();
  });

  it("can be cancelled, and says when the module cannot be kept", async () => {
    fakeServer({ ...files, "GET /videos/12/play/low/": { status: 500, body: {} } });
    render(<ModuleDownload moduleId={1} title="Week 1: Soils" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Keep “Week 1: Soils”/ }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: /Keep “Week 1: Soils”/ }));
    await user.click(await screen.findByRole("button", { name: "Keep it" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("“Soil profiles” could not be fetched. Try again later.");
  });

  it("says when the server cannot be asked", async () => {
    fakeServer({ "GET /offline/modules/1/": { status: 404, body: { code: "not_found", detail: "No such module." } } });
    render(<ModuleDownload moduleId={1} title="Week 1: Soils" />);
    await userEvent.click(await screen.findByRole("button", { name: /Keep “Week 1: Soils”/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No such module.");
  });

  it("lists what is kept under Downloaded, with its size, and removes it", async () => {
    fakeServer(files);
    render(<ModuleDownload moduleId={1} title="Week 1: Soils" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Keep “Week 1: Soils”/ }));
    await user.click(await screen.findByRole("button", { name: "Keep it" }));
    await screen.findByText("Kept offline");
    render(<DownloadsScreen />);
    const kept = await screen.findByRole("link", { name: "Week 1: Soils" });
    expect(kept).toHaveAttribute("href", "#/sites/9");
    expect(screen.getByText(/Introduction to Crop Production ·/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove “Week 1: Soils”" }));
    expect(await screen.findByText("Removed “Week 1: Soils” from this device.")).toBeInTheDocument();
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
  });

  it("sets data-light mode for this device", async () => {
    render(<DownloadsScreen />);
    const user = userEvent.setup();
    expect(screen.getByRole("radio", { name: /As the device suggests/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Always on" }));
    expect(isDataLight()).toBe(true);
    expect(screen.getByText(/It is on on this device now/)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Off" }));
    expect(isDataLight()).toBe(false);
    await user.click(screen.getByRole("radio", { name: /As the device suggests/ }));
    setDataLight(null);
  });
});

describe("a browser that cannot keep files", () => {
  it("offers nothing to keep", () => {
    render(<ModuleDownload moduleId={1} title="Week 1" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    render(<DownloadsScreen />);
    expect(screen.getByText("This browser cannot keep modules offline.")).toBeInTheDocument();
  });
});
