"""过滤表达式的单元测试。"""

import unittest

from wsprobe.client import Message
from wsprobe.filters import MessageFilter, FilterError, resolve_path, _tokenize_path


class SimpleMessage:
    """鸭子类型消息替身,只需暴露 data 属性。"""

    def __init__(self, data):
        self.data = data


class TestPath(unittest.TestCase):
    def test_tokenize(self):
        self.assertEqual(_tokenize_path("a.b[0].c"), [("key", "a"), ("key", "b"), ("index", 0), ("key", "c")])
        self.assertEqual(_tokenize_path("items[*]"), [("key", "items"), ("index", "*")])

    def test_root_path_is_empty(self):
        self.assertEqual(_tokenize_path("$"), [])
        self.assertEqual(_tokenize_path(""), [])

    def test_resolve_nested(self):
        data = {"a": {"b": [10, 20]}}
        self.assertEqual(resolve_path(data, _tokenize_path("a.b[1]")), [20])

    def test_resolve_wildcard(self):
        data = {"items": [{"id": 1}, {"id": 2}]}
        self.assertEqual(resolve_path(data, _tokenize_path("items[*].id")), [1, 2])

    def test_missing_path_returns_empty(self):
        self.assertEqual(resolve_path({"a": 1}, _tokenize_path("b.c")), [])


class TestOperators(unittest.TestCase):
    def check(self, expression, payload, expected):
        self.assertEqual(MessageFilter(expression).match(SimpleMessage(payload)), expected)

    def test_greater_than(self):
        self.check("price > 100", {"price": 150}, True)
        self.check("price > 100", {"price": 50}, False)

    def test_equality_string(self):
        self.check('status == "error"', {"status": "error"}, True)
        self.check('status == "error"', {"status": "ok"}, False)

    def test_inequality(self):
        self.check("level != 3", {"level": 4}, True)

    def test_contains(self):
        self.check('text ~ "timeout"', {"text": "connect timeout"}, True)

    def test_prefix_and_suffix(self):
        self.check('name ^ "ws"', {"name": "wsprobe"}, True)
        self.check('name $ "probe"', {"name": "wsprobe"}, True)

    def test_boolean_literals(self):
        self.check("ok == true", {"ok": True}, True)

    def test_type_mismatch_is_not_match(self):
        # 字符串与数字比较不应抛异常,而应判为不匹配
        self.check("age > 10", {"age": "unknown"}, False)


class TestOnMessages(unittest.TestCase):
    def test_json_text_message(self):
        message = Message(opcode=0x1, data=b'{"type":"tick","value":7}', direction="in")
        self.assertTrue(MessageFilter("value >= 5").match(message))
        self.assertFalse(MessageFilter("value >= 9").match(message))

    def test_plain_text_message(self):
        message = Message(opcode=0x1, data=b"connection timeout", direction="in")
        self.assertTrue(MessageFilter('$ ~ "timeout"').match(message))

    def test_empty_filter_matches_everything(self):
        message = Message(opcode=0x1, data=b"anything", direction="in")
        self.assertTrue(MessageFilter("").match(message))

    def test_existence_only(self):
        message = Message(opcode=0x1, data=b'{"error":{"code":5}}', direction="in")
        self.assertTrue(MessageFilter("error.code").match(message))
        self.assertFalse(MessageFilter("error.detail").match(message))


if __name__ == "__main__":
    unittest.main()
