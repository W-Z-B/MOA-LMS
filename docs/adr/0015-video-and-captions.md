# ADR 0015: Where video is kept, and how it is made light and captioned

**Status:** accepted on the recommended answer, 6 October 2026 (decision D3); GSA may revise. Items 4.06
and 4.07 are built on it (note below); 0.08 and 2.20 already were.
**Date:** 5 October 2026.

## Context

Students pay for data, and a deaf student needs captions. Video sent to a foreign platform is a transfer of
personal data abroad when it shows students. The usual conversion tool, FFmpeg, is LGPL and would run as a
separate program, which the licence policy must name.

## Recommended answer

1. Keep video in the LMS's own file store, with an allowance of storage per site.
2. Convert on upload to a low (about 240p) and a standard copy, and an audio-only copy (items 4.06, 4.07),
   with FFmpeg run as a separate program, named in ADR 0002 when this is taken.
3. Caption with a speech-to-text model (Whisper, MIT) on GSA's own server; the lecturer corrects the text.

## Consequences if taken

- Conversion and captioning need server capacity, sized when GSA answers on hosting (decision D9).
- No video or caption text leaves GSA's server.

## Note on what was built, 6 October 2026 (items 4.06, 4.07)

- **Put up once.** A lecturer puts a video up at `POST /api/v1/videos/` (MP4, MOV, WebM, MKV or 3GP, at most
  `UPLOAD_LIMIT_VIDEO_MB`, 1024 MB by default; Caddy allows that one address a body of 1100 MB). It becomes a
  content item of kind `video`, with the item's licence, release conditions and draft state. The original
  counts against the site's storage allowance at once.
- **Prepared by the job worker** (`video.convert`, Procrastinate queue `video`), never in a request:
  a low copy (at most 240 lines, H.264 at 250 kbit/s with mono AAC at 48 kbit/s), a standard copy (at most
  `VIDEO_STANDARD_HEIGHT`, 480 by default, 900 kbit/s with AAC at 96 kbit/s), a sound-only copy (AAC at
  64 kbit/s, mono: under the 128 kbit/s of item 4.07) and a poster frame. No copy is taller than the original.
  The original is then removed unless `VIDEO_KEEP_ORIGINAL` is set, and the item's size becomes the sum of
  what is kept, so the allowance counts every copy. A file the converter cannot read fails in words, and the
  lecturer can ask again. The lecturer is told when it is ready.
- **FFmpeg** is built in `api/Dockerfile` from Debian's own source package with LGPL components only
  (`--disable-autodetect`, no network protocols, no devices); H.264 comes from OpenH264 (BSD-2-Clause),
  AAC, JPEG and WAV from FFmpeg's own encoders. The build stops if FFmpeg does not say it is LGPL or was
  configured with GPL, non-free or version-3 parts, and the licence gate checks the same in the image
  (`scripts/check_licences.py`, "programs"). It is a named program under ADR 0002, point 6, in
  `scripts/licence-policy.json`. Debian's own `ffmpeg` package is built with `--enable-gpl` and is not used.
  The hosted single-container image (`deploy/railway/Dockerfile`) does not carry FFmpeg yet: there a video
  stays "could not be prepared: the video converter is not installed" until it does.
- **Image size.** The production API image (`docker build ./api`) grew from 488 MB to 560 MB: FFmpeg and
  FFprobe 33 MB, OpenH264 1 MB, and the push-notice packages (item 4.04) 17 MB, the rest being layers.
- **Played** at `GET /api/v1/videos/{item}/play/{low|standard|audio}/`, with Range requests so a player
  seeks without fetching the whole file, under the same rules as the item. The student chooses the quality,
  each shown with its size; phones in data-light mode (item 4.05) start on the low copy and fetch nothing,
  not even the poster, until Play.
- **Captions** are WebVTT text kept per language: put up as a file, or written and corrected cue by cue in
  the browser (`#/sites/{id}/videos/{item}/captions`). Markup in cue text is reduced to plain text.
- **Speech recognition** is whisper.cpp (MIT), installed by GSA on its own server and named in
  `VIDEO_TRANSCRIBE_COMMAND`. Off while that setting is empty, which is the default: it needs GSA's answer
  on hosting (D9) for the server capacity. When on, the job worker takes the sound with the LMS's FFmpeg
  (16 kHz, mono), runs the command with `-l <language> -f <file> -ovtt -of <name>`, and keeps the captions as
  "automatic" for the lecturer to correct. Nothing is sent to an outside service.
- Copying a course to a new term, or duplicating the item, stores every copy again.
