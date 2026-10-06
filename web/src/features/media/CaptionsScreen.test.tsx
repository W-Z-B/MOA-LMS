import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { VideoInfo } from "../../api/types-media";
import { fakeServer } from "../../test/fetch";
import { item } from "../content/fixtures";
import CaptionsScreen from "./CaptionsScreen";

const video: VideoInfo = {
  status: "ready",
  status_label: "Ready",
  failure: null,
  duration_seconds: 60,
  qualities: [{ quality: "low", label: "Low (240p)", size: 1000, width: 426, height: 240, bitrate_kbps: 200, url: "/api/v1/videos/12/play/low/" }],
  poster_url: null,
  poster_size: 0,
  captions: [{ language: "en", label: "English", source: "transcribed", url: "/api/v1/videos/12/captions/en/" }],
  transcription: "none",
  transcription_failure: null,
  can_transcribe: true,
};
const lecture = (more: Partial<VideoInfo> = {}) => item(12, 1, "Soil profiles", { kind: "video", body: "", video: { ...video, ...more } });
const cues = { label: "English", cues: [{ start: 0, end: 2.5, text: "Welcome to soils." }] };

describe("captions for a lecture video (item 4.06)", () => {
  it("corrects the captions cue by cue and saves them", async () => {
    const { calls } = fakeServer({
      "GET /content/12/": { body: lecture() },
      "GET /videos/12/captions/en/cues/": { body: cues },
      "PUT /videos/12/captions/en/cues/": { body: { label: "English", cues: [{ start: 0, end: 2.5, text: "Welcome to soil science." }] } },
    });
    render(<CaptionsScreen siteId={9} itemId={12} />);
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Captions: Soil profiles", level: 1 })).toBeInTheDocument();
    const text = await screen.findByRole("textbox", { name: "Caption 1" });
    expect(text).toHaveValue("Welcome to soils.");
    expect(screen.getByText("0:00 to 0:02")).toBeInTheDocument();
    await user.clear(text);
    await user.type(text, "Welcome to soil science.");
    await user.click(screen.getByRole("button", { name: /Add a caption at this point/ }));
    expect(screen.getAllByRole("textbox", { name: /^Caption \d$/ })).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Remove caption 2" }));
    await user.click(screen.getByRole("button", { name: "Save captions" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved the English captions.");
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({
      label: "English",
      cues: [{ start: 0, end: 2.5, text: "Welcome to soil science." }],
    });
  });

  it("puts a captions file up in another language, and removes captions", async () => {
    const { calls } = fakeServer({
      "GET /content/12/": { body: lecture() },
      "GET /videos/12/captions/en/cues/": { body: cues },
      "GET /videos/12/captions/es/cues/": [
        { status: 404, body: { code: "not_found", detail: "Not found." } },
        { body: { label: "Spanish", cues: [{ start: 1, end: 2, text: "Hola" }] } },
      ],
      "POST /videos/12/captions/": { status: 201, body: video },
      "DELETE /videos/12/captions/en/": { status: 204 },
    });
    render(<CaptionsScreen siteId={9} itemId={12} />);
    const user = userEvent.setup();
    await screen.findByRole("textbox", { name: "Caption 1" });
    await user.click(screen.getByRole("button", { name: "Remove these captions" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Removed the English captions.");
    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "es");
    expect(await screen.findByText("No captions in this language yet.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Name in the player" })).toHaveValue("Spanish");
    const file = new File(["WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHola\n"], "es.vtt", { type: "text/vtt" });
    const form = screen.getByRole("form", { name: "Put up a captions file" });
    await user.upload(within(form).getByLabelText("WebVTT file (.vtt)"), file);
    await user.click(within(form).getByRole("button", { name: "Put the file up" }));
    expect(await screen.findByText("Put up es.vtt as the Spanish captions.")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST")!.body as FormData;
    expect(sent.get("language")).toBe("es");
    expect(await screen.findByRole("textbox", { name: "Caption 1" })).toHaveValue("Hola");
  });

  it("asks GSA's server to write them, and says when it could not", async () => {
    const { calls } = fakeServer({
      "GET /content/12/": [{ body: lecture({ transcription: "failed", transcription_failure: "Speech recognition did not finish." }) }, { body: lecture({ transcription: "waiting" }) }],
      "GET /videos/12/captions/en/cues/": { body: cues },
      "POST /videos/12/transcribe/": { status: 202, body: video },
    });
    render(<CaptionsScreen siteId={9} itemId={12} />);
    const user = userEvent.setup();
    expect(await screen.findByText("Speech recognition did not finish.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Write English captions automatically" }));
    expect(calls.find((c) => c.path === "/videos/12/transcribe/")!.body).toEqual({ language: "en" });
    expect(await screen.findByText("Being written. Come back in a few minutes.")).toBeInTheDocument();
  });

  it("says when the video cannot be opened, or saving is refused", async () => {
    fakeServer({ "GET /content/12/": { status: 404, body: { code: "not_found", detail: "Not found." } }, "GET /videos/12/captions/en/cues/": { body: cues } });
    render(<CaptionsScreen siteId={9} itemId={12} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });

  it("shows the server's reason when the captions are refused", async () => {
    fakeServer({
      "GET /content/12/": { body: lecture({ can_transcribe: false }) },
      "GET /videos/12/captions/en/cues/": { body: cues },
      "PUT /videos/12/captions/en/cues/": { status: 400, body: { cues: ["A cue must end after it starts (00:00:04.000)."] } },
    });
    render(<CaptionsScreen siteId={9} itemId={12} />);
    const user = userEvent.setup();
    await screen.findByRole("textbox", { name: "Caption 1" });
    expect(screen.queryByRole("heading", { name: "Write them automatically" })).not.toBeInTheDocument();
    await user.clear(screen.getByRole("spinbutton", { name: "From (seconds)" }));
    await user.type(screen.getByRole("spinbutton", { name: "From (seconds)" }), "4");
    await user.click(screen.getByRole("button", { name: "Save captions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A cue must end after it starts");
  });
});
