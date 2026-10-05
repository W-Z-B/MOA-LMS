# ADR 0015: Where video is kept, and how it is made light and captioned

**Status:** proposed (decision D3); not yet taken. The items it holds up (0.08, 2.20, 4.06, 4.07) wait for it.
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
