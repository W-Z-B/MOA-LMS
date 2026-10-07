import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VideoInfo } from "../../api/types-media";
import { fakeServer } from "../../test/fetch";
import { DocumentView } from "../content/PageBody";
import { item } from "../content/fixtures";
import { setDataLight } from "./dataLight";
import VideoItem from "./VideoItem";

const MB = 1024 * 1024;
const ready: VideoInfo = {
  status: "ready",
  status_label: "Ready",
  failure: null,
  duration_seconds: 754,
  qualities: [
    { quality: "low", label: "Low (240p)", size: 9 * MB, width: 426, height: 240, bitrate_kbps: 300, url: "/api/v1/videos/12/play/low/" },
    { quality: "standard", label: "Standard (480p)", size: 40 * MB, width: 854, height: 480, bitrate_kbps: 1000, url: "/api/v1/videos/12/play/standard/" },
    { quality: "audio", label: "Sound only", size: 6 * MB, width: null, height: null, bitrate_kbps: 64, url: "/api/v1/videos/12/play/audio/" },
  ],
  poster_url: "/api/v1/videos/12/poster/",
  poster_size: 30_000,
  captions: [{ language: "en", label: "English", source: "edited", url: "/api/v1/videos/12/captions/en/" }],
  transcription: null,
  transcription_failure: null,
  can_transcribe: false,
};
const lecture = (video: VideoInfo) => item(12, 1, "Soil profiles", { kind: "video", body: "", video });

describe("a lecture video in the course (items 4.06, 4.07)", () => {
  afterEach(() => setDataLight(null));

  it("plays the standard copy with its poster and captions, and the student chooses another quality", async () => {
    setDataLight(false);
    render(<VideoItem item={lecture(ready)} siteId={9} teaching={false} />);
    const player = document.querySelector("video")!;
    expect(player).toHaveAttribute("src", "/api/v1/videos/12/play/standard/");
    expect(player).toHaveAttribute("poster", "/api/v1/videos/12/poster/");
    expect(player).toHaveAttribute("preload", "metadata");
    expect(player.querySelector("track")).toHaveAttribute("src", "/api/v1/videos/12/captions/en/");
    expect(screen.getByRole("group", { name: "Quality (12:34 long)" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Standard (480p), 40 MB" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Sound only, 6 MB" }));
    expect(document.querySelector("audio")).toHaveAttribute("src", "/api/v1/videos/12/play/audio/");
    expect(localStorage.getItem("gsa-lms.video-quality")).toBe("audio");
    expect(screen.queryByRole("link", { name: "Captions" })).not.toBeInTheDocument();
  });

  it("chooses the low copy in data-light mode and fetches nothing until Play", () => {
    setDataLight(true);
    render(<VideoItem item={lecture({ ...ready, captions: [] })} siteId={9} teaching />);
    const player = document.querySelector("video")!;
    expect(player).toHaveAttribute("src", "/api/v1/videos/12/play/low/");
    expect(player).not.toHaveAttribute("poster");
    expect(player).toHaveAttribute("preload", "none");
    expect(screen.getByText("No captions yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Captions" })).toHaveAttribute("href", "#/sites/9/videos/12/captions");
  });

  it("says when it is being prepared, and lets teaching staff ask again when it failed", async () => {
    const { calls } = fakeServer({ "POST /videos/12/convert/": { status: 202, body: { ...ready, status: "waiting", qualities: [] } } });
    const { rerender } = render(<VideoItem item={lecture({ ...ready, status: "converting", qualities: [] })} siteId={9} teaching={false} />);
    expect(screen.getByRole("status")).toHaveTextContent("Being prepared for phones");
    rerender(<VideoItem key="failed" item={lecture({ ...ready, status: "failed", failure: "The video converter is not installed." })} siteId={9} teaching />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be prepared. The video converter is not installed.");
    await userEvent.click(screen.getByRole("button", { name: "Prepare it again" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/videos/12/convert/")).toBe(true);
    expect(await screen.findByRole("status")).toHaveTextContent("Being prepared");
    rerender(<VideoItem key="student" item={lecture({ ...ready, status: "failed", failure: null })} siteId={9} teaching={false} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This video is not ready yet.");
  });

  it("checks again while the video is being prepared", async () => {
    vi.useFakeTimers();
    try {
      const { calls } = fakeServer({ "GET /videos/12/": { body: ready } });
      render(<VideoItem item={lecture({ ...ready, status: "waiting", qualities: [] })} siteId={9} teaching={false} />);
      await vi.advanceTimersByTimeAsync(20_000);
      expect(calls.filter((c) => c.path === "/videos/12/")).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
    expect(await screen.findByRole("radio", { name: "Standard (480p), 40 MB" })).toBeChecked();
  });

  it("holds a large photograph back in data-light mode and says the size of the download", async () => {
    setDataLight(true);
    render(<DocumentView title="Soil map" filename="map.jpg" url="/api/v1/content/5/download/" size={3 * MB} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download map.jpg (3 MB)" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show the picture (3 MB)" }));
    expect(screen.getByRole("img", { name: "Soil map" })).toBeInTheDocument();
  });
});
