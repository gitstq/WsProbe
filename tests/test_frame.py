"""帧编解码层的单元测试。"""

import struct
import unittest

from wsprobe.frame import (
    CLOSE_NORMAL,
    OP_BINARY,
    OP_CLOSE,
    OP_PING,
    OP_TEXT,
    ConnectionClosed,
    Frame,
    MessageAssembler,
    PayloadTooLargeError,
    ProtocolError,
    apply_mask,
    decode_close_payload,
    encode_close_frame,
    encode_frame,
    generate_masking_key,
    read_frame,
)


class FakeSock:
    """最小 socket 替身,仅实现 recv/sendall,用于离线测试解码逻辑。"""

    def __init__(self, data: bytes = b""):
        self.buffer = bytearray(data)
        self.sent = bytearray()
        self.closed = False

    def recv(self, n: int) -> bytes:
        if not self.buffer:
            return b""
        chunk = bytes(self.buffer[:n])
        del self.buffer[:n]
        return chunk

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def close(self) -> None:
        self.closed = True

    def settimeout(self, _timeout) -> None:
        pass

    @property
    def fileno(self):
        return -1


class TestMasking(unittest.TestCase):
    def test_mask_is_self_inverse(self):
        data = bytes(range(64))
        key = generate_masking_key()
        self.assertEqual(len(key), 4)
        self.assertEqual(apply_mask(apply_mask(data, key), key), data)

    def test_empty_payload(self):
        self.assertEqual(apply_mask(b"", b"abcd"), b"")

    def test_mask_changes_payload(self):
        data = b"AAAAAAAA"
        key = b"\x01\x02\x03\x04"
        self.assertNotEqual(apply_mask(data, key), data)


class TestEncodeDecode(unittest.TestCase):
    def roundtrip(self, length: int):
        payload = bytes((i % 251) for i in range(length))
        wire = encode_frame(payload, opcode=OP_BINARY, fin=True, mask=False)
        frame = read_frame(FakeSock(wire))
        self.assertEqual(frame.payload, payload)
        self.assertEqual(frame.opcode, OP_BINARY)
        self.assertTrue(frame.fin)

    def test_length_boundaries(self):
        for length in (0, 1, 125, 126, 127, 65535, 65536, 70000):
            with self.subTest(length=length):
                self.roundtrip(length)

    def test_client_frames_are_masked(self):
        wire = encode_frame(b"secret", opcode=OP_TEXT, fin=True, mask=True)
        first, second = wire[0], wire[1]
        self.assertTrue(second & 0x80, "客户端帧必须设置 MASK 位")
        frame = read_frame(FakeSock(wire))
        self.assertEqual(frame.payload, b"secret")

    def test_header_sizes(self):
        self.assertEqual(len(encode_frame(b"a" * 10, mask=False)) - 10, 2)
        self.assertEqual(len(encode_frame(b"a" * 200, mask=False)) - 200, 4)
        self.assertEqual(len(encode_frame(b"a" * 70000, mask=False)) - 70000, 10)

    def test_fin_bit(self):
        wire = encode_frame(b"x", opcode=OP_TEXT, fin=False, mask=False)
        self.assertEqual(wire[0] & 0x80, 0)


class TestProtocolValidation(unittest.TestCase):
    def test_control_frame_must_not_fragment(self):
        with self.assertRaises(ProtocolError):
            encode_frame(b"x", opcode=OP_PING, fin=False)

    def test_control_frame_payload_limit(self):
        with self.assertRaises(ProtocolError):
            encode_frame(b"x" * 126, opcode=OP_PING)

    def test_rsv_bits_rejected(self):
        wire = bytearray(encode_frame(b"x", opcode=OP_TEXT, mask=False))
        wire[0] |= 0x40  # RSV1
        with self.assertRaises(ProtocolError):
            read_frame(FakeSock(bytes(wire)))

    def test_unknown_opcode_rejected(self):
        wire = bytearray(encode_frame(b"x", opcode=OP_TEXT, mask=False))
        wire[0] = (wire[0] & 0xF0) | 0x5
        with self.assertRaises(ProtocolError):
            read_frame(FakeSock(bytes(wire)))

    def test_fragmented_control_frame_rejected(self):
        wire = bytearray(encode_frame(b"x", opcode=OP_CLOSE, mask=False))
        wire[0] &= 0x7F  # 清除 FIN
        with self.assertRaises(ProtocolError):
            read_frame(FakeSock(bytes(wire)))

    def test_payload_limit_enforced(self):
        wire = encode_frame(b"x" * 500, opcode=OP_BINARY, mask=False)
        with self.assertRaises(PayloadTooLargeError):
            read_frame(FakeSock(wire), max_payload=100)

    def test_truncated_stream_raises_connection_closed(self):
        wire = encode_frame(b"x" * 300, opcode=OP_BINARY, mask=False)
        with self.assertRaises(ConnectionClosed):
            read_frame(FakeSock(wire[:10]))

    def test_invalid_utf8_text_rejected(self):
        wire = encode_frame(b"\xff\xfe", opcode=OP_TEXT, mask=False)
        with self.assertRaises(ProtocolError):
            read_frame(FakeSock(wire))


class TestCloseFrame(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        wire = encode_close_frame(1000, "bye")
        frame = read_frame(FakeSock(wire))
        self.assertEqual(frame.opcode, OP_CLOSE)
        code, reason = decode_close_payload(frame.payload)
        self.assertEqual(code, 1000)
        self.assertEqual(reason, "bye")

    def test_empty_payload(self):
        code, reason = decode_close_payload(b"")
        self.assertIsNone(code)
        self.assertEqual(reason, "")

    def test_1015_cannot_be_sent(self):
        with self.assertRaises(ProtocolError):
            encode_close_frame(1015)

    def test_reason_too_long(self):
        with self.assertRaises(ProtocolError):
            encode_close_frame(CLOSE_NORMAL, "x" * 200)


class TestMessageAssembler(unittest.TestCase):
    def test_fragmented_message(self):
        assembler = MessageAssembler()
        self.assertIsNone(assembler.feed(Frame(opcode=OP_TEXT, payload=b"a", fin=False)))
        self.assertTrue(assembler.in_fragments)
        self.assertIsNone(assembler.feed(Frame(opcode=0x0, payload=b"b", fin=False)))
        merged = assembler.feed(Frame(opcode=0x0, payload=b"c", fin=True))
        self.assertIsNotNone(merged)
        self.assertEqual(merged.payload, b"abc")
        self.assertEqual(merged.opcode, OP_TEXT)
        self.assertFalse(assembler.in_fragments)

    def test_unfragmented_passthrough(self):
        assembler = MessageAssembler()
        merged = assembler.feed(Frame(opcode=OP_TEXT, payload=b"hi", fin=True))
        self.assertEqual(merged.payload, b"hi")

    def test_unexpected_continuation(self):
        assembler = MessageAssembler()
        with self.assertRaises(ProtocolError):
            assembler.feed(Frame(opcode=0x0, payload=b"x", fin=True))

    def test_interleaved_data_frame_rejected(self):
        assembler = MessageAssembler()
        assembler.feed(Frame(opcode=OP_TEXT, payload=b"a", fin=False))
        with self.assertRaises(ProtocolError):
            assembler.feed(Frame(opcode=OP_TEXT, payload=b"b", fin=True))


if __name__ == "__main__":
    unittest.main()
