"""端到端测试:用内置自研服务端验证完整链路。"""

import json
import os
import socket
import tempfile
import threading
import time
import unittest

from wsprobe.client import WebSocketClient
from wsprobe.filters import MessageFilter
from wsprobe.server import WsEchoServer
from wsprobe.session import Recorder, load_records
from wsprobe.script import ScriptError, run_script


def free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class ServerFixture(unittest.TestCase):
    """每个用例启动一个独立的内置服务端。"""

    def setUp(self):
        self.port = free_port()
        self.server = WsEchoServer(host="127.0.0.1", port=self.port, verbose=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.25)
        self.url = f"ws://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)


class TestHandshakeE2E(ServerFixture):
    def test_101_and_accept(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            report = ws.handshake_report()
            self.assertEqual(report["status"], 101)
            self.assertTrue(report["negotiated"]["accept_valid"])

    def test_bad_path_still_upgrades(self):
        # 内置服务端不校验 path,任何路径都应握手成功
        with WebSocketClient(f"{self.url}/anywhere", timeout=5) as ws:
            self.assertEqual(ws.response_status, 101)

    def test_connection_refused(self):
        dead_port = free_port()
        with self.assertRaises(Exception):
            WebSocketClient(f"ws://127.0.0.1:{dead_port}", timeout=2).connect()


class TestMessaging(ServerFixture):
    def test_text_echo(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            ws.send_text("hello")
            self.assertEqual(ws.recv(timeout=5).text, "hello")

    def test_json_echo(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            ws.send_json({"cmd": "ping", "id": 7})
            self.assertEqual(ws.recv(timeout=5).json["id"], 7)

    def test_binary_echo(self):
        payload = bytes(range(256))
        with WebSocketClient(self.url, timeout=5) as ws:
            ws.send_binary(payload)
            message = ws.recv(timeout=5)
            self.assertTrue(message.is_binary)
            self.assertEqual(message.data, payload)

    def test_large_payload(self):
        payload = "Z" * 70000
        with WebSocketClient(self.url, timeout=15) as ws:
            ws.send_text(payload)
            self.assertEqual(len(ws.recv(timeout=15).data), 70000)

    def test_fragmented_send(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            ws.send_fragmented([b"frag", b"-", b"ok"])
            self.assertEqual(ws.recv(timeout=5).text, "frag-ok")

    def test_multiple_roundtrips(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            for index in range(10):
                ws.send_text(f"msg-{index}")
                self.assertEqual(ws.recv(timeout=5).text, f"msg-{index}")


class TestHeartbeatAndClose(ServerFixture):
    def test_ping_pong(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            rtt = ws.ping(timeout=5)
            self.assertIsNotNone(rtt)
            self.assertGreaterEqual(rtt, 0)

    def test_close_handshake(self):
        ws = WebSocketClient(self.url, timeout=5)
        ws.connect()
        ws.close(code=1000, reason="done")
        self.assertEqual(ws.close_code, 1000)

    def test_stats_after_session(self):
        with WebSocketClient(self.url, timeout=5) as ws:
            ws.send_text("a")
            ws.recv(timeout=5)
            ws.stats.finish()
            report = ws.stats.to_dict()
            self.assertEqual(report["messages_received"], 1)
            self.assertEqual(report["messages_sent"], 1)


class TestRecorder(ServerFixture):
    def test_record_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "session.jsonl")
            with Recorder(path) as recorder:
                recorder.write_meta({"url": self.url})
                with WebSocketClient(self.url, timeout=5) as ws:
                    ws.send_text("recorded")
                    recorder.write(ws.recv(timeout=5))
            records = load_records(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"], "recorded")


class TestScriptRunner(ServerFixture):
    def test_script_success(self):
        script = {
            "url": self.url,
            "steps": [
                {"action": "send", "data": "hello"},
                {"action": "expect", "filter": '$ ~ "hello"', "timeout": 5},
                {"action": "ping"},
                {"action": "close"},
            ],
        }
        result = run_script(script, verbose=False)
        self.assertTrue(result["success"], result["failures"])

    def test_script_failure_on_timeout(self):
        script = {
            "url": self.url,
            "steps": [
                {"action": "expect", "filter": '$ ~ "never-appears"', "timeout": 1},
            ],
        }
        result = run_script(script, verbose=False)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["failures"]), 1)

    def test_invalid_action_rejected(self):
        from wsprobe.script import validate_script

        with self.assertRaises(ScriptError):
            validate_script({"steps": [{"action": "explode"}]})


if __name__ == "__main__":
    unittest.main()
