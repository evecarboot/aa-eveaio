"""Roaming API over real HTTP — in-process WSGI server + requests.

Exercises the same code path Alliance Auth serves in production:
actual sockets, headers, octet-stream bodies, keep-alive connections.
Also the threaded two-writer generation conflict proof.

These tests use ``transaction=True`` so ORM setup commits are visible to
the server thread's separate DB connection (same file-backed test DB).
"""

import json
import threading

import pytest
import requests

from tests.live_server import LiveAAServer


@pytest.fixture()
def live(transactional_db):
    srv = LiveAAServer().start()
    try:
        yield srv
    finally:
        srv.stop()


def _mk_user(username, token):
    from django.contrib.auth import get_user_model
    from aa_eveaio.models import EveAioServiceToken
    u = get_user_model().objects.create_user(username=username, password="x")
    EveAioServiceToken.objects.create(user=u, token=token)
    return u


def H(token):
    return {"X-Eveaio-Token": token}


@pytest.mark.django_db(transaction=True)
class TestLiveRoamingAPI:
    def test_full_roundtrip_over_http(self, live):
        _mk_user("alice", "token-a")
        s = requests.Session()
        cap = s.get(live.url + "/eveaio/api/capabilities/",
                    headers=H("token-a"), timeout=5)
        assert cap.status_code == 200
        assert cap.json()["roaming_profile"] is True

        # records + blob + manifest — the real client order
        r = s.put(live.url + "/eveaio/api/roaming/records/recovery.json",
                  headers=H("token-a"), json={"record": {"wrapped": "k"}},
                  timeout=5)
        assert r.status_code == 200
        blob = bytes(range(256)) * 8
        r = s.put(live.url + "/eveaio/api/roaming/blob/snapshot_000001.roam",
                  headers={**H("token-a"),
                           "Content-Type": "application/octet-stream"},
                  data=blob, timeout=5)
        assert r.status_code == 200
        man = {"format": "eveaio-roaming-profile", "profile_id": "pid-1",
               "generation": 1, "snapshot_file": "snapshot_000001.roam"}
        r = s.put(live.url + "/eveaio/api/roaming/manifest/",
                  headers=H("token-a"),
                  json={"expected_generation": 0, "manifest": man},
                  timeout=5)
        assert r.status_code == 200 and r.json()["generation"] == 1

        r = s.get(live.url + "/eveaio/api/roaming/manifest/",
                  headers=H("token-a"), timeout=5)
        assert r.json()["manifest"]["profile_id"] == "pid-1"
        r = s.get(live.url + "/eveaio/api/roaming/blob/snapshot_000001.roam",
                  headers=H("token-a"), timeout=5)
        assert r.content == blob
        r = s.get(live.url + "/eveaio/api/roaming/records/",
                  headers=H("token-a"), params={"prefix": ""}, timeout=5)
        assert r.json()["records"]["recovery.json"] == {"wrapped": "k"}
        # keep-alive reuse across all those calls on one Session — no leak
        s.close()

    def test_no_auth_over_http(self, live):
        r = requests.get(live.url + "/eveaio/api/roaming/manifest/",
                         timeout=5)
        assert r.status_code == 401
        r = requests.get(live.url + "/eveaio/api/roaming/manifest/",
                         headers=H("bogus"), timeout=5)
        assert r.status_code == 403

    def test_two_writers_one_wins(self, live):
        """Two writers base on generation 0; exactly one promotes gen 1."""
        _mk_user("alice", "token-a")
        results = []

        def writer(tag):
            sess = requests.Session()
            try:
                man = {"profile_id": f"pid-{tag}", "generation": 1}
                r = sess.put(
                    live.url + "/eveaio/api/roaming/manifest/",
                    headers=H("token-a"),
                    json={"expected_generation": 0, "manifest": man},
                    timeout=15)
                results.append(r.status_code)
            finally:
                sess.close()

        threads = [threading.Thread(target=writer, args=(i,))
                   for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert sorted(results) == [200, 409]

    def test_two_writers_existing_generation(self, live):
        _mk_user("alice", "token-a")
        man1 = {"profile_id": "p", "generation": 1}
        requests.put(live.url + "/eveaio/api/roaming/manifest/",
                     headers=H("token-a"),
                     json={"expected_generation": 0, "manifest": man1},
                     timeout=5)
        results = []

        def writer(tag):
            r = requests.put(
                live.url + "/eveaio/api/roaming/manifest/",
                headers=H("token-a"),
                json={"expected_generation": 1,
                      "manifest": {"profile_id": f"p-{tag}",
                                   "generation": 2}},
                timeout=15)
            results.append(r.status_code)

        threads = [threading.Thread(target=writer, args=(i,))
                   for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert sorted(results) == [200, 409, 409]
