# CCcat 海龟汤 — 完整架构 v5.0

> 基于原CCcat猜词大挑战改造的抖音直播弹幕海龟汤互动游戏
> 双轨道并行：逐字解密（Track A）+ 是非问答（Track B）
> 单进程架构，在线 API 推理，嵌入式 + SPA 双前端

---

## 一、游戏流程

### 一局游戏的完整生命周期

```
开局（自动/手动）
   |
   v
[1] 系统随机选题 -> 加载汤底原文 + 题库
   |
   v
[2] 播报汤面（TTS朗读悬疑开头，弹幕来了可打断）
   |
   v
[3] 公示规则：虚词已揭示 / 实词打码 / 观众弹幕猜词
   |
   v
[4] 弹幕互动阶段（核心）
   |  ├─ 轨道A：逐字揭示（每条弹幕必走）
   |  ├─ 轨道B：是非问答（过滤后走）
   |  ├─ 礼物/点赞/灯牌触发揭示
   |  ├─ 防卡死兜底（后端 anti_stall_loop）
   |  └─ 礼物索要提示（LLM 间歇生成）
   |
   v
[5] 通关条件满足 -> 恭喜播报（不可打断）
   |
   v
[6] 朗读完整汤底 -> 清空弹幕缓存 -> 5秒后下一局
```

---

## 二、服务架构（当前）

```
┌─────────────────────────────────────────────────┐
│                  server.py                      │
│              (单进程, 端口 3010)                  │
│                                                  │
│  ┌──────────┐    ┌───────────────────────┐       │
│  │ FastAPI   │    │   WebSocket /ws       │       │
│  │ REST API  │    │   - danmaku 处理       │       │
│  │           │    │   - gift 处理          │       │
│  │ /classify │    │   - start_round       │       │
│  │ /hint     │    │   - state_sync        │       │
│  │ /config   │    │                       │       │
│  │ /game/*   │    │    +─ anti_stall_loop │       │
│  └──────────┘    └───────────────────────┘       │
│                        │                         │
│                        ▼                         │
│  ┌─────────────────────────────────────────┐     │
│  │ Embedded UI (HTML) — 无前端环境时的替代  │     │
│  │ Meoo SPA (Vite+React) — 正常浏览模式    │     │
│  └─────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────┐
│  DeepSeek API       │  ← 弹幕三分类、提示生成
│  (deepseek-v4-flash)│     礼物索要话术
└─────────────────────┘
```

### 辅助服务（独立进程）

| 服务 | 文件 | 端口 | 说明 |
|------|------|------|------|
| 弹幕中继 | `barrage-relay.mjs` | :9876 | HTTP POST /push → WS 广播 |
| TTS 语音 | `tts-relay.cjs` | :3006 | Edge TTS 合成（可选） |

> **注意**：`game_server.py` 和 `qwen_server.py` 已废弃（v4.x 架构），所有功能合并到 `server.py`。

---

## 三、弹幕处理管道（核心架构）

```
抖音弹幕（WSS 抓包 或 /api/barrage/push）
    |
    v
+----------------------------------------------+
| 第一层过滤（通用快筛）                         |
| 纯标点 / 纯数字 / 纯表情 / 纯特殊符号          |
| 长度 < 2 或 > 50                              |
| 拦截 -> 丢弃，不进入后续处理                   |
+--------------------+-------------------------+
                     | 通过
                     v
+----------------------------------------------+
| 轨道A：逐字解密（每条弹幕必走，永远不拦截）      |
| 弹幕中每个字 -> 检查是否属于"待揭示实词集合"    |
| 命中 -> 全文同字所有位置同时揭示               |
| 不命中 -> 不揭示                              |
| ★ 不管命中与否，都继续往下传                   |
+--------------------+-------------------------+
                     | 必走
                     v
+----------------------------------------------+
| 第二层过滤（弹幕内容过滤）                     |
| 关键词黑名单：哈哈哈/666/主播好/来了/签到...   |
| 纯数字/纯标点                                 |
| 长度 < 3 或 > 30                              |
| 拦截 -> 显示为"不相关"气泡                    |
+--------------------+-------------------------+
                     | 通过
                     v
+----------------------------------------------+
| 轨道B：LLM 三分类（DeepSeek API）              |
| 输入：汤底原文 + 弹幕                         |
| 输出：是 / 是也不是 / 不是                    |
| 结果 -> 对应问答气泡展示                       |
+----------------------------------------------+

四种结果气泡展示：
- 🟢 是          — 绿色标签
- 🟡 是也不是     — 黄色标签
- 🔴 不是          — 红色标签
- ⚪ 不相关       — 灰色标签（仅显示弹幕内容）
```

---

## 三、轨道A：逐字解密（详细机制）

### 打码规则

| 类型 | 处理 | 示例 |
|------|------|------|
| 实词 | 参与解密，初始打码 | "男、人、走、进、酒、吧、要、水..." |
| 虚词 | 开局直接揭示 | "的、了、是、在、和、吗" |
| 标点 | 开局直接揭示 | "，。、？！；：""''" |

### 虚词列表（`server.py:FUNCTION_WORDS`，全局生效）

```
的、了、是、在、和、吗、呢、吧、着、过、得、地、个、一、不、没、
有、就、都、而、但、又、如果、因为、所以、然后、于是、向、对、从、到、
把、被、给、让、每、只、想、会、能、可以、很、太、非常、已经、正在、
曾经、将、要、这、那、你、我、他、她、它、们、上、下、里、外、前、
后、中、时、还、也、再、才、刚、做、说、看、来、去
```

### 揭示逻辑（v5.0 修复）

```python
# server.py — RevealEngine.reveal_char()
# ★ 全文同字同时揭示（v5.0 修复：之前是 reveal_one_char 仅揭示第一处）
def reveal_char(states, target):
    return [{**s, "revealed": True} if s["char"] == target else s for s in states]

# handle_danmaku — 聚合判断，只广播一次
any_revealed = False
for ch in text:
    if ch in answer and is_content_word(ch):
        if any(s["char"]==ch and not s["revealed"] for s in states):
            states = reveal_char(states, ch)
            any_revealed = True
if any_revealed:
    broadcast_reveal_update()
else:
    anti_since_reveal += 1
```

### 揭示进度计算

```
progress = (已揭示实词数 / 总实词数) x 100%

示例：汤底共 120 个字符，其中 80 个实词、40 个虚词/标点
      已揭示 40 个实词 -> 进度 50%
```

---

## 四、轨道B：是非问答（详细机制）

### 题库结构

```python
# data_soups.py
SOUPS = [
    {
        "id": "soup-001",
        "title": "海龟汤",
        "surface": "一个男人走进餐厅，点了一碗海龟汤...",
        "bottom": "男人曾经和朋友们在海上遇难...",
        "keywords": ["海龟汤", "餐厅", "自杀", "朋友", "海上", "人肉", "味道"],
        "difficulty": "medium",
    },
    ...
]
```

### LLM 三分类调用

```
POST /classify  (server.py)
→ 转发到 DeepSeek API

请求:
{
  "text": "玩家弹幕",
  "answer": "汤底原文",
  "keywords": ["关键词1", "关键词2"]
}

响应:
{
  "answerType": "是"    # 可选值：是 / 不是 / 是也不是
}
```

> v5.0 变更：不再使用本地 Qwen 2.5-0.5B 模型，全部通过 DeepSeek API 在线推理。
> 弹幕先走规则过滤（毫秒级），通过后再调 LLM 分类，避免无效 API 调用。

---

## 五、礼物与互动机制

### 礼物触发链路

```
WSS 抓包 或 WebSocket 消息
    |
    +-> 弹幕类 -> 弹幕处理管道
    |
    +-> 互动类 -> 直接触发轨道A的揭示逻辑
         |
         +-- 点赞累积 -> 每500赞揭示一字
         |    揭示规则：全文同字同时揭示
         |
         +-- 粉丝灯牌 -> 揭示一句话
         |    每局最多3次（max_fanlight=3）
         |
         +-- 人气票 -> 方向引导
         |    基于 qaHistory + LLM 动态生成
         |
         +-- 啤酒 -> 随机揭示一字
         |    揭示规则：全文同字同时揭示
         |
         +-- 棒棒糖 -> 随机揭示一句
         |
         +-- 墨镜 -> 揭示全文（通关）
```

### 礼物效果一览

| 礼物 | 效果 | 揭示规则 | 频次控制 |
|------|------|---------|---------|
| 人气票 | 方向引导提示 | — | 每次送触发 |
| 啤酒 | 揭示一个高频实词字 | 全文同字全部揭示 | 每次送触发 |
| 棒棒糖 | 揭示一整句 | 句中所有实词揭示 | 每次送触发 |
| 墨镜 | 揭示全文通关 | 全部揭示 | 每次送触发 |
| 粉丝灯牌 | 揭示一句 | 句中所有实词揭示 | 每局最多3次 |
| 点赞累积 | 每500赞揭示一字 | 全文同字全部揭示 | 持续累积 |

### 防卡死机制（后端 `anti_stall_loop`）

| 条件 | 数值 | 说明 |
|------|------|------|
| 触发逻辑 | 任一条件触发即可（或逻辑） | 后端独立线程 |
| 时间条件 | 3 分钟无新字揭示 | 适合慢节奏场 |
| 弹幕条件 | 50 条弹幕无新字命中 | 适合快节奏场 |
| 触发效果 | 自动揭示 1 个高频实词字 | 优先选择出现次数多的字 |
| 衰减机制 | 连续触发间隔缩短 20% | 第二次 2.4min/40条，第三次 1.9min/32条 |

> **v5.0 变更**：防卡死仅在后端运行（之前前端也有独立防卡死，现已移除）。

---

## 六、数据格式

### 游戏状态：GameRoom

```python
class GameRoom:
    phase: str          # lobby | reading | playing | complete
    soup_text: str      # 汤面
    soup_answer: str    # 汤底
    soup_keywords: list
    char_states: list[dict]  # [{char, revealed, isContent}, ...]
    qa_history: list[dict]   # [{user, question, result, timestamp}, ...]
    gift_log: list[dict]
    like_progress: int
    like_threshold: int = 500
    guess_count: int
    anti_last_reveal: float  # 上次揭示时间戳
    anti_since_reveal: int   # 上次揭示以来的弹幕数
    anti_triggers: int       # 连续防卡死触发次数
    fanlight_used: int       # 本局灯牌使用次数
    max_fanlight: int = 3
```

### WebSocket 消息协议

| 方向 | type | 说明 |
|------|------|------|
| 客户端→服务器 | `danmaku` | 弹幕消息 |
| 客户端→服务器 | `gift` | 礼物消息 |
| 客户端→服务器 | `start_round` | 开始新一局 |
| 客户端→服务器 | `ping` | 心跳 |
| 服务器→客户端 | `game_start` | 新局开始，携带汤面+字状态 |
| 服务器→客户端 | `reveal_update` | 揭示更新 |
| 服务器→客户端 | `classification` | 弹幕分类结果 |
| 服务器→客户端 | `game_end` | 游戏结束 |
| 服务器→客户端 | `hint` | 方向提示 |
| 服务器→客户端 | `gift_effect` | 礼物效果 |
| 服务器→客户端 | `state_sync` | 状态同步（断线重连） |

---

## 七、项目文件清单（当前）

```
抖音海龟汤/
├── backend/                    # 后端
│   ├── server.py               # 主服务（FastAPI + WS + LLM）
│   ├── data_soups.py           # 题库（15 题）
│   ├── embedded_ui.py          # 嵌入式前端（fallback）
│   ├── barrage-relay.mjs       # 弹幕中继（可选）
│   ├── tts-relay.cjs           # TTS 语音（可选）
│   ├── requirements.txt        # Python 依赖
│   ├── start_all.bat           # 一键启动
│   └── start_backend.bat       # 后端启动
│
├── meoo_frontend/              # 正式前端（Vite + React + TanStack Router）
│   ├── src/
│   │   ├── components/         # UI 组件
│   │   ├── hooks/              # 自定义 Hooks
│   │   ├── stores/             # Zustand 状态管理
│   │   ├── routes/             # 页面路由
│   │   ├── services/           # API 服务
│   │   ├── data/               # TS 题库（与 Python 版同步）
│   │   └── types/              # TypeScript 类型
│   └── package.json
│
├── _archive/                   # 废弃文件（可删除）
│   ├── game_server.py          # 旧版独立游戏服务（v4.x）
│   ├── qwen_server.py          # 旧版 Qwen 本地推理服务
│   ├── 临时脚本/崩溃日志/截图   # 开发过程残留
│   └── backend/                # backend 目录的临时脚本
│
├── .env                        # 环境变量（API Key 等）
├── .gitignore
├── CCcat海龟汤_完整架构.md      # 本文档
├── CCcat海龟汤.exe              # PyInstaller 打包
├── build_exe.bat               # EXE 构建脚本
├── start_all.bat               # 一键启动（根目录）
├── README.md
└── docs/                       # 设计文档
```

---

## 八、技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI + Python 3.11+ | REST + WebSocket |
| AI 推理 | DeepSeek API (deepseek-v4-flash) | 弹幕三分类、提示生成 |
| 正式前端 | Vite + React 18 + TanStack Router | SPA |
| 状态管理 | Zustand | 轻量级 |
| 嵌入式前端 | 纯 HTML/CSS/JS | 无需构建的 fallback |
| 弹幕中继 | Node.js + ws | HTTP POST → WS 广播 |
| TTS | Edge TTS（Python edge-tts 或 CLI）| 中文语音合成 |
| 打包 | PyInstaller | 单 EXE 分发 |

---

## 九、变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v5.0 | 2026-06-23 | 单进程合并；修复 Track A 揭示 bug；移除前端防卡死；清理废弃文件 |
| v4.1 | 2026-06-21 | 初始多进程架构（已废弃） |

### v4.x → v5.0 关键变更

| 原组件 | 操作 | 原因 |
|--------|------|------|
| `game_server.py` + `qwen_server.py` | 移除 → 合并到 `server.py` | 单进程简化部署 |
| `reveal_one_char()` | 移除 → 统一 `reveal_char()` | 全文同字同时揭示 |
| 前端防卡死 (`useGameState.ts`) | 移除 | 和后端防卡死冲突 |
| LLM API Key 硬编码默认值 | 移除 | 安全风险 |
| 临时脚本 / 崩溃日志 | 移入 `_archive/` | 清理工作目录 |

---

> **版本**：v5.0
> **日期**：2026-06-23
> **后端端口**：:3010
> **LLM 模型**：deepseek-v4-flash
> **API 地址**：https://api.deepseek.com
