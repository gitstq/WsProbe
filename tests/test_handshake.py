"""握手层的单元测试。"""

import unittest

from wsprobe import handshake as hs
from wsprobe.frame import ProtocolError


class TestKeyAndAccept(unittest.TestCase):
    def test_generated_key_is_base64_of_16_bytes(self):
        import base64

        key = hs.generate_key()
        self.assertEqual(len(base64.b64decode(key)), 16)
        self.assertTrue(key.endswith("=="))

    def test_rfc6455_reference_vector(self):
        # RFC 6455 第 1.3 节给出的示例向量
        self.assertEqual(
            hs.compute_accept("dGhlIHNhbXBsZSBub25jZQ=="),
            "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        )

    def test_verify_accept(self):
        key = hs.generate_key()
        self.assertTrue(hs.verify_accept(key, hs.compute_accept(key)))
        self.assertFalse(hs.verify_accept(key, "bogus"))
        self.assertFalse(hs.verify_accept(key, None))


class TestURLParsing(unittest.TestCase):
    def test_plain_ws(self):
        url = hs.WebSocketURL("ws://example.com/chat")
        self.assertEqual(url.host, "example.com")
        self.assertEqual(url.port, 80)
        self.assertEqual(url.path, "/chat")
        self.assertFalse(url.secure)

    def test_secure_wss_default_port(self):
        url = hs.WebSocketURL("wss://example.com/stream")
        self.assertTrue(url.secure)
        self.assertEqual(url.port, 443)

    def test_scheme_is_optional(self):
        url = hs.WebSocketURL("localhost:9000/app")
        self.assertEqual(url.scheme, "ws")
        self.assertEqual(url.port, 9000)

    def test_http_scheme_normalized(self):
        self.assertEqual(hs.WebSocketURL("https://a.io/x").scheme, "wss")
        self.assertEqual(hs.WebSocketURL("http://a.io/x").scheme, "ws")

    def test_query_preserved(self):
        url = hs.WebSocketURL("ws://h.io/p?token=abc")
        self.assertEqual(url.path, "/p?token=abc")

    def test_unsupported_scheme(self):
        with self.assertRaises(hs.HandshakeError):
            hs.WebSocketURL("ftp://h.io/p")

    def test_origin_header(self):
        self.assertEqual(hs.WebSocketURL("ws://h.io:81/p").origin, "http://h.io:81")
        self.assertEqual(hs.WebSocketURL("wss://h.io/p").origin, "https://h.io")


class TestUpgradeRequest(unittest.TestCase):
    def setUp(self):
        self.url = hs.WebSocketURL("ws://example.com:8080/echo")
        self.key = "dGhlIHNhbXBsZSBub25jZQ=="

    def test_required_headers(self):
        raw = hs.build_upgrade_request(self.url, self.key).decode()
        self.assertIn("GET /echo HTTP/1.1", raw)
        self.assertIn("Host: example.com:8080", raw)
        self.assertIn("Upgrade: websocket", raw)
        self.assertIn("Connection: Upgrade", raw)
        self.assertIn(f"Sec-WebSocket-Key: {self.key}", raw)
        self.assertIn("Sec-WebSocket-Version: 13", raw)
        self.assertTrue(raw.endswith("\r\n\r\n"))

    def test_custom_headers_and_subprotocols(self):
        raw = hs.build_upgrade_request(
            self.url,
            self.key,
            headers={"Authorization": "Bearer t"},
            subprotocols=["json", "msgpack"],
        ).decode()
        self.assertIn("Authorization: Bearer t", raw)
        self.assertIn("Sec-WebSocket-Protocol: json, msgpack", raw)


class TestResponseParsing(unittest.TestCase):
    def test_parse_101(self):
        buffer = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n"
        )
        status, reason, headers, leftover = hs.parse_http_response(buffer)
        self.assertEqual(status, 101)
        self.assertEqual(reason, "Switching Protocols")
        self.assertEqual(headers["sec-websocket-accept"], "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")
        self.assertEqual(leftover, b"")

    def test_headers_are_lowercased(self):
        buffer = b"HTTP/1.1 200 OK\r\nX-Mixed-Case: v\r\n\r\n"
        _, _, headers, _ = hs.parse_http_response(buffer)
        self.assertIn("x-mixed-case", headers)

    def test_check_upgrade_response_ok(self):
        headers = {
            "upgrade": "websocket",
            "connection": "Upgrade",
            "sec-websocket-accept": hs.compute_accept("abc"),
            "sec-websocket-protocol": "json",
        }
        result = hs.check_upgrade_response(headers, "abc")
        self.assertTrue(result["accept_valid"])
        self.assertEqual(result["protocol"], "json")

    def test_missing_upgrade_header(self):
        with self.assertRaises(hs.HandshakeError):
            hs.check_upgrade_response({"connection": "upgrade"}, "abc")

    def test_missing_connection_token(self):
        with self.assertRaises(hs.HandshakeError):
            hs.check_upgrade_response({"upgrade": "websocket", "connection": "keep-alive"}, "abc")

    def test_accept_mismatch(self):
        headers = {
            "upgrade": "websocket",
            "connection": "upgrade",
            "sec-websocket-accept": "wrong",
        }
        with self.assertRaises(hs.HandshakeError):
            hs.check_upgrade_response(headers, "abc")

    def test_non_strict_mode_tolerates_bad_accept(self):
        headers = {"upgrade": "websocket", "connection": "upgrade", "sec-websocket-accept": "bad"}
        result = hs.check_upgrade_response(headers, "abc", strict=False)
        self.assertFalse(result["accept_valid"])


if __name__ == "__main__":
    unittest.main()
