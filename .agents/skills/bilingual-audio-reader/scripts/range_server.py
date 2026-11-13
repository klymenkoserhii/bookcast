#!/usr/bin/env python3
"""
range_server.py — tiny static file server with HTTP Range support.

    python range_server.py <directory> [port]      # default port 8150

Why this exists: `python -m http.server` ignores Range requests, so an <audio>
element cannot seek and every "play section N" test silently fails. Browsers
also cannot open file:// pages in some automation harnesses. This server speaks
HTTP/1.1 keep-alive (HTTP/1.0 responses were intermittently rejected with 502
by an automation proxy) and answers byte ranges with 206.

Run it in the background, test, then kill it:
    nohup python range_server.py "$PWD" 8150 >/tmp/range.log 2>&1 &
    pkill -f range_server.py
"""

import functools
import http.server
import os
import re
import sys


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if os.path.isdir(path) or not rng:
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404)
            return None
        size = os.fstat(f.fileno()).st_size
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        start = int(m.group(1) or 0)
        end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        f.seek(start)
        return _Limited(f, end - start + 1)


class _Limited:
    def __init__(self, f, n):
        self.f, self.n = f, n

    def read(self, k=-1):
        if self.n <= 0:
            return b""
        k = self.n if k < 0 or k > self.n else k
        data = self.f.read(k)
        self.n -= len(data)
        return data

    def close(self):
        self.f.close()


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8150
    handler = functools.partial(RangeHandler, directory=directory)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
