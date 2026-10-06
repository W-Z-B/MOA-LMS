/**
 * Types for lecture video, offline reading and push notices (api/video, api/notifications; items 4.03 to
 * 4.07). They mirror video/serializers.py, video/offline.py and notifications/api.py; keep them in step
 * with /api/docs.
 */

export type VideoQuality = "low" | "standard" | "audio";

export interface VideoCopy {
  quality: VideoQuality;
  /** "Low (240p)", "Standard (480p)", "Sound only". */
  label: string;
  size: number;
  width: number | null;
  height: number | null;
  bitrate_kbps: number | null;
  url: string;
}

export interface CaptionInfo {
  language: string;
  label: string;
  source: "uploaded" | "edited" | "transcribed";
  url: string;
}

export interface VideoInfo {
  status: "waiting" | "converting" | "ready" | "failed";
  status_label: string;
  /** Why it could not be prepared; teaching staff only. */
  failure: string | null;
  duration_seconds: number | null;
  /** Lowest first: phones play the first. */
  qualities: VideoCopy[];
  poster_url: string | null;
  poster_size: number;
  captions: CaptionInfo[];
  /** Automatic captions; teaching staff only. */
  transcription: "none" | "waiting" | "working" | "done" | "failed" | null;
  transcription_failure: string | null;
  can_transcribe: boolean;
}

export interface Cue {
  start: number;
  end: number;
  text: string;
}

export interface Cues {
  label: string;
  cues: Cue[];
}

export interface PushState {
  available: boolean;
  public_key: string | null;
  devices: number;
}

/** 75 -> "1:15"; 3725 -> "1:02:05". */
export function clock(seconds: number): string {
  const whole = Math.max(Math.floor(seconds), 0);
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = String(whole % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
