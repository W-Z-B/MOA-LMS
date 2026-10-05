import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { submission } from "../../test/marking";
import { FeedbackFiles } from "./FeedbackFiles";

/** A browser that can record: the microphone gives a stream, and the recorder hands back one piece of sound. */
class FakeRecorder {
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(["sound"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

describe("spoken feedback recorded in the page (item 2.24)", () => {
  it("records, plays the recording back, and returns it with the mark", async () => {
    const stop = vi.fn();
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) },
    });
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: () => "blob:take" });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const returned = submission({ feedback_files: [{ id: 9, filename: "spoken-feedback.webm", kind: "webm", is_audio: true, size: 5, download_url: "/api/v1/feedback-files/9/" }] });
    const { calls } = fakeServer({ "POST /submissions/21/feedback-files/": { status: 201, body: returned } });
    const onChanged = vi.fn();
    render(<FeedbackFiles submission={submission()} locked={false} onChanged={onChanged} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Record spoken feedback" }));
    await user.click(await screen.findByRole("button", { name: "Stop recording" }));
    expect(stop).toHaveBeenCalled();
    expect(screen.getByLabelText("The recording")).toHaveAttribute("src", "blob:take");
    await user.click(screen.getByRole("button", { name: "Return this recording" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledWith(returned));
    const sent = (calls[0].body as FormData).get("file") as File;
    expect(sent.name).toBe("spoken-feedback.webm");
  });

  it("asks for an upload when the microphone cannot be used", async () => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(<FeedbackFiles submission={submission()} locked={false} onChanged={vi.fn()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Record spoken feedback" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Record on your phone and upload the recording instead.");
  });
});
