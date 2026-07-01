/**
 * CCcat 海龟汤 — Edge TTS 语音播报中继服务
 *
 * 端口 :3006
 * 使用 edge-tts 包进行中文语音合成
 * WS 广播 TTS 状态
 *
 * 依赖: npm install edge-tts ws express
 */

const express = require("express");
const http = require("http");
const { WebSocketServer } = require("ws");
const { createServer } = require("http");
const { spawn } = require("child_process");

const PORT = 3006;
const TTS_VOICE = "zh-CN-XiaoxiaoNeural";  // 中文女声
const TTS_RATE = "+0%";                     // 语速
const TTS_VOLUME = "+0%";                   // 音量

const app = express();
app.use(express.json());

const server = createServer(app);
const wss = new WebSocketServer({ server });

// ── CORS ──
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }
  next();
});

// ── WS 连接管理 ──
wss.on("connection", (ws, req) => {
  const addr = req.socket.remoteAddress || "unknown";
  console.log(`[TTS] WS 客户端连接: ${addr}`);

  ws.send(JSON.stringify({
    type: "tts_connected",
    message: "已连接到 TTS 语音服务",
    voice: TTS_VOICE,
  }));

  ws.on("close", () => console.log(`[TTS] WS 断开: ${addr}`));
  ws.on("error", (err) => console.error(`[TTS] WS 错误: ${err.message}`));
});

// ── TTS 广播 ──
function broadcastTTSStatus(status, data = {}) {
  const message = JSON.stringify({
    type: "tts_status",
    status,
    ...data,
    timestamp: Date.now(),
  });
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocketServer.OPEN) {
      client.send(message);
    }
  });
}

// ── Edge TTS 合成 ──
function speak(text) {
  return new Promise((resolve, reject) => {
    if (!text || text.trim().length === 0) {
      return reject(new Error("文本不能为空"));
    }

    // 截断过长文本（edge-tts 有长度限制）
    const truncated = text.slice(0, 500);

    console.log(`[TTS] 开始合成: "${truncated.slice(0, 50)}..."`);

    // 使用 edge-tts CLI
    // 格式: edge-tts --voice zh-CN-XiaoxiaoNeural --text "..." --write-media output.mp3
    // 这里我们不写文件，通过子进程直接播放，或者让前端自行处理
    // 这里我们用 edge-tts 的 Python 包（如果可用）或者 edge-tts npm 包

    // 尝试用 edge-tts 命令行工具
    const proc = spawn("edge-tts", [
      "--voice", TTS_VOICE,
      "--rate", TTS_RATE,
      "--volume", TTS_VOLUME,
      "--text", truncated,
      "--write-media", "-",   // 输出到 stdout
    ], { stdio: ["ignore", "pipe", "pipe"] });

    const chunks = [];

    proc.stdout.on("data", (chunk) => {
      chunks.push(chunk);
    });

    proc.on("close", (code) => {
      if (code === 0 && chunks.length > 0) {
        const audioBuffer = Buffer.concat(chunks);
        const base64 = audioBuffer.toString("base64");
        console.log(`[TTS] 合成完成: ${(audioBuffer.length / 1024).toFixed(1)} KB`);
        resolve(base64);
      } else {
        // edge-tts CLI 不存在或出错，用 fallback 方式
        console.warn(`[TTS] edge-tts CLI 失败 (code=${code})，尝试用 Python 模块`);
        fallbackSpeak(truncated).then(resolve).catch(reject);
      }
    });

    proc.on("error", (err) => {
      console.warn(`[TTS] edge-tts CLI 不可用: ${err.message}，尝试用 Python 模块`);
      fallbackSpeak(truncated).then(resolve).catch(reject);
    });
  });
}

// ── Fallback: 使用 Python edge-tts 模块 ──
function fallbackSpeak(text) {
  return new Promise((resolve, reject) => {
    const script = `
import asyncio, sys, io
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

async def main():
    import edge_tts
    communicate = edge_tts.Communicate(
        text=sys.argv[1] if len(sys.argv) > 1 else "${TTS_VOICE}",
        voice="${TTS_VOICE}",
        rate="${TTS_RATE}",
        volume="${TTS_VOLUME}"
    )
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    sys.stdout.buffer.write(audio)

asyncio.run(main())
`;
    const proc = spawn("python", ["-c", script, text], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    const chunks = [];
    proc.stdout.on("data", (chunk) => chunks.push(chunk));

    proc.on("close", (code) => {
      if (code === 0 && chunks.length > 0) {
        const audioBuffer = Buffer.concat(chunks);
        const base64 = audioBuffer.toString("base64");
        console.log(`[TTS] Python 合成完成: ${(audioBuffer.length / 1024).toFixed(1)} KB`);
        resolve(base64);
      } else {
        reject(new Error(`Python TTS 失败 (code=${code})`));
      }
    });

    proc.on("error", (err) => reject(err));
  });
}

// ── Routes ──

app.post("/speak", async (req, res) => {
  const { text } = req.body;

  if (!text) {
    return res.status(400).json({ ok: false, error: "缺少 text 字段" });
  }

  broadcastTTSStatus("speaking", { text: text.slice(0, 100) });

  try {
    const audioBase64 = await speak(text);
    broadcastTTSStatus("done", { text: text.slice(0, 100) });

    res.json({
      ok: true,
      audio: audioBase64,
      format: "mp3",
      voice: TTS_VOICE,
      text: text.slice(0, 100),
    });
  } catch (err) {
    console.error(`[TTS] 合成失败: ${err.message}`);
    broadcastTTSStatus("error", { error: err.message });

    res.status(500).json({
      ok: false,
      error: err.message,
    });
  }
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    clients: wss.clients.size,
    voice: TTS_VOICE,
  });
});

// ── 启动 ──
server.listen(PORT, "0.0.0.0", () => {
  console.log(`╔══════════════════════════════════╗`);
  console.log(`║  CCcat TTS 语音播报服务           ║`);
  console.log(`║  POST    :3006/speak  语音合成    ║`);
  console.log(`║  WS      :3006        状态广播    ║`);
  console.log(`║  GET     :3006/health 健康检查    ║`);
  console.log(`║  语音: ${TTS_VOICE}               ║`);
  console.log(`╚══════════════════════════════════╝`);
});
