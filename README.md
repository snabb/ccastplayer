# ccastplayer

This is a simple CLI tool for streaming video file to Chromecast device.
It is implemented in Python and requires [PyChromecast](https://github.com/home-assistant-libs/pychromecast)
library for communicating with the Chromecast device.

This is somewhat similar to [Mkchromecast](https://mkchromecast.com/)
but simpler. The intention is to enable simple viewing of video files
on a Chromecast device from a Linux command line. It might work on
some other OSes too.

This script does not do any conversion. It expects the video file to be
already in a [format that is accepted by the Chromecast device](https://developers.google.com/cast/docs/media).

There are no controls for playback. The assumption is that it is used
with "Chromecast with Google TV" type device that can be controlled
with a remote control. However playback can be gracefully stopped by
pressing Ctrl-C.

Subtitles can be supplied using a separate VTT file.

By default the first Chromecast device discovered on the local
network is used.

Example usage with a local video file:
```
ccastplayer.py myvideo.mp4
```

Example usage with a local video and subtitles file:
```
ccastplayer.py myvideo.mp4 --subs mysubs.vtt
```

Example usage with a remote video file:
```
ccastplayer.py http://example.org/videos/myvideo.mp4
```

More help on command line options:
```
ccastplayer.py --help
```
