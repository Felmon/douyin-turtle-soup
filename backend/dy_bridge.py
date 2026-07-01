"""抖音弹幕桥接 — 对接 douyinLive.exe WebSocket 推流

douyinLive.exe（Go二进制，v2.0.17）监听抖音直播间 WebSocket，
收到弹幕/礼物后推送到本模块，本模块再转发给 server.py 的 /api/barrage/push。

架构:
  douyinLive.exe (WSS抓包, :1088)
    → WebSocket 推流到 dy_bridge.py (WS客户端)
    → HTTP POST 到 server.py (/api/barrage/push)

用法:
  from dy_bridge import DouyinBridge
  bridge = DouyinBridge(server_url="http://localhost:3010")
  await bridge.start()
"""
import asyncio
import json
import time
import httpx


class DouyinBridge:
    """抖音弹幕桥接器。"""

    def __init__(self, live_ws_url: str = "ws://localhost:1088",
                 server_push_url: str = "http://localhost:3010/api/barrage/push",
                 server_gift_push_url: str | None = None,
                 reconnect_delay: float = 3.0):
        self.live_ws_url = live_ws_url
        self.server_push_url = server_push_url
        self.server_gift_push_url = server_gift_push_url or server_push_url.replace(
            "/api/barrage/push", "/api/gift/push"
        )
        self.reconnect_delay = reconnect_delay
        self._running = False
        self._task: asyncio.Task | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._stats = {"connected": 0, "forwarded": 0, "errors": 0}

    async def start(self):
        """启动桥接（后台任务）。"""
        self._running = True
        self._http_client = httpx.AsyncClient(timeout=10.0)
        self._task = asyncio.create_task(self._run())
        print(f"[DouyinBridge] 已启动 -> WS: {self.live_ws_url} | Push: {self.server_push_url}")

    async def stop(self):
        """停止桥接。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http_client:
            await self._http_client.aclose()
        print(f"[DouyinBridge] 已停止")

    async def _run(self):
        while self._running:
            try:
                import websockets as ws_lib
                async with ws_lib.connect(self.live_ws_url) as ws:
                    self._stats["connected"] += 1
                    print(f"[DouyinBridge] 已连接 {self.live_ws_url}")
                    async for raw in ws:
                        if not self._running:
                            break
                        await self._forward(raw)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["errors"] += 1
                print(f"[DouyinBridge] 连接异常: {e}")
                if self._running:
                    await asyncio.sleep(self.reconnect_delay)

    async def _forward(self, raw: str):
        """将收到的消息转发到 server.py。"""
        try:
            data = json.loads(raw)
            msg_type = data.get("type", "")
            payload = {}
            if msg_type == "danmaku":
                payload = {
                    "type": "danmaku",
                    "user": data.get("user", {}).get("nickname", "观众"),
                    "content": data.get("content", ""),
                }
            elif msg_type == "gift":
                payload = {
                    "type": "gift",
                    "user": data.get("user", {}).get("nickname", "观众"),
                    "gift_name": data.get("gift", {}).get("gift_name", ""),
                    "diamond_count": data.get("gift", {}).get("diamond_count", 0),
                    "count": data.get("gift", {}).get("count", 1),
                }
            elif msg_type in ("like", "member", "follow"):
                # 这些类型没有 content 字段，无法推送到 /api/barrage/push
                self._stats["forwarded"] += 1
                return
            else:
                return  # 不处理未知类型

            if self._http_client and payload:
                target_url = self.server_gift_push_url if msg_type == "gift" else self.server_push_url
                resp = await self._http_client.post(
                    target_url,
                    json=payload,
                )
                if resp.status_code == 200:
                    self._stats["forwarded"] += 1
                else:
                    self._stats["errors"] += 1
                    print(f"[DouyinBridge] 转发失败: {resp.status_code}")
        except json.JSONDecodeError:
            pass  # 非JSON消息忽略
        except Exception as e:
            print(f"[DouyinBridge] 转发异常: {e}")

    def get_stats(self) -> dict:
        return {**self._stats}
