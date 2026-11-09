"""Public connection configuration and bounded HTTP behavior without a server."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from piixelverso.piixelfone.config import (
    Config, ConfigError, DEFAULT_URL, MAX_CONFIG_BYTES, load_config, save_config,
)
from piixelverso.piixelfone.transport import (
    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, TIMEOUT_SECONDS, Transport,
    TransportError, _NoRedirects,
)


PUBLIC_KEY = "sb_publishable_public_client_key_12345"
USER_ID = "42caa2df-c2c0-480c-9ba6-9c8fa9ccc843"


def legacy_key(role):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    return ".".join((part({"alg": "HS256", "typ": "JWT"}), part({"role": role}), "signature"))


class Response(io.BytesIO):
    def __init__(self, value, status=200):
        super().__init__(value if isinstance(value, bytes) else json.dumps(value).encode())
        self.status = status


class Requester:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


class PiixelfoneConfigTests(unittest.TestCase):
    def test_missing_config_is_first_run_and_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connection.json"
            config = load_config(path)
            self.assertEqual(config, Config(DEFAULT_URL, ""))
            self.assertFalse(path.exists())
            with self.assertRaisesRegex(ConfigError, "administrador do sistema"):
                config.validate()

    def test_publishable_and_legacy_anon_are_accepted(self):
        for key in (PUBLIC_KEY, legacy_key("anon")):
            with self.subTest(key_type=key[:16]):
                config = Config(" " + DEFAULT_URL + "/ ", " " + key + " ")
                self.assertIs(config.validate(), config)
                self.assertEqual(config.url, DEFAULT_URL)
                self.assertEqual(config.public_key, key)

    def test_rejects_secret_administrative_and_arbitrary_keys(self):
        keys = ["sb_secret_do_not_accept_this", legacy_key("service_role"), legacy_key("authenticated"),
                "service_role", "arbitrary", "a.b.c", "sb_publishable_short", PUBLIC_KEY + "\nextra",
                "a" * 8193, None, 42]
        for key in keys:
            with self.subTest(key_type=str(key)[:20]):
                with self.assertRaises(ConfigError):
                    Config(DEFAULT_URL, key).validate()

    def test_url_accepts_only_https_origin(self):
        urls = ["http://localhost", "http://example.supabase.co", "https://user:pass@example.org",
                "https://example.org/query?key=abc", "https://example.org/#fragment", "https://example.org:123",
                "https://example.org:abc", "https://example.org\n", "https://ex ample.org",
                "https://example.org/other", "file:///etc/passwd", "https://.example.org", "https://a..org",
                None, 3]
        # Surrounding whitespace is intentionally normalized, but embedded
        # control characters never reach urllib's header or URL parsing.
        urls.remove("https://example.org\n")
        urls.append("https://exam\nple.org")
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(ConfigError):
                    Config(url, PUBLIC_KEY).validate()
        self.assertEqual(Config("https://custom.example.org:443", PUBLIC_KEY).validate().url,
                         "https://custom.example.org:443")

    def test_config_roundtrip_contains_only_public_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phone" / "connection.json"
            config = Config(DEFAULT_URL, PUBLIC_KEY)
            save_config(path, config)
            self.assertEqual(load_config(path), config)
            self.assertEqual(json.loads(path.read_bytes()), {
                "version": 1, "url": DEFAULT_URL, "public_key": PUBLIC_KEY,
            })
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_atomic_save_failure_preserves_previous_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connection.json"
            config = Config(DEFAULT_URL, PUBLIC_KEY)
            save_config(path, config)
            before = path.read_bytes()
            with patch("piixelverso.piixelfone.config.os.replace", side_effect=OSError("disk-full")):
                with self.assertRaises(ConfigError):
                    save_config(path, Config("https://other.example.org", PUBLIC_KEY))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob(".connection-*.tmp")), [])

    def test_malformed_or_oversized_config_never_echoes_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connection.json"
            for raw in (b"not-json-private-data", b"[]", b'"private"', b"x" * (MAX_CONFIG_BYTES + 1),
                        json.dumps({"version": 1, "url": DEFAULT_URL, "public_key": "sb_secret_PRIVATE"}).encode()):
                path.write_bytes(raw)
                with self.assertRaises(ConfigError) as raised:
                    load_config(path)
                self.assertNotIn("PRIVATE", str(raised.exception))


class PiixelfoneTransportTests(unittest.TestCase):
    def auth(self):
        return {"access_token": "access-private-value", "refresh_token": "refresh-private-value",
                "user": {"id": USER_ID}, "expires_at": 2_000_000_000}

    def transport(self, requester):
        return Transport(Config(DEFAULT_URL, PUBLIC_KEY), requester=requester)

    def test_signup_is_anonymous_post_and_normalizes_session(self):
        response = self.auth() | {"user": {"id": USER_ID, "email": "ignored"}, "unexpected": "ignored"}
        requester = Requester(Response(response))
        transport = self.transport(requester)
        self.assertEqual(transport.sign_up(), self.auth())
        request, timeout = requester.requests[0]
        self.assertEqual(request.full_url, DEFAULT_URL + "/auth/v1/signup")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"data": {}})
        self.assertEqual(timeout, TIMEOUT_SECONDS)
        self.assertEqual(request.get_header("Apikey"), PUBLIC_KEY)
        self.assertIsNone(request.get_header("Authorization"))

    def test_session_expiration_derived_when_auth_returns_duration(self):
        response = self.auth()
        del response["expires_at"]
        response["expires_in"] = 3600
        with patch("piixelverso.piixelfone.transport.time.time", return_value=1000):
            auth = self.transport(Requester(Response(response))).sign_up()
        self.assertEqual(auth["expires_at"], 4600)

    def test_refresh_only_posts_refresh_token_to_token_endpoint(self):
        requester = Requester(Response(self.auth()))
        transport = self.transport(requester)
        self.assertEqual(transport.refresh("old-refresh-private"), self.auth())
        request, _ = requester.requests[0]
        self.assertEqual(request.full_url, DEFAULT_URL + "/auth/v1/token?grant_type=refresh_token")
        self.assertEqual(json.loads(request.data), {"refresh_token": "old-refresh-private"})
        self.assertIsNone(request.get_header("Authorization"))

    def test_rpc_requires_access_token_and_sends_only_expected_headers_and_body(self):
        requester = Requester(Response({"ok": True}))
        transport = self.transport(requester)
        with self.assertRaises(TransportError) as raised:
            transport.rpc("pii_contacts")
        self.assertEqual(raised.exception.code, "missing_session")
        self.assertEqual(len(requester.requests), 0)
        transport.set_auth(self.auth())
        self.assertEqual(transport.rpc("pii_lookup", {"p_number": "584093"}), {"ok": True})
        request, _ = requester.requests[0]
        self.assertEqual(request.full_url, DEFAULT_URL + "/rest/v1/rpc/pii_lookup")
        self.assertEqual(request.get_header("Authorization"), "Bearer access-private-value")
        self.assertEqual(request.get_header("Apikey"), PUBLIC_KEY)
        self.assertEqual(json.loads(request.data), {"p_number": "584093"})
        transport.set_auth({})
        self.assertEqual(transport.auth, {})

    def test_invalid_rpc_name_and_request_size_never_reach_network(self):
        requester = Requester(Response({}))
        transport = self.transport(requester)
        transport.set_auth(self.auth())
        for name in ("../auth", "pii_lookup?secret=x", "pii_lookup/other", "other", None):
            with self.subTest(name=name):
                with self.assertRaises(TransportError):
                    transport.rpc(name)
        with self.assertRaises(TransportError) as raised:
            transport.rpc("pii_send", {"payload": "x" * MAX_REQUEST_BYTES})
        self.assertEqual(raised.exception.code, "request_too_large")
        self.assertEqual(requester.requests, [])

    def test_received_ciphertext_response_is_bounded(self):
        requester = Requester(Response(b"x" * (MAX_RESPONSE_BYTES + 1)))
        with self.assertRaises(TransportError) as raised:
            self.transport(requester).sign_up()
        self.assertEqual(raised.exception.code, "response_too_large")

    def test_status_errors_are_categorized_and_do_not_echo_server_details(self):
        cases = [(401, "unauthorized", {}), (403, "forbidden", {}), (429, "rate_limit", {}),
                 (404, "service_unavailable", {}), (503, "service_unavailable", {}),
                 (500, "server_error", {}), (409, "conflict", {}), (302, "redirect", {}),
                 (400, "anonymous_disabled", {"error_code": "anonymous_provider_disabled"}),
                 (400, "captcha_required", {"error_code": "captcha_failed"}),
                 (400, "service_unavailable", {"code": "PGRST202"}),
                 (400, "request_rejected", {})]
        for status, code, extra in cases:
            with self.subTest(status=status, code=code):
                body = json.dumps(extra | {"message": "SECRET_TOKEN_PRIVATE_MESSAGE"}).encode()
                error = HTTPError(DEFAULT_URL, status, "SECRET_TOKEN_PRIVATE_MESSAGE", {}, io.BytesIO(body))
                with self.assertRaises(TransportError) as raised:
                    self.transport(Requester(error=error)).sign_up()
                self.assertEqual(raised.exception.status, status)
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("SECRET_TOKEN", str(raised.exception))

    def test_network_exceptions_do_not_expose_request_values(self):
        for error, code in ((URLError("secret-value"), "connection"),
                            (OSError("secret-value"), "connection"),
                            (socket.timeout("secret-value"), "timeout")):
            with self.subTest(code=code):
                with self.assertRaises(TransportError) as raised:
                    self.transport(Requester(error=error)).sign_up()
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("secret-value", str(raised.exception))

    def test_redirect_handler_never_copies_credentials_to_second_origin(self):
        requester = Requester(Response(self.auth()))
        self.transport(requester).sign_up()
        request, _ = requester.requests[0]
        self.assertIsNone(_NoRedirects().redirect_request(
            request, None, 302, "Found", {}, "https://another.example.org/steal"
        ))

    def test_invalid_json_and_invalid_auth_are_sanitized(self):
        responses = [b"PRIVATE_INVALID_JSON", b"[]", b'"private"', {},
                     self.auth() | {"user": {"id": "not-a-uuid"}},
                     self.auth() | {"access_token": "secret\r\ninjected: yes"},
                     self.auth() | {"access_token": "token-não-ASCII"},
                     self.auth() | {"expires_at": float("nan")},
                     self.auth() | {"expires_at": True}]
        for response in responses:
            with self.subTest(response_type=type(response).__name__):
                with self.assertRaises(TransportError) as raised:
                    self.transport(Requester(Response(response))).sign_up()
                self.assertEqual(raised.exception.code, "invalid_response")
                self.assertNotIn("PRIVATE", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
