import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { VideoInfo } from "../../api/types-media";
import { fakeCaches } from "../../test/caches";
import { fakeServer } from "../../test/fetch";
import { ContentTab } from "../content/ContentTab";
import { asSite, contents, item, module } from "../content/fixtures";
import { setOfflineOwner } from "./offlineStore";

vi.mock("../content/maths", () => ({ drawMaths: () => Promise.resolve() }));

const video: VideoInfo = {
  status: "ready",
  status_label: "Ready",
  failure: null,
  duration_seconds: 90,
  qualities: [{ quality: "low", label: "Low (240p)", size: 3 * 1024 * 1024, width: 426, height: 240, bitrate_kbps: 280, url: "/api/v1/videos/15/play/low/" }],
  poster_url: "/api/v1/videos/15/poster/",
  poster_size: 20_000,
  captions: [],
  transcription: null,
  transcription_failure: null,
  can_transcribe: false,
};
const week = module(1, "Week 1: Soils", [item(15, 1, "Soil profiles", { kind: "video", body: "", file_size: 3 * 1024 * 1024, video })]);

describe("video and offline reading in the Content tab (items 4.03, 4.06)", () => {
  it("plays a video in the module and offers to keep the module offline", async () => {
    fakeCaches();
    await setOfflineOwner(3);
    fakeServer({});
    render(<ContentTab data={asSite(contents([week], "student"))} teaching={false} onChanged={vi.fn()} />);
    expect(await screen.findByRole("radio", { name: "Low (240p), 3 MB" })).toBeChecked();
    expect(document.querySelector("video")).toHaveAttribute("src", "/api/v1/videos/15/play/low/");
    expect(await screen.findByRole("button", { name: "Keep “Week 1: Soils” to read offline" })).toBeInTheDocument();
    await setOfflineOwner(null);
  });

  it("lets a lecturer put a video up once, with whose material it is", async () => {
    const { calls } = fakeServer({
      "GET /groups/": { body: { count: 0, next: null, previous: null, results: [] } },
      "POST /videos/": { status: 201, body: item(16, 1, "Field walk", { kind: "video", video: { ...video, status: "waiting", qualities: [] } }) },
    });
    const onChanged = vi.fn();
    render(<ContentTab data={asSite(contents([week]))} teaching onChanged={onChanged} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Put a video up" }));
    const form = screen.getByRole("button", { name: "Put the video up" }).closest("form")!;
    await user.type(within(form).getByLabelText("Title"), "Field walk");
    await user.upload(within(form).getByLabelText(/^Video/), new File(["mp4"], "walk.mp4", { type: "video/mp4" }));
    await user.selectOptions(within(form).getByLabelText("Whose material is this?"), "gsa_own");
    await user.click(within(form).getByRole("button", { name: "Put the video up" }));
    expect(await screen.findByText("Added “Field walk”.")).toBeInTheDocument();
    const sent = calls.find((c) => c.path === "/videos/")!.body as FormData;
    expect(sent.get("title")).toBe("Field walk");
    expect(sent.get("module")).toBe("1");
    expect((sent.get("file") as File).name).toBe("walk.mp4");
    expect(onChanged).toHaveBeenCalled();
  });

  it("says why a video could not be put up", async () => {
    fakeServer({
      "GET /groups/": { body: { count: 0, next: null, previous: null, results: [] } },
      "POST /videos/": { status: 400, body: { file: ["The video is larger than 1024 MB."] } },
    });
    render(<ContentTab data={asSite(contents([week]))} teaching onChanged={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Put a video up" }));
    const form = screen.getByRole("button", { name: "Put the video up" }).closest("form")!;
    await user.type(within(form).getByLabelText("Title"), "Big");
    await user.upload(within(form).getByLabelText(/^Video/), new File(["mp4"], "big.mp4", { type: "video/mp4" }));
    await user.selectOptions(within(form).getByLabelText("Whose material is this?"), "gsa_own");
    await user.click(within(form).getByRole("button", { name: "Put the video up" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("file: The video is larger than 1024 MB.");
  });
});
