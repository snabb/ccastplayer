# ccastplayer

This is a simple CLI tool for streaming a video file to a Chromecast device.
It is implemented in Python and requires [PyChromecast](https://github.com/home-assistant-libs/pychromecast)
library for communicating with the Chromecast device.

This is somewhat similar to [Mkchromecast](https://mkchromecast.com/)
but simpler. The intention is to enable simple viewing of video files
on a Chromecast device from a Linux command line. It might work on
some other OSes too.

This script does not do any conversion. It expects the video file to already be
already in a [format that is accepted by the Chromecast device](https://developers.google.com/cast/docs/media).

There are no controls for playback. The assumption is that it is used
with "Chromecast with Google TV" type device that can be controlled
with a remote control. However playback can be gracefully stopped by
pressing Ctrl-C.

Subtitles can be supplied using a separate VTT file.

By default the first Chromecast device discovered on the local
network is used.

## Installation

Install from PyPI with `pip`:
```sh
pip install ccastplayer
```

Install from PyPI with `pipx`:
```sh
pipx install ccastplayer
```

Install from PyPI with `uv`:
```sh
uv tool install ccastplayer
```

Install directly from the GitHub repository:
```sh
pip install "ccastplayer @ git+https://github.com/snabb/ccastplayer.git"
pipx install git+https://github.com/snabb/ccastplayer.git
uv tool install git+https://github.com/snabb/ccastplayer.git
```

Example usage with a local video file:
```sh
ccastplayer myvideo.mp4
```

Example usage with a local video and subtitles file:
```sh
ccastplayer myvideo.mp4 --subs mysubs.vtt
```

Example usage with a remote video file:
```sh
ccastplayer http://example.org/videos/myvideo.mp4
```

If the script is unable to auto-discover the device in your local network,
you can supply the IP address with the `--chromecast-ip` option:
```sh
ccastplayer --chromecast-ip 192.0.2.123 example.mkv
```

More help on command line options:
```sh
ccastplayer --help
```

Run the test suite with:
```
python3 -m unittest discover -s tests -v
```
