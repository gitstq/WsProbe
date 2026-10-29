"""轻量级消息过滤表达式(自研 DSL,零依赖)。

WebSocket 调试时往往只关心海量推送中的一小部分(例如价格大于某个阈值、
状态字段变成 ``error``)。WsProbe 提供了一种极简的查询语法,无需引入
jsonpath / JMESPath 等重型依赖:

语法::

    <path> [<operator> <value>]

* ``path`` 支持点号字段、数组下标、通配符:``data.items[0].price``、``items[*].id``
* 省略 path(写作 ``$``)表示对整条消息(文本或原始对象)进行操作
* 支持的运算符:``==`` ``!=`` ``>`` ``>=`` ``<`` ``<=`` ``~``(包含)``^``(前缀)``$``(后缀)
* 文本消息会先尝试按 JSON 解析,失败则作为纯字符串处理

示例::

    $.price > 100
    data.status == "error"
    text ~ "timeout"
    items[*].id
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+|\*)\]")
_OPERATOR_RE = re.compile(r"(==|!=|>=|<=|>|<|~|\^|\$)")


class FilterError(ValueError):
    """过滤表达式语法错误。"""


def _tokenize_path(path: str) -> List:
    """把路径字符串切成 ``('key', name)`` / ``('index', int|'*')`` 标记序列。"""
    if path in ("", "$", "$."):
        return []
    # 去掉根路径符 "$" / "$.",它只是语法糖,不是真实字段名
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    tokens: List = []
    for match in _PATH_TOKEN.finditer(path):
        name, index = match.group(1), match.group(2)
        if name is not None:
            tokens.append(("key", name))
        elif index == "*":
            tokens.append(("index", "*"))
        else:
            tokens.append(("index", int(index)))
    if not tokens:
        raise FilterError(f"invalid path expression: {path!r}")
    return tokens


def resolve_path(data: Any, tokens: List) -> List[Any]:
    """沿路径取值,返回所有命中值(通配符会产生多个结果)。"""
    current: List[Any] = [data]
    for kind, token in tokens:
        nxt: List[Any] = []
        for node in current:
            if kind == "key":
                if isinstance(node, dict) and token in node:
                    nxt.append(node[token])
            else:  # index
                if isinstance(node, list):
                    if token == "*":
                        nxt.extend(node)
                    elif isinstance(token, int) and -len(node) <= token < len(node):
                        nxt.append(node[token])
        current = nxt
        if not current:
            break
    return current


def _coerce(value: str) -> Any:
    """把表达式右侧的字面量转成 Python 值(支持 quoted 字符串/数字/布尔/null)。"""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "none"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _compare(left: Any, operator: str, right: Any) -> bool:
    try:
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == "~":
            return str(right) in str(left)
        if operator == "^":
            return str(left).startswith(str(right))
        if operator == "$":
            return str(left).endswith(str(right))
    except TypeError:
        # 类型不可比(例如 str 与 int 比较)时视为不匹配,而不是崩溃
        return False
    raise FilterError(f"unsupported operator: {operator!r}")


class MessageFilter:
    """编译后的消息过滤器。"""

    def __init__(self, expression: str):
        self.expression = expression.strip()
        self.path_tokens: List = []
        self.operator: Optional[str] = None
        self.value: Any = None
        self._parse()

    def _parse(self) -> None:
        if not self.expression:
            return
        expr = self.expression
        # 根路径符 "$" 与后缀运算符 "$" 同形:先跳过开头的根路径符,再搜索运算符
        if expr.startswith("$."):
            prefix = 2
        elif expr.startswith("$"):
            prefix = 1
        else:
            prefix = 0
        match = _OPERATOR_RE.search(expr, prefix)
        if match:
            path_part = expr[: match.start()].strip()
            self.operator = match.group(1)
            self.value = _coerce(expr[match.end():])
        else:
            path_part = expr
        self.path_tokens = _tokenize_path(path_part)

    @property
    def is_empty(self) -> bool:
        return not self.expression

    def match(self, message: "Any") -> bool:
        """判断消息是否命中过滤条件。

        :param message: :class:`wsprobe.client.Message` 或任意 Python 对象
        """
        if self.is_empty:
            return True
        payload = _payload_of(message)
        if self.operator is None:
            return bool(resolve_path(payload, self.path_tokens))
        for candidate in resolve_path(payload, self.path_tokens) or [None]:
            if _compare(candidate, self.operator, self.value):
                return True
        return False


def _payload_of(message: Any) -> Any:
    """从消息对象中提取可查询的负载(优先 JSON 解析后的对象)。"""
    raw = getattr(message, "data", message)
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped[:1] in ("{", "["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return raw
        return raw
    return raw
