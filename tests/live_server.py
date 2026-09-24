"""In-process real-HTTP server for integration tests.

Serves the actual Django WSGI application (the same handlers Alliance
Auth's runserver uses) on a loopback port, so tests exercise real HTTP —
headers, octet-stream bodies, keep-alive — rather than the Django test
client's request factory. Same process => the locmem license cache and
ORM setup performed by the test are visible to the server, as long as
the test runs with ``django_db(transaction=True)`` so writes commit.
"""

import threading

from django.core.handlers.wsgi import WSGIHandler
from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass


class LiveAAServer:
    """Threaded WSGI server bound to 127.0.0.1 on an ephemeral port."""

    def __init__(self):
        self.httpd = None
        self.port = 0
        self._thread = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.httpd = WSGIServer(("127.0.0.1", 0), _QuietHandler)
        self.httpd.set_app(WSGIHandler())
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="LiveAAServer", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
