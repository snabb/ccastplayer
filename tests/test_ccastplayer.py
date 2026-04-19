import io
import os
import tempfile
import unittest

import ccastplayer


class HTTPRequestHandlerTests(unittest.TestCase):
    def make_handler(self):
        handler = ccastplayer.HTTPRequestHandler.__new__(ccastplayer.HTTPRequestHandler)
        handler.headers = {}
        handler._files = {}
        handler._file = None
        handler.path = "/video"
        handler.range = ccastplayer.Range(first=None, last=None)
        handler.responses = []
        handler.error_responses = []
        handler.ended = False
        handler.send_response = lambda code: handler.responses.append(("status", code))
        handler.send_header = lambda name, value: handler.responses.append((name, value))
        handler.end_headers = lambda: setattr(handler, "ended", True)
        handler.send_error = lambda code, message=None: handler.error_responses.append(
            (code, message)
        )
        return handler

    def test_parse_range_header(self):
        handler = self.make_handler()
        handler.headers["Range"] = "bytes=10-20"

        ccastplayer.HTTPRequestHandler.parse_range(handler)

        self.assertEqual(handler.range, ccastplayer.Range(first=10, last=20))

    def test_send_head_returns_416_with_content_range(self):
        handler = self.make_handler()
        handler._files = {
            "/video": ccastplayer.File(
                local_path="movie.mp4", size=100, mimetype="video/mp4"
            )
        }
        handler.range = ccastplayer.Range(first=200, last=300)

        success = ccastplayer.HTTPRequestHandler.send_head(handler)

        self.assertFalse(success)
        self.assertEqual(
            handler.responses,
            [
                ("status", ccastplayer.HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE),
                ("Content-Range", "bytes */100"),
            ],
        )
        self.assertTrue(handler.ended)

    def test_copyfile_stops_when_source_reaches_eof(self):
        handler = self.make_handler()
        handler._file = ccastplayer.File(
            local_path="movie.mp4", size=10, mimetype="video/mp4"
        )
        handler.range = ccastplayer.Range(first=0, last=9)
        source = io.BytesIO(b"12345")
        target = io.BytesIO()

        ccastplayer.HTTPRequestHandler.copyfile(handler, source, target, bufsize=4)

        self.assertEqual(target.getvalue(), b"12345")


class PrepareSourceTests(unittest.TestCase):
    def test_prepare_remote_source_keeps_url(self):
        url, mimetype, local_files = ccastplayer.prepare_source(
            "https://example.com/video.mp4", None, "192.0.2.1", 8080, "/video"
        )

        self.assertEqual(url, "https://example.com/video.mp4")
        self.assertEqual(mimetype, "video/mp4")
        self.assertEqual(local_files, {})

    def test_prepare_local_source_registers_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_file.write(b"video")
            local_path = temp_file.name

        try:
            url, mimetype, local_files = ccastplayer.prepare_source(
                local_path, None, "192.0.2.1", 8080, "/video"
            )
        finally:
            os.unlink(local_path)

        self.assertEqual(url, "http://192.0.2.1:8080/video")
        self.assertEqual(mimetype, "video/mp4")
        self.assertIn("/video", local_files)
        self.assertEqual(local_files["/video"].local_path, local_path)


if __name__ == "__main__":
    unittest.main()
