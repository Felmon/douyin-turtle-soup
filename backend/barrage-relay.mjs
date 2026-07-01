/**
 * CCcat 海龟汤 — WSS 弹幕中继服务
 *
 * 端口 :9876
 * 接收外部弹幕推送（HTTP POST /push），广播到所有连接的 WS 客户端
 *
 * 消息格式:
 *   { type: "danmu", data: { user, content } }
 */

import http from "node:http";
import { WebSocketServer } from "ws";

const PORT = 9876;

// ── HTTP Server ──
const server = http.createServer((req, res) => {
  // CORS
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === "POST" && req.url === "/push") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        const data = JSON.parse(body);
        const message = {
          type: "danmu",
          data: {
            user: data.user || "anonymous",
            content: data.content || "",
            timestamp: Date.now(),
          },
        };

        // 广播到所有 WS 客户端
        let count = 0;
        wss.clients.forEach((client) => {
          if (client.readyState === WebSocketServer.OPEN) {
            client.send(JSON.stringify(message));
            count++;
          }
        });

        console.log(`[Relay] 收到弹幕: ${data.user}: ${data.content}  → 广播到 ${count} 个客户端`);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true, broadcast: count }));
      } catch (err) {
        console.error(`[Relay] JSON解析错误: ${err.message}`);
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "invalid_json" }));
      }
    });
    return;
  }

  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      status: "ok",
      clients: wss.clients.size,
      uptime: process.uptime(),
    }));
    return;
  }

  res.writeHead(404);
  res.end("Not Found");
});

// ── WebSocket Server ──
const wss = new WebSocketServer({ server });

wss.on("connection", (ws, req) => {
  const clientAddr = req.socket.remoteAddress || "unknown";
  console.log(`[Relay] WS 客户端连接: ${clientAddr}  (当前连接数: ${wss.clients.size})`);

  // 发送欢迎消息
  ws.send(JSON.stringify({
    type: "connected",
    message: "已连接到弹幕中继服务",
    timestamp: Date.now(),
  }));

  ws.on("close", () => {
    console.log(`[Relay] WS 客户端断开: ${clientAddr}  (剩余连接数: ${wss.clients.size})`);
  });

  ws.on("error", (err) => {
    console.error(`[Relay] WS 错误 (${clientAddr}): ${err.message}`);
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`╔══════════════════════════════════╗`);
  console.log(`║  CCcat 弹幕中继服务              ║`);
  console.log(`║  HTTP POST :9876/push  推送弹幕   ║`);
  console.log(`║  WS       :9876        接收弹幕   ║`);
  console.log(`║  GET      :9876/health 健康检查   ║`);
  console.log(`╚══════════════════════════════════╝`);
});
