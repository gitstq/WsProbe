<div align="center">

# 🔭 WsProbe

**零依赖 WebSocket 调试探针 · 自带 RFC 6455 全协议栈**

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![RFC](https://img.shields.io/badge/RFC-6455-orange)

</div>

---

## 🎉 项目介绍

**WsProbe** 是一个用于调试 WebSocket 服务的命令行探针与 Python 库。它的特别之处只有一句话:

> **整个 WebSocket 协议栈(RFC 6455)都是自己实现的,运行时不依赖任何第三方库。**

不装 `websockets`,不装 `websocket-client`,不装 `aiohttp`、`requests`、`numpy`。
只需要一个 Python 3.8+ 解释器,把仓库拉下来就能跑——在内网、离线环境、最小化容器里同样如此。

### 🤔 它解决了什么痛点

| # | 痛点 | WsProbe 的应对 |
|---|------|----------------|
| 1 | 🔌 WebSocket 缺少「curl 级」的趁手工具,调试全靠写临时脚本 | 一条命令连接、发送、过滤、录制 |
| 2 | 📦 现有工具依赖沉重,离线 / 内网环境根本装不上 | **运行时零依赖**,仅用标准库 |
| 3 | 🕶️ 握手失败是黑盒,只知道「连不上」,不知道为什么 | `inspect` 输出状态码、请求 Key、Accept 校验结果、解析 IP |
| 4 | 🌊 订阅流每秒几十条推送,关心的那一条淹没在里面 | 内置过滤 DSL,`--filter '$.price > 100'` |
| 5 | 🔁 联调过程无法复现,问题「刚刚还在」 | 录制为 JSONL,随时原速 / 加速回放 |
| 6 | 🧪 WebSocket 接口无法像 HTTP 那样做回归测试 | 声明式 JSON 脚本,可进 CI,失败即非零退出码 |
| 7 | 📊 「有点慢」说不清慢在哪 | `bench` 给出吞吐与 P50 / P95 / P99 延迟分位数 |

### 💎 自研差异化亮点

* 🧬 **协议栈 100% 自研**:帧编解码、XOR 掩码、扩展长度(7/16/64bit)、分片重组、握手 Accept 计算、心跳、关闭握手——逐字节手写,不是对第三方库的封装。
* 🎯 **双向自研**:客户端和**服务端**都是自己实现的。内置 `wsprobe serve` 既是演示靶机,也是端到端测试的基础设施。
* 🔍 **自研过滤表达式**:不引入 jsonpath / JMESPath,自己实现路径 + 通配符 + 比较运算符的迷你查询语言。
* 🩺 **可观测**:握手诊断、RTT 测量、字节/消息计数、延迟分位数,全部内置。
* 🔌 **既是 CLI 也是库**:`from wsprobe import WebSocketClient` 即可嵌入你自己的程序。

### 🌱 灵感来源

WsProbe 的思路来自三个工具的融合:**curl**(命令行的直接)、**tcpdump**(流量可录制可回放)、**wscat**(交互式会话),
并把它们压缩进一个零依赖、可审计、可在 CI 中运行的纯 Python 包里。

> 📸 *演示截图 / 动图占位:成功运行后在此处补充终端录制动图。*

---

## ✨ 核心特性

### 🧬 协议层(全部自研)

* ✅ **完整帧编解码**:FIN / RSV / opcode / MASK / 7-16-64bit 扩展负载长度
* ✅ **客户端掩码**:CSPRNG 生成 4 字节掩码,XOR 运算自反可逆
* ✅ **分片重组**:continuation 帧拼接,并校验「数据帧不得交错」等协议约束
* ✅ **握手**:`Sec-WebSocket-Key` 生成、`Sec-WebSocket-Accept` SHA-1 + GUID 计算与校验
* ✅ **心跳**:主动 PING 测 RTT;**自动回应**服务端 PING(RFC 强制要求)
* ✅ **关闭握手**:发送 close → 等待对端 close → 关闭 TCP,并解析状态码与原因
* ✅ **协议守卫**:RSV 位、未知 opcode、分片控制帧、非法 UTF-8、超长负载全部拦截
* ✅ **TLS / 代理**:`wss://` 与 HTTP CONNECT 代理隧道

### 🛠️ 工具层

* 🔭 **`connect`**:连接、发送、过滤、录制,支持交互 REPL 模式
* 🩺 **`inspect`**:只做握手,输出完整诊断报告
* 📈 **`bench`**:并发压测,吞吐 + P50/P95/P99
* 🎬 **`script`**:声明式 JSON 脚本(send / expect / wait / sleep / ping / close)
* ♻️ **`replay`**:把录制文件重放到任意目标
* 🖥️ **`serve`**:内置回显 / 定时推送 / 广播服务器
* 🧪 **`selftest`**:10 项协议自检,一条命令验证环境
* 🎨 **输出友好**:彩色高亮、JSON Lines、hexdump、`--no-color` 降级

---

## 🚀 快速开始

### 📋 环境要求

| 项目 | 要求 |
|------|------|
| Python | **>= 3.8**(仅标准库) |
| 第三方依赖 | **无** |
| 操作系统 | Windows / macOS / Linux |
| 网络 | 出站 TCP;如需代理用 `--proxy` |

### 📦 安装

```bash
# 方式一:pip 安装(推荐)
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe
pip install .

# 方式二:免安装,直接用模块方式运行
python -m wsprobe --help
```

安装后命令行入口为 `wsprobe`。

### ⚡ 三步体验

**第一步** 开一个终端,启动内置服务器(每秒推送一条消息):

```bash
wsprobe serve --port 8765 --pump 1
```

**第二步** 另开一个终端,连上去看看:

```bash
wsprobe ws://127.0.0.1:8765
```

你会看到类似输出:

```
✓ HTTP 101 Switching Protocols · 127.0.0.1:8765 (127.0.0.1)
[10:32:01] ← {"type": "pump", "seq": 1, "ts": 1793290921.1, "value": 12.33}
[10:32:02] ← {"type": "pump", "seq": 2, "ts": 1793290922.1, "value": 24.67}
```

**第三步** 只留下你关心的消息:

```bash
wsprobe ws://127.0.0.1:8765 --filter '$.value > 20' --count 5 --stats
```

> 💡 没有现成的 WebSocket 服务?`wsprobe serve` 就是为这个场景准备的。

---

## 📖 详细使用指南

### 🗂️ 子命令一览

| 命令 | 作用 | 典型用法 |
|------|------|----------|
| `connect` | 连接并收发消息(默认,可省略) | `wsprobe ws://host/p --send hi` |
| `inspect` | 只做握手并输出诊断 | `wsprobe inspect wss://host/p` |
| `bench` | 并发压测 | `wsprobe bench ws://host -c 20 -m 200` |
| `script` | 执行声明式脚本 | `wsprobe script flow.json` |
| `replay` | 回放录制文件 | `wsprobe replay rec.jsonl --to ws://host` |
| `serve` | 启动内置服务器 | `wsprobe serve --port 8765 --pump 1` |
| `selftest` | 协议自检 | `wsprobe selftest` |

### 🔭 连接与发送

```bash
# 连接后进入交互模式(输入即发送,/quit 退出)
wsprobe ws://127.0.0.1:8765

# 发送一条文本并接收 1 条响应
wsprobe ws://127.0.0.1:8765 --send '{"cmd":"ping"}' --count 1

# 连续发送多条,每条间隔 0.5 秒
wsprobe ws://127.0.0.1:8765 --send a --send b --send-interval 0.5

# 从文件读取内容发送
wsprobe ws://127.0.0.1:8765 --send-file payload.json

# 持续监听 30 秒
wsprobe ws://127.0.0.1:8765 --duration 30

# 自定义请求头 / 子协议 / 代理 / 跳过证书校验
wsprobe wss://host/p \
  --header "Authorization: Bearer TOKEN" \
  --subprotocol json \
  --proxy http://127.0.0.1:7890 \
  --insecure
```

**交互模式内置命令:**

| 输入 | 作用 |
|------|------|
| `任意文本` | 作为文本帧发送 |
| `/ping` | 测量一次往返时延 |
| `/wait 3` | 静默接收 3 秒内的所有消息 |
| `/stats` | 打印当前会话统计 |
| `/quit` | 关闭连接并退出 |

### 🔍 过滤表达式

语法是 `<路径> [<运算符> <值>]`:

| 表达式 | 含义 |
|--------|------|
| `$.price > 100` | 顶层 `price` 大于 100 |
| `data.status == "error"` | 嵌套字段等于 `error` |
| `items[*].id` | 数组中任意元素存在 `id` 字段 |
| `text ~ "timeout"` | 文本包含 `timeout` |
| `name ^ "ws"` | 以 `ws` 开头 |
| `name $ "probe"` | 以 `probe` 结尾 |

支持的运算符:`==` `!=` `>` `>=` `<` `<=` `~`(包含) `^`(前缀) `$`(后缀)。
文本消息会先尝试按 JSON 解析,解析失败则作为纯字符串处理;类型不可比时判为「不匹配」而不会报错。

### 🎬 录制与回放

```bash
# 录制(所有流量写入 JSONL,与是否命中过滤无关)
wsprobe ws://host/p --duration 60 --record session.jsonl

# 查看录制内容而不真正发送
wsprobe replay session.jsonl --preview

# 原速重放到另一个地址
wsprobe replay session.jsonl --to ws://staging-host/p

# 2 倍速重放;--speed 0 表示全速不等间隔
wsprobe replay session.jsonl --to ws://host/p --speed 2
```

JSONL 每行形如:

```json
{"ts": 1793290921.106, "dir": "in", "op": "text", "size": 64, "data": "{\"type\":\"pump\"}"}
```

### 🧪 声明式脚本(可用于 CI)

```json
{
  "url": "ws://127.0.0.1:8765",
  "steps": [
    { "action": "send",   "data": { "cmd": "subscribe", "channel": "ticker" } },
    { "action": "expect", "filter": "cmd == \"subscribe\"", "timeout": 5 },
    { "action": "sleep",  "seconds": 0.5 },
    { "action": "wait",   "count": 3, "timeout": 10 },
    { "action": "ping" },
    { "action": "close" }
  ]
}
```

```bash
wsprobe script flow.json --json     # 机器可读输出,便于 CI 断言
```

全部步骤通过时退出码为 `0`,任何一步失败即为 `1`,可直接接在流水线里做回归门禁。

### 📈 压测

```bash
wsprobe bench ws://127.0.0.1:8765 --connections 20 --messages 200 --payload 128
```

```
url                     : ws://127.0.0.1:8765
connections             : 20
messages_per_connection : 200
completed               : 4000
errors                  : 0
throughput_msg_per_s    : 6098.68
latency_p50_ms          : 0.364
latency_p95_ms          : 0.932
latency_p99_ms          : 1.022
```

### 🩺 握手诊断

```bash
wsprobe inspect wss://echo.example.com
```

```
HTTP 101 Switching Protocols
  目标    : wss://echo.example.com
  解析 IP : 93.184.216.34
  请求 Key: xUFq46M2kCNjLVU859PCwQ==
  预期 Acc: HN2CMetJ8CJC/UA3cp1YIJXqG9Y=
  Accept  : HN2CMetJ8CJC/UA3cp1YIJXqG9Y= (校验通过)
  首包 RTT: 42.15 ms
```

连不上时,这一段就是定位问题的第一手材料:状态码不是 101?Accept 校验失败?还是 TLS / 代理的问题?

### 🐍 作为库使用

```python
from wsprobe import WebSocketClient
from wsprobe.filters import MessageFilter

matcher = MessageFilter("value >= 10")

with WebSocketClient("ws://127.0.0.1:8765", timeout=5) as ws:
    ws.send_json({"cmd": "subscribe", "channel": "ticker"})
    for message in ws.iter_messages(count=100, timeout=10):
        if matcher.match(message):
            print(message.json)

    rtt = ws.ping()          # 往返时延(秒)
    print(ws.stats.to_dict())
```

更多用法见 [`examples/library_usage.py`](examples/library_usage.py)。

### ❓ 常见问题

<details>
<summary><b>握手失败,提示 HTTP 4xx / 5xx 怎么办?</b></summary>

先用 `wsprobe inspect <url>` 看状态码与响应头。401/403 通常是鉴权头缺失(加 `--header`),
404 通常是 path 不对,301/302 需要换成重定向后的地址。
</details>

<details>
<summary><b>报 <code>Sec-WebSocket-Accept verification failed</code>?</b></summary>

说明对端返回的 Accept 与标准算法不符(常见于被中间设备拦截,或对方并非真正的 WebSocket 服务)。
确认目标无误后,可用 `--no-strict-accept` 跳过校验继续排查。
</details>

<details>
<summary><b>需要走公司代理?</b></summary>

用 `--proxy http://host:port`,WsProbe 会先发 HTTP CONNECT 建立隧道,再在其上完成 TLS 与握手。
</details>

<details>
<summary><b>自签名证书报错?</b></summary>

加 `--insecure` 跳过证书校验(仅建议在内网调试时使用)。
</details>

<details>
<summary><b>消息太大被拒?</b></summary>

默认单消息上限 64 MiB,可用 `--max-payload` 调整。这是防止被恶意服务端耗尽内存的保护机制。
</details>

---

## 💡 设计思路与迭代规划

### 🏗️ 分层架构

```
┌──────────────────────────────────────────────┐
│  cli.py        命令解析、输出渲染、REPL        │  ← 应用层
├──────────────────────────────────────────────┤
│  script.py / session.py / stats.py / filters  │  ← 能力层(脚本、录制、统计、过滤)
├──────────────────────────────────────────────┤
│  client.py     连接状态机、心跳、关闭握手      │  ← 会话层
├──────────────────────────────────────────────┤
│  handshake.py  HTTP Upgrade / Key / Accept    │  ← 握手层
├──────────────────────────────────────────────┤
│  frame.py      RFC 6455 帧编解码 / 掩码 / 分片 │  ← 协议层(最核心的自研部分)
└──────────────────────────────────────────────┘
```

### 🤔 关键设计决策

| 决策 | 原因 |
|------|------|
| **零第三方依赖** | 调试工具必须能在最糟糕的环境里跑起来——内网、离线、最小化容器。依赖越少,可用性越高 |
| **阻塞式 socket + 线程** | 不引入 asyncio 复杂度;调试场景下阻塞模型行为更可预测,超时语义更清晰 |
| **掩码用大整数异或** | 逐字节 Python 循环在 64KB 负载上很慢,`int.from_bytes` 一次性异或可快一个数量级 |
| **过滤 DSL 自己实现** | jsonpath / JMESPath 语法重、依赖大;调试场景只需要路径 + 比较,自己实现更轻且更可控 |
| **内置服务端** | 让工具自带「靶机」:既是零门槛演示,也让端到端测试不依赖外网 |
| **脚本失败即非零退出码** | 让 WebSocket 接口能像 HTTP 一样纳入 CI 门禁 |

### 🗺️ 后续迭代规划

* [ ] 🔐 支持 WebSocket 压缩扩展 `permessage-deflate` 的探测与协商
* [ ] 🧩 插件式消息编解码器(Protobuf / MessagePack 需要时可选装)
* [ ] 📊 HTML 可视化报告(把录制文件渲染成时间线图)
* [ ] 🔄 自动重连与指数退避(`--reconnect`)
* [ ] 🌐 SOCKS5 代理支持
* [ ] 🧵 异步客户端(asyncio 版本,可选依赖)
* [ ] 📦 发布到 PyPI

### 🤝 社区贡献方向

最欢迎的三类贡献:**更多真实服务端场景的兼容性验证**、**过滤 DSL 的表达能力增强**、**文档与示例的本地化**。

---

## 📦 打包与部署指南

WsProbe 属于**工具库 / CLI 类项目**,因此**不需要**发布二进制 Release 附件;按下方方式安装即可零门槛使用。

### 🐍 方式一:pip 安装(推荐)

```bash
pip install .
# 或开发模式(改动即时生效)
pip install -e .
```

安装后获得两个入口:

* 命令行:`wsprobe --help`
* 库导入:`from wsprobe import WebSocketClient`

### 📄 方式二:免安装运行

```bash
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe
python -m wsprobe --help       # 等价于 wsprobe --help
```

由于零依赖,也可以直接把 `wsprobe/` 目录拷进你的项目里使用。

### 🧊 方式三:打包为单文件可执行程序(可选)

需要无依赖可执行文件时,用 PyInstaller:

```bash
pip install pyinstaller
./scripts/build.sh              # 产物在 dist/wsprobe,并生成 .sha256 校验和
./scripts/build.sh clean        # 清理
```

> ⚠️ PyInstaller **不支持交叉编译**。生成 Windows / macOS 产物需要在对应系统上执行
> (或使用该系统的 CI runner,见 `.github/workflows/release.yml`)。

### 🌍 兼容环境

| 环境 | 状态 |
|------|------|
| Python 3.8 / 3.9 / 3.10 / 3.11 / 3.12 | ✅ 支持 |
| Windows 10+ / macOS 11+ / Linux | ✅ 支持 |
| 离线 / 内网环境 | ✅ 支持(零依赖) |
| Docker 最小化镜像(如 `python:3.11-slim`) | ✅ 支持 |

### 🧪 验证安装

```bash
wsprobe selftest
```

10 项协议自检全部通过即表示环境正常。

---

## 🤝 贡献指南

### 🔀 Pull Request 规范

1. Fork 本仓库并创建特性分支:`git checkout -b feat/your-feature`
2. 提交信息遵循 **Angular 规范**:

   ```
   feat: 新增 xxx 功能
   fix: 修复 xxx 问题
   docs: 更新 xxx 文档
   refactor: 重构 xxx 模块
   test: 补充 xxx 测试
   chore: 调整构建配置
   ```

3. 新增代码请**保持零第三方依赖**这一核心约束(测试依赖除外)
4. 补充或更新对应的单元测试,并确保全部通过:

   ```bash
   python -m unittest discover tests
   wsprobe selftest
   ```

5. 如果改动涉及命令行行为,请同步更新**三个语言版本**的 README

### 🐛 Issue 反馈规则

提交 Issue 时请尽量包含:

* WsProbe 版本(`wsprobe --version`)与 Python 版本
* 操作系统
* 复现命令(可脱敏的目标地址)
* `wsprobe inspect <url>` 的完整输出
* 期望行为与实际行为

### 🧭 代码风格

* 遵循 PEP 8,公开接口带 docstring
* 协议层改动必须配套单元测试(协议错误往往只在极端输入下暴露)
* 保持模块单一职责:`frame.py` 只管字节,`client.py` 只管会话

---

## 📄 开源协议说明

本项目采用 **MIT License** 开源协议,完整条款见 [LICENSE](LICENSE)。

* ✅ 允许商用、修改、分发、私有化使用
* ✅ 允许用于闭源项目
* ⚠️ 需保留原始版权声明与许可声明
* ❌ 作者不对软件的适用性作任何担保

---

<div align="center">

**🔭 WsProbe —— 把 WebSocket 的黑盒,变成看得见的字节。**

Made with ❤️ by WsProbe Contributors

</div>
