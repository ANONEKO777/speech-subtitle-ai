import argparse
import http.server
import sys

parser = argparse.ArgumentParser()
parser.add_argument("-m")
parser.add_argument("--host", required=True)
parser.add_argument("--port", type=int, required=True)
parser.add_argument("-ngl")
parser.add_argument("-c")
parser.add_argument("-np")
parser.add_argument("--no-webui", action="store_true")
parser.add_argument("--die", action="store_true")
args = parser.parse_args()
if args.die:
    sys.exit(3)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return None


http.server.HTTPServer((args.host, args.port), Handler).serve_forever()
