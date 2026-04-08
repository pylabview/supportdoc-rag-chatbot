import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from supportdoc_rag_chatbot.app.schemas import build_example_answer_response

ANSWER = build_example_answer_response().model_dump(mode="json")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send(
                200,
                {"object": "list", "data": [{"id": "demo-model", "object": "model"}]},
            )
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("content-length", "0"))
            _ = self.rfile.read(length)
            self._send(
                200,
                {
                    "id": "chatcmpl-demo",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(ANSWER),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
            return
        self._send(404, {"error": "not found"})

    def log_message(self, format, *args):
        return


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
