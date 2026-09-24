"""Roaming Profile API tests — real Django views/models via test client.

Covers the full client contract (see docs/roaming-api.md): auth,
capabilities, manifest generation semantics, encrypted blobs, JSON
records, payload bounds, name validation, user isolation, token/user
lifecycle, license enforcement, and the legacy settings/data sync
regression.
"""

import json

import pytest
from django.core.cache import cache

CAP = "/eveaio/api/capabilities/"
MAN = "/eveaio/api/roaming/manifest/"
BLOBS = "/eveaio/api/roaming/blobs/"
BLOB = "/eveaio/api/roaming/blob/"
RECORDS = "/eveaio/api/roaming/records/"


def hdr(token):
    return {"HTTP_X_EVEAIO_TOKEN": token}


def man(gen=1, snap=None, pid="profile-uuid-1"):
    m = {"format": "eveaio-roaming-profile", "profile_id": pid,
         "generation": gen, "device_name": "Desk"}
    if snap:
        m["snapshot_file"] = snap
    return m


def put_manifest(client, token, expected, manifest):
    return client.put(MAN, data=json.dumps(
        {"expected_generation": expected, "manifest": manifest}),
        content_type="application/json", **hdr(token))


def put_blob(client, token, name, payload):
    return client.put(BLOB + name, data=payload,
                      content_type="application/octet-stream", **hdr(token))


def put_record(client, token, rel, record):
    return client.put(RECORDS + rel, data=json.dumps({"record": record}),
                      content_type="application/json", **hdr(token))


# ---------------------------------------------------------------------------
# capabilities
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCapabilities:
    def test_shape(self, client, user_a):
        r = client.get(CAP, **hdr(user_a[1]))
        assert r.status_code == 200
        data = r.json()
        assert data["roaming_profile"] is True
        assert data["roaming_api"] == 1
        assert data["max_payload_bytes"] == 8 * 1024 * 1024

    def test_missing_token_401(self, client):
        assert client.get(CAP).status_code == 401

    def test_invalid_token_403(self, client):
        assert client.get(CAP, **hdr("nope")).status_code == 403

    def test_post_405(self, client, user_a):
        assert client.post(CAP, **hdr(user_a[1])).status_code == 405


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestManifest:
    def test_get_no_profile_404(self, client, user_a):
        assert client.get(MAN, **hdr(user_a[1])).status_code == 404

    def test_create_and_read(self, client, user_a):
        r = put_manifest(client, user_a[1], 0, man(gen=1))
        assert r.status_code == 200
        assert r.json() == {"ok": True, "generation": 1}
        r = client.get(MAN, **hdr(user_a[1]))
        assert r.status_code == 200
        assert r.json()["manifest"]["generation"] == 1
        assert r.json()["manifest"]["profile_id"] == "profile-uuid-1"

    def test_advance_and_stale_rejected(self, client, user_a):
        put_manifest(client, user_a[1], 0, man(gen=1))
        r = put_manifest(client, user_a[1], 1, man(gen=2))
        assert r.status_code == 200
        # stale writer still basing on generation 0
        r = put_manifest(client, user_a[1], 0, man(gen=1))
        assert r.status_code == 409
        assert r.json()["current_generation"] == 2
        # re-writing the current generation is also stale
        r = put_manifest(client, user_a[1], 1, man(gen=2))
        assert r.status_code == 409

    def test_expected_nonzero_without_profile_409(self, client, user_a):
        r = put_manifest(client, user_a[1], 3, man(gen=4))
        assert r.status_code == 409
        assert r.json()["current_generation"] == 0

    def test_generation_mismatch_400(self, client, user_a):
        # expected=0 but manifest claims generation 5
        r = put_manifest(client, user_a[1], 0, man(gen=5))
        assert r.status_code == 400

    def test_missing_manifest_400(self, client, user_a):
        r = client.put(MAN, data=json.dumps({"expected_generation": 0}),
                       content_type="application/json", **hdr(user_a[1]))
        assert r.status_code == 400

    def test_bad_json_400(self, client, user_a):
        r = client.put(MAN, data="{not json", content_type="application/json",
                       **hdr(user_a[1]))
        assert r.status_code == 400

    def test_snapshot_must_exist_before_commit(self, client, user_a):
        # Manifest references a snapshot that was never uploaded.
        r = put_manifest(client, user_a[1], 0,
                         man(gen=1, snap="snapshot_000001.roam"))
        assert r.status_code == 409
        assert "snapshot" in r.json()["error"]
        # Upload the blob first -> commit succeeds.
        put_blob(client, user_a[1], "snapshot_000001.roam", b"cipher")
        r = put_manifest(client, user_a[1], 0,
                         man(gen=1, snap="snapshot_000001.roam"))
        assert r.status_code == 200

    def test_invalid_snapshot_file_name_400(self, client, user_a):
        r = put_manifest(client, user_a[1], 0, man(gen=1, snap="../evil"))
        assert r.status_code == 400

    def test_method_restrictions(self, client, user_a):
        assert client.post(MAN, **hdr(user_a[1])).status_code == 405
        assert client.delete(MAN, **hdr(user_a[1])).status_code == 405


# ---------------------------------------------------------------------------
# blobs (encrypted snapshots)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBlobs:
    def test_roundtrip_binary_exact(self, client, user_a):
        payload = bytes(range(256)) * 64 + b"\x00\xff binary \xfe"
        r = put_blob(client, user_a[1], "snapshot_000001.roam", payload)
        assert r.status_code == 200 and r.json()["ok"] is True
        r = client.get(BLOB + "snapshot_000001.roam", **hdr(user_a[1]))
        assert r.status_code == 200
        assert r["Content-Type"] == "application/octet-stream"
        assert r.content == payload

    def test_missing_404(self, client, user_a):
        assert client.get(BLOB + "snapshot_000042.roam",
                          **hdr(user_a[1])).status_code == 404

    def test_invalid_names_400(self, client, user_a):
        for bad in ("evil.txt", "snapshot_1.roam", "snapshot_abcdef.roam",
                    "snapshot_000001.roam.exe"):
            assert put_blob(client, user_a[1], bad, b"x").status_code == 400
            assert client.get(BLOB + bad, **hdr(user_a[1])).status_code == 400

    def test_list_and_delete(self, client, user_a):
        put_blob(client, user_a[1], "snapshot_000001.roam", b"a")
        put_blob(client, user_a[1], "snapshot_000002.roam", b"b")
        r = client.get(BLOBS, **hdr(user_a[1]))
        assert r.json()["names"] == ["snapshot_000001.roam",
                                     "snapshot_000002.roam"]
        r = client.delete(BLOB + "snapshot_000001.roam", **hdr(user_a[1]))
        assert r.status_code == 204
        # idempotent
        assert client.delete(BLOB + "snapshot_000001.roam",
                             **hdr(user_a[1])).status_code == 204
        assert client.get(BLOBS, **hdr(user_a[1])).json()["names"] == \
            ["snapshot_000002.roam"]

    def test_payload_limit_boundary(self, client, user_a):
        from aa_eveaio.views import ROAMING_MAX_PAYLOAD_BYTES as LIM
        assert put_blob(client, user_a[1], "snapshot_000001.roam",
                        b"x" * (LIM - 1)).status_code == 200
        assert put_blob(client, user_a[1], "snapshot_000001.roam",
                        b"x" * LIM).status_code == 200
        assert put_blob(client, user_a[1], "snapshot_000001.roam",
                        b"x" * (LIM + 1)).status_code == 413

    def test_blob_count_bound(self, client, user_a, monkeypatch):
        import aa_eveaio.views as v
        monkeypatch.setattr(v, "ROAMING_MAX_BLOBS", 3)
        for i in range(1, 4):
            assert put_blob(client, user_a[1],
                            f"snapshot_{i:06d}.roam", b"x").status_code == 200
        assert put_blob(client, user_a[1], "snapshot_000004.roam",
                        b"x").status_code == 413
        # overwriting an existing blob is still fine
        assert put_blob(client, user_a[1], "snapshot_000001.roam",
                        b"x").status_code == 200

    def test_method_restrictions(self, client, user_a):
        assert client.post(BLOB + "snapshot_000001.roam",
                           **hdr(user_a[1])).status_code == 405


# ---------------------------------------------------------------------------
# records (recovery.json, devices/<id>.json)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecords:
    def test_roundtrip(self, client, user_a):
        assert client.get(RECORDS + "recovery.json",
                          **hdr(user_a[1])).status_code == 404
        rec = {"format": "eveaio-roaming-recovery", "wrapped_key": "b64=="}
        assert put_record(client, user_a[1], "recovery.json",
                          rec).status_code == 200
        r = client.get(RECORDS + "recovery.json", **hdr(user_a[1]))
        assert r.json()["record"] == rec

    def test_nested_device_records_and_prefix_list(self, client, user_a):
        put_record(client, user_a[1], "devices/dev-1.json",
                   {"device_id": "dev-1", "device_name": "Desk"})
        put_record(client, user_a[1], "devices/dev-2.json",
                   {"device_id": "dev-2"})
        put_record(client, user_a[1], "recovery.json", {"wrapped": "k"})
        r = client.get(RECORDS, data={"prefix": "devices/"},
                       **hdr(user_a[1]))
        recs = r.json()["records"]
        assert set(recs) == {"devices/dev-1.json", "devices/dev-2.json"}
        assert recs["devices/dev-1.json"]["device_name"] == "Desk"
        # no prefix -> all records
        r = client.get(RECORDS, **hdr(user_a[1]))
        assert len(r.json()["records"]) == 3

    def test_invalid_record_names_400(self, client, user_a):
        for bad in ("../escape.json", "a/../b.json", "bad name.json",
                    "a//b.json"):
            assert put_record(client, user_a[1], bad, {}).status_code == 400
        # traversal that survives URL normalisation must also fail
        assert client.get("/eveaio/api/roaming/records/%2e%2e/x.json",
                          **hdr(user_a[1])).status_code == 400

    def test_delete_idempotent(self, client, user_a):
        put_record(client, user_a[1], "devices/d.json", {"device_id": "d"})
        assert client.delete(RECORDS + "devices/d.json",
                             **hdr(user_a[1])).status_code == 204
        assert client.delete(RECORDS + "devices/d.json",
                             **hdr(user_a[1])).status_code == 204
        assert client.get(RECORDS + "devices/d.json",
                          **hdr(user_a[1])).status_code == 404

    def test_record_size_bound(self, client, user_a, monkeypatch):
        import aa_eveaio.views as v
        monkeypatch.setattr(v, "ROAMING_MAX_RECORD_BYTES", 64)
        big = {"blob": "x" * 200}
        assert put_record(client, user_a[1], "big.json", big
                          ).status_code == 413
        small = {"ok": True}
        assert put_record(client, user_a[1], "ok.json",
                          small).status_code == 200

    def test_bad_body_400(self, client, user_a):
        assert client.put(RECORDS + "x.json", data="{bad",
                          content_type="application/json",
                          **hdr(user_a[1])).status_code == 400
        assert client.put(RECORDS + "x.json", data=json.dumps({"x": 1}),
                          content_type="application/json",
                          **hdr(user_a[1])).status_code == 400

    def test_method_restrictions(self, client, user_a):
        assert client.post(RECORDS + "x.json",
                           **hdr(user_a[1])).status_code == 405
        assert client.put(RECORDS, **hdr(user_a[1])).status_code == 405


# ---------------------------------------------------------------------------
# user isolation — release-blocking
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserIsolation:
    def _seed_a(self, client, token):
        put_blob(client, token, "snapshot_000001.roam", b"A-CIPHERTEXT")
        put_manifest(client, token, 0,
                     man(gen=1, snap="snapshot_000001.roam",
                         pid="profile-A"))
        put_record(client, token, "recovery.json", {"wrapped": "A-key"})
        put_record(client, token, "devices/devA.json",
                   {"device_id": "devA"})

    def test_b_reads_nothing(self, client, user_a, user_b):
        self._seed_a(client, user_a[1])
        tb = user_b[1]
        assert client.get(MAN, **hdr(tb)).status_code == 404
        assert client.get(BLOB + "snapshot_000001.roam",
                          **hdr(tb)).status_code == 404
        assert client.get(BLOBS, **hdr(tb)).json()["names"] == []
        assert client.get(RECORDS + "recovery.json",
                          **hdr(tb)).status_code == 404
        assert client.get(RECORDS + "devices/devA.json",
                          **hdr(tb)).status_code == 404
        assert client.get(RECORDS, **hdr(tb)).json()["records"] == {}

    def test_b_writes_never_touch_a(self, client, user_a, user_b):
        self._seed_a(client, user_a[1])
        tb = user_b[1]
        # B "creates" their own profile — must not alter A's.
        assert put_manifest(client, tb, 0,
                            man(gen=1, pid="profile-B")).status_code == 200
        put_blob(client, tb, "snapshot_000001.roam", b"B-CIPHERTEXT")
        put_record(client, tb, "recovery.json", {"wrapped": "B-key"})
        client.delete(BLOB + "snapshot_000001.roam", **hdr(tb))
        client.delete(RECORDS + "recovery.json", **hdr(tb))
        # A's data untouched.
        r = client.get(MAN, **hdr(user_a[1]))
        assert r.json()["manifest"]["profile_id"] == "profile-A"
        assert client.get(BLOB + "snapshot_000001.roam",
                          **hdr(user_a[1])).content == b"A-CIPHERTEXT"
        assert client.get(RECORDS + "recovery.json",
                          **hdr(user_a[1])).json()["record"] == \
            {"wrapped": "A-key"}

    def test_b_stale_write_cannot_override_a(self, client, user_a, user_b):
        self._seed_a(client, user_a[1])
        # B tries expected_generation=0 style overwrites — but B has no
        # committed profile, so anything above 0 is conflict, 0 creates B's
        # OWN profile (isolation intact either way).
        assert put_manifest(client, user_b[1], 1,
                            man(gen=2)).status_code == 409
        r = client.get(MAN, **hdr(user_a[1]))
        assert r.json()["manifest"]["generation"] == 1


# ---------------------------------------------------------------------------
# auth lifecycle: token regen / delete / user cascade
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLifecycle:
    def test_token_regeneration(self, client, user_a):
        user, tok1 = user_a
        put_manifest(client, tok1, 0, man(gen=1))
        from aa_eveaio.models import EveAioServiceToken
        tok_obj = EveAioServiceToken.objects.get(user=user)
        tok_obj.regenerate_token()
        tok2 = tok_obj.token
        assert tok2 != tok1
        # old token dead, new token reaches the SAME profile
        assert client.get(MAN, **hdr(tok1)).status_code == 403
        r = client.get(MAN, **hdr(tok2))
        assert r.status_code == 200
        assert r.json()["manifest"]["generation"] == 1

    def test_token_deleted_loses_access(self, client, user_a):
        user, tok = user_a
        put_manifest(client, tok, 0, man(gen=1))
        user.eveaio_service_token.delete()
        assert client.get(MAN, **hdr(tok)).status_code == 403

    def test_user_delete_cascades(self, client, user_a):
        user, tok = user_a
        put_blob(client, tok, "snapshot_000001.roam", b"x")
        put_manifest(client, tok, 0,
                     man(gen=1, snap="snapshot_000001.roam"))
        put_record(client, tok, "recovery.json", {"w": 1})
        from aa_eveaio.models import (EveAioRoamingObject,
                                      EveAioRoamingProfile)
        assert EveAioRoamingProfile.objects.count() == 1
        assert EveAioRoamingObject.objects.count() == 2
        user.delete()
        assert EveAioRoamingProfile.objects.count() == 0
        assert EveAioRoamingObject.objects.count() == 0

    def test_license_failure_402(self, client, user_a):
        cache.clear()  # drop the seeded "license valid" flag
        assert client.get(CAP, **hdr(user_a[1])).status_code == 402
        assert client.get(MAN, **hdr(user_a[1])).status_code == 402


# ---------------------------------------------------------------------------
# legacy endpoints regression — untouched by roaming
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLegacySyncRegression:
    def test_settings_sync_roundtrip(self, client, user_a):
        body = {"settings": {"theme": "dark", "x": 1}, "version": "9.9.9"}
        r = client.post("/eveaio/api/settings_sync/",
                        data=json.dumps(body),
                        content_type="application/json", **hdr(user_a[1]))
        assert r.status_code == 200
        r = client.get("/eveaio/api/settings_sync/", **hdr(user_a[1]))
        assert r.json()["settings"] == {"theme": "dark", "x": 1}
        assert r.json()["version"] == "9.9.9"

    def test_data_sync_roundtrip(self, client, user_a):
        body = {"data": {"ledger": {"a": 1}}, "version": "9.9.9"}
        r = client.post("/eveaio/api/data_sync/", data=json.dumps(body),
                        content_type="application/json", **hdr(user_a[1]))
        assert r.status_code == 200
        r = client.get("/eveaio/api/data_sync/", **hdr(user_a[1]))
        assert r.json()["data"] == {"ledger": {"a": 1}}


# ---------------------------------------------------------------------------
# logging — never bodies, never tokens
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLogging:
    def test_no_secret_in_logs(self, client, user_a, caplog):
        import logging
        payload = b"CIPHERTEXT-BYTES-SENTINEL-\x00\x99" * 4
        with caplog.at_level(logging.INFO, logger="aa_eveaio.views"):
            put_blob(client, user_a[1], "snapshot_000001.roam", payload)
            put_manifest(client, user_a[1], 0,
                         man(gen=1, snap="snapshot_000001.roam"))
        out = "\n".join(r.getMessage() for r in caplog.records)
        assert "CIPHERTEXT-BYTES-SENTINEL" not in out
        assert "token-a" not in out  # the token value never logged
