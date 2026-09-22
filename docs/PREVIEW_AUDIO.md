# Preview audio

TubeClipper 1.2.0 supports audio during editing for both kinds of YouTube
delivery:

- Combined streams, where one URL contains the video and audio tracks.
- Adaptive streams, where YouTube provides separate video and audio URLs.

For adaptive streams, TubeClipper uses the video clock as the source of truth
and keeps a second audio player synchronized with it. Play, pause, seeking,
frame stepping, playback speed, and the volume slider apply to both players.

## If the preview is silent

1. Raise the volume slider at the bottom-right of the preview.
2. Check the system volume mixer and confirm that TubeClipper is not muted.
3. Confirm that the correct speakers or headphones are selected in Windows or
   macOS.
4. Reload the video after changing the system audio output device.
5. For age-restricted, members-only, or signed-in videos, select the appropriate
   browser in TubeClipper's cookie preferences and load the link again.

Preview playback and export are separate. A temporary preview playback problem
does not remove audio from an exported clip. Exports are created directly by
FFmpeg from the selected source tracks.
