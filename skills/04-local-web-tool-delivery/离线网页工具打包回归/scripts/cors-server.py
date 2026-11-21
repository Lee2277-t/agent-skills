#!/usr/bin/env python3
"""One-shot CORS static server for local test fixtures. Binds 127.0.0.1 only.

stdout is ASCII-safe (Windows console codepages mangle Chinese); the real port is
always taken from the READY line, never assumed.
"""
import argparse
import functools
import http.server
import os
import socket
import sys
import threading


def emit(line):
    sys.stdout.write(line.encode("ascii", "replace").decode("ascii") + "\n")
    sys.stdout.flush()


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        emit("REQ %s %s" % (self.address_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="directory to serve (usually the fixtures dir)")
    ap.add_argument("--port", type=int, default=0, help="0 = auto-pick a free port")
    ap.add_argument("--scan", type=int, default=20, help="ports to try above --port")
    ap.add_argument("--exit-after", type=int, default=1800, help="self-terminate seconds")
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        emit("ERROR not a directory: " + root.encode("unicode_escape").decode("ascii"))
        return 2

    handler = functools.partial(Handler, directory=root)
    server = None
    tried = []
    candidates = ([args.port] if args.port else range(8790, 8790 + args.scan))
    for port in candidates:
        try:
            server = http.server.ThreadingHTTPServer((args.bind, port), handler)
            break
        except OSError as exc:
            tried.append("%d:%s" % (port, exc.errno))
    if server is None:
        emit("ERROR no free port, tried " + ",".join(tried))
        return 2

    if args.exit_after > 0:
        threading.Timer(args.exit_after, os._exit, args=(0,)).start()

    host, port = server.server_address[0], server.server_port
    emit("PID %d" % os.getpid())
    emit("ROOT %s" % root.encode("unicode_escape").decode("ascii"))
    emit("READY http://%s:%d/" % (host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    socket.setdefaulttimeout(None)
    sys.exit(main())
