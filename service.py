"""闽港医疗科创协作的运行入口与只读接口。

路由：
  GET /health                       健康检查（联调与巡检）
  GET /api/demands                  需求列表（脱敏摘要，任何机构可见）
  GET /api/demands/<id>?org=<org>   需求详情：按机构身份决定能否看到秘密材料
  GET /api/brief/<demand_id>        主管视图：推荐证据、权利占用、跨组织待办、资金对账
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from domain import DomainError
from seed import build_demo_platform

SERVICE_ID = "medical-matchmaking"
SERVICE_NAME = "闽港医疗科创协作"

PLATFORM = build_demo_platform()


def health_payload():
    """返回稳定的服务身份信息。"""
    return {"status": "ok", "service": SERVICE_ID, "name": SERVICE_NAME}


def list_demands():
    return {"demands": [PLATFORM.view_demand(did, org_id=None)
                        for did in PLATFORM.demands]}


def get_demand(demand_id, org_id):
    return PLATFORM.view_demand(demand_id, org_id)


def get_brief(demand_id):
    return PLATFORM.supervisor_brief(demand_id)


class Handler(BaseHTTPRequestHandler):
    """只读接口；写操作（签 NDA、尽调、排他、拨款）走领域层，见 domain.py。"""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path == "/health":
                self._send(200, health_payload())
            elif path == "/api/demands":
                self._send(200, list_demands())
            elif path.startswith("/api/demands/"):
                demand_id = path.split("/")[-1]
                org_id = query.get("org", [None])[0]
                self._send(200, get_demand(demand_id, org_id))
            elif path.startswith("/api/brief/"):
                self._send(200, get_brief(path.split("/")[-1]))
            else:
                self.send_error(404)
        except DomainError as exc:
            self._send(404, {"error": str(exc)})

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def main():
    parser = argparse.ArgumentParser(description=SERVICE_NAME)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        assert health_payload()["service"] == SERVICE_ID
        assert "DEM-001" in PLATFORM.demands
        print("基础检查通过")
        return
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
