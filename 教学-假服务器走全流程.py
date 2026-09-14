"""
教学用假服务器：冒充 DeepSeek，把"客户端到底发了什么"完整录下来。

它做的事和真服务器一模一样：监听一个端口、收 HTTP POST、回一段 JSON。
区别只是它不做推理，而是把那 3 步原样报告出来。
"""

import io
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

收到的请求 = []


class 假DeepSeek(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        长度 = int(self.headers.get("Content-Length", 0))
        原始字节 = self.rfile.read(长度)
        原始文本 = 原始字节.decode("utf-8")

        收到的请求.append(
            {
                "方法": "POST",
                "路径": self.path,
                "请求头": dict(self.headers),
                "原始请求体": 原始文本,
            }
        )

        请求 = json.loads(原始文本)
        消息列表 = 请求["messages"]

        角色们 = []
        for m in 消息列表:
            角色们.append(m["role"])

        最后一句话 = ""
        for m in 消息列表:
            if m["role"] == "user":
                最后一句话 = m.get("content") or ""

        回复文本 = (
            "我收到了 " + str(len(消息列表)) + " 条消息，"
            "角色依次是 " + " → ".join(角色们) + "。"
            "你说的最后一句是：「" + 最后一句话 + "」"
        )

        响应 = {
            "id": "chatcmpl-fake-0001",
            "object": "chat.completion",
            "created": 1757800000,
            "model": 请求["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": 回复文本},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 31,
                "completion_tokens": 12,
                "total_tokens": 43,
            },
        }

        响应字节 = json.dumps(响应, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(响应字节)))
        self.end_headers()
        self.wfile.write(响应字节)

    def log_message(self, *args):
        pass


def 起服务器():
    服务器 = ThreadingHTTPServer(("127.0.0.1", 18999), 假DeepSeek)
    服务器.daemon_threads = True
    线程 = threading.Thread(target=服务器.serve_forever, daemon=True)
    线程.start()
    return 服务器


def 显示请求():
    for i in range(len(收到的请求)):
        条目 = 收到的请求[i]
        print("=" * 70)
        print("第 " + str(i + 1) + " 次请求")
        print("=" * 70)
        print("【HTTP 方法 + 路径】  " + 条目["方法"] + " " + 条目["路径"])
        print()
        print("【请求头】")
        for 名字 in 条目["请求头"]:
            值 = 条目["请求头"][名字]
            if 名字.lower() == "authorization":
                值 = "Bearer sk-******（打码）"
            elif 名字.lower() == "host":
                值 = 值 + "   ← 请求发到了这个地址"
            print("    " + 名字 + ": " + 值)
        print()
        print("【请求体（这就是真的发出去的 JSON）】")
        print(json.dumps(json.loads(条目["原始请求体"]), ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    服务器 = 起服务器()
    os.environ["BASE_URL"] = "http://127.0.0.1:18999/v1"

    sys.stdin = io.StringIO("你好，我叫小明\n我刚才说我叫什么？\nexit\n")

    from afg.chat import main

    main()
    服务器.shutdown()

    print()
    print("再走一遍：服务器这一侧看到了什么")
    print()
    显示请求()
