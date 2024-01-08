#!/usr/bin/python3
#
# SPDX-License-Identifier: MIT
#
# Copyright (c) 2023-2024 Janne Snabb <snabb at epipe.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""A script for streaming a local or remote video file to Chromecast device."""

import argparse
from collections import namedtuple
from datetime import timedelta
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPStatus
import logging
import math
import mimetypes
import os
import re
import socketserver
import sys
import threading
from threading import Event
import time
from urllib.parse import urljoin

import pychromecast
from pychromecast.controllers.media import MediaStatus, MediaStatusListener


class MyMediaStatusListener(
    MediaStatusListener
):  # pylint: disable=too-few-public-methods
    """Class that receives media status reports and emits status line to
    terminal."""

    def new_media_status(self, status: MediaStatus):
        if status.adjusted_current_time is not None:
            current_time = str(
                timedelta(seconds=math.floor(status.adjusted_current_time))
            )
        else:
            current_time = "-:--:--"

        if status.duration is not None:
            duration = str(timedelta(seconds=math.floor(status.duration)))
        else:
            duration = "-:--:--"

        # Refresh status line on terminal:
        print(
            f"{current_time}/{duration} {status.player_state}                      \r",
            end="",
        )


# Type for inventory entry of a local files that can be served:
File = namedtuple("File", ["local_path", "size", "mimetype"])

# Regex for parsing "range" HTTP header value:
BYTE_RANGE_RE = re.compile(r"bytes=(\d+)?-(\d+)?")

# Type for parsed "range" HTTP header value:
Range = namedtuple("Range", ["first", "last"])


class HTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler class that serves local files to cast device.
    Supports range requests."""

    def __init__(self, *args, files, **kwargs):
        self._files = files
        self._file = None
        self.range = Range(first=None, last=None)
        super().__init__(*args, **kwargs)

    def do_GET(self):  # pylint: disable=invalid-name
        """Handle HTTP GET request."""

        self.parse_range()
        try:
            success = self.send_head()
            if not success:
                return

            with open(self._file.local_path, "rb") as rfile:
                self.copyfile(rfile, self.wfile)

        except (ConnectionResetError, BrokenPipeError):
            pass

    def do_HEAD(self):  # pylint: disable=invalid-name
        """Handle HTTP HEAD request."""

        try:
            self.send_head()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def send_head(self):
        """Check HTTP request and send response headers."""

        # Check if the request path can be found in our "inventory":
        if self.path in self._files:
            self._file = self._files[self.path]
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return False

        if self.range == Range(first=None, last=None):
            # Normal HTTP request without "range":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", self._file.size)
        else:
            # HTTP request for specific "range":
            last_pos = self._file.size - 1

            if self.range.first is None:  # handle "bytes=-N" case
                self.range = Range(
                    first=self._file.size - self.range.last, last=last_pos
                )
            elif self.range.last is None:  # handle "bytes=N-" case
                self.range = Range(first=self.range.first, last=last_pos)

            if (
                self.range.first > last_pos
                or self.range.last > last_pos
                or self.range.first > self.range.last
            ):  # Return 416 response code in case the range was bad:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{self._file.size}")
                return False

            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header(
                "Content-Length", str(self.range.last - self.range.first + 1)
            )
            self.send_header(
                "Content-Range",
                f"bytes {self.range.first}-{self.range.last}/{self._file.size}",
            )

        self.send_header("Content-Type", self._file.mimetype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        return True

    def parse_range(self):
        """Parse range header. Supports only a single range."""

        if not "Range" in self.headers:
            return

        match = BYTE_RANGE_RE.fullmatch(self.headers["Range"])
        if not match:
            return

        str1 = match.group(1)
        first = int(str1) if str1 is not None else None
        str2 = match.group(2)
        last = int(str2) if str2 is not None else None

        self.range = Range(first=first, last=last)

    def copyfile(self, rfile, wfile, bufsize=64 * 1024):
        """Copy file contents (all or range) from rfile to wfile."""

        first, last = self.range

        if first is None:
            first = 0

        if last is None:
            last = self._file.size - 1

        remaining = last - first + 1

        if first > 0:
            rfile.seek(first)

        while remaining > 0:
            buf = rfile.read(min(remaining, bufsize))
            if buf == "":
                # File got shorter while running?
                break

            wfile.write(buf)
            remaining -= len(buf)

    def log_request(self, code="-", size="-"):
        """Override log_request function to suppress log output."""

        return


def start_httpd(server_address, files):
    """Start HTTP server for serving local files."""

    # Use "partial" from "functools" to pass local file directory
    # to the request handler:
    handler = partial(HTTPRequestHandler, files=files)

    # Use a threading server variant so that we can serve multiple
    # HTTP requests simultaneously:
    httpd = socketserver.ThreadingTCPServer(
        server_address, handler, bind_and_activate=False
    )
    httpd.allow_reuse_address = True
    httpd.daemon_threads = True
    httpd.server_bind()
    httpd.server_activate()

    # Start the HTTP server in a daemon thread:
    httpd_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    httpd_thread.start()


def play_video(
    cast,
    video_url,
    video_mimetype,
    subs_url=None,
    subs_mimetype=None,
    wait_timeout=5,
    idle_timeout=10,
):  # pylint: disable=too-many-arguments
    """Play video on cast device and display status in terminal."""

    media_controller = cast.media_controller

    # Register a status listener that emits a status line on the terminal:
    media_status_listener = MyMediaStatusListener()
    media_controller.register_status_listener(media_status_listener)

    # Start playback:
    media_controller.play_media(
        video_url,
        video_mimetype,
        subtitles=subs_url,
        subtitles_mime=subs_mimetype,
    )
    media_controller.block_until_active(timeout=wait_timeout)

    try:
        idle_since = None

        while True:
            # Get status update from the cast device every second.
            # As a side effect this will cause a status line refresh
            # to be emitted to terminal.
            media_controller.update_status()

            if media_controller.status.player_is_idle:
                if idle_since is None:
                    idle_since = time.monotonic()
                else:
                    if time.monotonic() - idle_since > idle_timeout:
                        # Bail out if the player has been idle for 10 seconds.
                        # The video probably ended.
                        break

            else:
                idle_since = None

            time.sleep(1)

    except KeyboardInterrupt:
        # Pressing ctrl-C stops playback.
        pass

    print("\nExiting")
    media_controller.stop()
    media_controller.tear_down()
    cast.quit_app()


def prepare_source(source, mimetype, local_ip, local_port, url_path):
    """Prepare source file or URL for streaming."""

    if mimetype is None:
        mimetype = mimetypes.guess_type(source)[0]

    if source.startswith("http://") or source.startswith("https://"):
        # Remote URL
        url = source
        local_files = {}
    else:
        # Local file
        url = urljoin(f"http://{local_ip}:{local_port}/", url_path)

        local_files = {
            url_path: File(
                local_path=source,
                size=os.path.getsize(source),
                mimetype=mimetype,
            )
        }

    return url, mimetype, local_files


def handle_args():
    """Handle command-line arguments."""

    parser = argparse.ArgumentParser()
    parser.add_argument("video_source", help="video source (local file or URL)")
    parser.add_argument("--chromecast-name", help="Name of cast device")
    parser.add_argument(
        "--chromecast-ip",
        help="Add known cast device IP, can be used multiple times",
        action="append",
    )
    parser.add_argument(
        "--discovery-timeout",
        help="Cast device discovery timeout seconds (default: 10)",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--idle-timeout",
        help="Cast device idle timeout seconds (default: 10)",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--wait-timeout",
        help="Cast device wait timeout seconds (default: 5)",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--local-ip",
        help="Local IP for serving video (default: autodetect)",
        default="",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        help="Local port for serving video (default: 8080)",
        default=8080,
    )
    parser.add_argument(
        "--video-mimetype", help="Video source mimetype (default: autodetect)"
    )
    parser.add_argument("--subs", help="Subtitles source (local file or URL)")
    parser.add_argument(
        "--subs-mimetype", help="Subtitles source mimetype (default: autodetect)"
    )
    parser.add_argument("--debug", help="Enable debug output", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    return args


def discover_cast(args):
    """Discover and/or select cast device."""

    if args.chromecast_name:
        # Find a named cast device:
        chromecasts = pychromecast.get_listed_chromecasts(
            friendly_names=[args.chromecast_name],
            timeout=args.discovery_timeout,
            known_hosts=args.chromecast_ip,
        )[0]
    else:
        chromecasts = []
        discover_complete = Event()

        def found_device(cast):
            chromecasts.append(cast)
            discover_complete.set()

        # Find one cast device (the first one to respond):
        browser = pychromecast.get_chromecasts(
            timeout=args.discovery_timeout,
            known_hosts=args.chromecast_ip,
            blocking=False,
            callback=found_device,
        )
        discover_complete.wait(args.discovery_timeout)

    if not chromecasts:
        print("Could not find cast device")
        sys.exit(1)

    print(f"Discovered devices: {[cast.name for cast in chromecasts]}")

    # Pick the first device if there are many:
    cast = chromecasts[0]
    print(f"Casting to: {cast.name}")

    return cast


def main():
    """Main."""

    args = handle_args()

    cast = discover_cast(args)

    cast.wait(timeout=args.wait_timeout)

    # Determine our local IP address that the cast device should use when
    # doing a reverse connection back to us:
    if args.local_ip:
        local_ip = args.local_ip
    else:
        local_ip = cast.socket_client.socket.getsockname()[0]

    # Prepare video file or URL:
    video_url, video_mimetype, local_files = prepare_source(
        args.video_source,
        args.video_mimetype,
        local_ip,
        args.local_port,
        "/video",
    )

    # Prepare subtitles file or URL:
    if args.subs is not None:
        subs_url, subs_mimetype, subs_local_files = prepare_source(
            args.subs,
            args.subs_mimetype,
            local_ip,
            args.local_port,
            "/subtitles",
        )
        local_files |= subs_local_files
    else:
        subs_url = None
        subs_mimetype = None

    # Start local HTTP server in case we need to serve local files
    # to the cast device:
    if local_files:
        start_httpd((args.local_ip, args.local_port), local_files)

    print(f"Video URL: {video_url} ({video_mimetype})")
    if subs_url:
        print(f"Subtitles URL: {subs_url} ({subs_mimetype})")

    # Video playback:
    play_video(
        cast,
        video_url,
        video_mimetype,
        subs_url=subs_url,
        subs_mimetype=subs_mimetype,
        wait_timeout=args.wait_timeout,
        idle_timeout=args.idle_timeout,
    )

    cast.disconnect(timeout=args.wait_timeout)


if __name__ == "__main__":
    main()
