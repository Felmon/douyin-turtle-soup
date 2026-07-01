# CCcat 海龟汤 — 游戏完全手册

> 基于原CCcat猜词大挑战改造的抖音直播弹幕海龟汤互动游戏
> 双轨道并行：逐字解密（Track A）+ 是非问答（Track B）

---

## 一、游戏概念

### 什么是海龟汤？

海龟汤（Situation Puzzle）是一种情境猜谜游戏。主持人给出一个简短的故事开头（**汤面**），观众通过提问来还原完整的故事（**汤底**）。主持人只能回答「是」「不是」或「是也不是」。

### 本项目玩法

将海龟汤与抖音直播弹幕结合，观众发送弹幕参与猜谜：

- **Track A — 逐字解密**：弹幕中的每个字符自动与汤底匹配，命中则揭示全文所有相同字符。这是「歪打正着」的趣味通道。
- **Track B — 是非问答**：弹幕经过LLM三分类，判断与汤底的相关性，以气泡形式展示。
- **礼物互动**：观众送礼物触发揭示/提示效果。
- **防卡死**：长时间无进展时自动揭示关键字符。

---

## 二、系统架构

### 整体结构

当前版本为**单进程合并模式**，所有功能集成在 server.py 中：

`
用户浏览器
  http://localhost:3010/  (嵌入式HTML，默认)
  或 http://localhost:3015/ (React前端)
        |  WebSocket  ws://:3010/ws
        v
server.py (:3010)  [单进程合并服务]
  ├── WebSocket连接管理器 (多客户端)
  ├── 弹幕处理管道
  │     Layer 1: 规则快筛 -> Track A: 逐字揭示
  │     -> Layer 2: 内容过滤 -> Track B: LLM三分类
  ├── 游戏引擎 (房间状态+题库+礼物+防卡死)
  ├── LLM API (远程qwen3.5-plus)
  └── TTS (Web Speech API / tts-relay.cjs)
`

### 文件结构

`
根目录/
  backend/
    server.py         # 主服务 (游戏引擎+WS+API+前端)
    embedded_ui.py    # 嵌入式HTML前端
    data_soups.py     # 题库 (15道海龟汤)
    qwen_server.py    # 独立LLM服务
    barrage-relay.mjs # WSS弹幕中继
    tts-relay.cjs     # Edge TTS
  meoo_frontend/      # React前端
    src/
      routes/index.tsx          # 主页 (WS连接)
      stores/gameStore.ts       # 游戏状态管理
      components/game/SoupDisplay.tsx  # 汤底展示
      components/game/GiftPanel.tsx    # 礼物面板
      components/game/QaBubble.tsx     # 问答气泡
      components/game/GameControls.tsx # 控制按钮
      components/game/ProgressBars.tsx # 进度条
      components/game/ContributionBoard.tsx # 贡献榜
      data/soups.ts             # 题库
      utils/pinyinReveal.ts     # 揭示工具
      types/index.ts            # 类型定义
  docs/
    架构对比分析.md            # 架构差异文档
  .env                          # 环境变量
  start_all.bat                 # 一键启动
`

---

## 三、弹幕处理管道（核心机制）

每条弹幕进入系统后的完整处理流程：

`
弹幕进入 (用户发送/抖音WSS)
   |
   v
Layer 1: 规则快筛 (rule_filter)
  拦截: 纯标点/纯数字/纯emoji/长度<2
        666/哈哈哈/主播好/来了/签到
  判定: 命中 -> 丢弃 (不显示)
   |
   v  (通过)
Track A: 逐字揭示 (必走，永不拦截)
  对弹幕中的每个字符：
    1. 检查是否在汤底中
    2. 检查是否为实词 (非虚词)
    3. 检查是否尚未揭示
    4. 全部满足 -> 全文同字一起揭示
  (不管是否命中，都继续往下传)
   |
   v  (必走)
Layer 2: 内容过滤
  拦截: 长度<3或>30 / 纯数字/纯标点 / 黑名单
  拦截效果: 显示为「不相关」气泡 (灰色)
   |
   v  (通过)
Track B: LLM三分类
  输入: 汤底原文 + 弹幕文本
  输出: 是 / 不是 / 是也不是
  (通过远程LLM API: qwen3.5-plus)
   |
   v
广播分类结果到所有客户端
`

### 四种结果气泡

| 结果 | 颜色 | 含义 |
|------|------|------|
| 是 | 绿色 | 弹幕与汤底真相一致 |
| 不是 | 红色 | 弹幕与汤底不符 |
| 是也不是 | 黄色 | 部分正确需要更精确 |
| 不相关 | 灰色 | 规则过滤拦截 |

---

## 四、汉字揭示机制 (Track A)

### 三类字符

| 类型 | 开局状态 | 示例 | 数量占比 |
|------|---------|------|---------|
| **实词** | 打码显示 ** | 男人走进酒吧要水 | ~60% |
| **虚词** | 直接揭示 (灰色) | 的了是在和吗呢吧 | ~35% |
| **标点** | 直接揭示 | ，。、？！；： | ~5% |

### 揭示规则

1. 观众发送弹幕「酒吧」
2. 系统检查「酒」在汤底中 -> 是
3. 「酒」是实词且未揭示 -> 揭示汤底中**所有**的「酒」
4. 「吧」是虚词(已在开局揭示) -> 忽略
5. 广播 
eveal_update，前端更新遮罩

### 虚词列表 (内置80+个)

`
的 了 是 在 和 吗 呢 吧 着 过 得 地 个 一 不 没
有 就 都 而 但 又 如果 因为 所以 然后 于是 向 对
从 到 把 被 给 让 每 只 想 会 能 可以 很 太 非常
已经 正在 曾经 将 要 这 那 你 我 他 她 它 们
上 下 里 外 前 后 中 时 还 也 再 才 刚 做 说
看 来 去
`

### 进度计算

`
progress = (已揭示实词数 / 总实词数) * 100%

例: 汤底共120字, 80个实词, 40个虚词/标点
    已揭示40个实词 -> 进度 50%
`

---

## 五、礼物系统

| 礼物 | 后端效果 | 详情 |
|------|---------|------|
| 人气票 | 方向引导提示 | 调用LLM根据问答历史生成提示语 |
| 啤酒 | 揭示一个高频实词 | 从未揭示实词中随机选一个 |
| 棒棒糖 | 揭示一整句 | 找第一个未完全揭示的从句 |
| 墨镜 | 直接通关 | 所有字揭示，触发game_end |
| 粉丝灯牌 | 揭示一句 | 同棒棒糖效果，每局有次数限制 |
| 点赞累积 | 每500赞揭示一字 | 累积计数达到阈值触发 |

---

## 六、防卡死机制

### 触发逻辑

每30秒后台检查（或逻辑，任一触发）：

- **时间条件**: 3分钟(180秒) 无新字揭示
- **弹幕条件**: 50条弹幕无新字命中

### 衰减机制

每次连续触发阈值缩短20%：
- 第1次: 3分钟 / 50条
- 第2次: 2.4分钟 / 40条
- 第3次: 1.9分钟 / 32条

### 触发效果

1. 选汤底中出现频率最高的未揭示实词
2. 自动揭示（全文同字揭示）
3. 广播系统消息「防卡死自动揭示：X」
4. 检查是否已通关

---

## 七、LLM API 集成

### 三个调用场景

| 场景 | 函数 | 工作 |
|------|------|------|
| 弹幕分类 | llm_classify() | 判断弹幕与汤底的相关性 |
| 方向提示 | llm_hint() | 根据问答历史生成引导提示 |
| 礼物索要 | llm_gift_solicit() | 生成索要话术 (当前未触发) |

### 当前配置

`
LLM_API_KEY = sk-dNctBhMEO5xHrbQCHAjI71YKEALoAhQN1KW3k9GvEKhTUGj7ksbDmwnrlM5WRbQX
LLM_BASE_URL = https://api.deepseek.com
LLM_MODEL = deepseek-v4-flash
`

支持替换为其他 OpenAI-compatible API。

---

## 八、WebSocket 消息协议

### 客户端 -> 服务器

`json
{ "type": "start_round" }
{ "type": "danmaku", "text": "和钱有关吗", "nickname": "观众" }
{ "type": "gift", "giftName": "啤酒", "nickname": "观众" }
{ "type": "ping" }
`

### 服务器 -> 客户端

`json
{ "type": "game_start", "surface": "...", "keywords": [...], "charStates": [...] }
{ "type": "reveal_update", "charStates": [...] }
{ "type": "classification", "text": "...", "answerType": "是|不是|是也不是|不相关" }
{ "type": "hint", "hint": "想想故事里谁最可疑?" }
{ "type": "gift_effect", "user": "...", "giftName": "啤酒" }
{ "type": "game_end", "winner": "...", "charStates": [...] }
{ "type": "pong" }
`

---

## 九、运行方式

### 方式1: 一键启动

`ash
start_all.bat
`
自动检测exe或venv，启动后端:3010 + 前端:3015。

### 方式2: Python直接运行 (推荐)

`ash
cd backend
pip install -r requirements.txt
python server.py
`
打开 http://localhost:3010/ 即可游戏。

### 方式3: React版

`ash
# 终端1
python backend/server.py
# 终端2
cd meoo_frontend && npm install && npm run dev
`
打开 http://localhost:3015/ 体验React版。

### 方式4: exe

`ash
dist/CCcat海龟汤.exe
`

### 环境要求

- OS: Windows 10/11
- Python: 3.11+
- Node.js: 18+ (React版)
- RAM: 2GB+ (无本地模型)
- LLM API Key (已配置)

---

## 十、游戏全流程

`
1. 打开 http://localhost:3010/
2. 点击「开始游戏」
   -> 后端随机选题，初始化遮罩
   -> 广播 game_start (汤面 + 所有字符状态)
   -> 前端显示汤面3秒后进入游戏
3. 弹幕互动
   -> 输入框输入猜测/提问
   -> 规则快筛 -> 轨道A揭示 -> LLM分类
   -> 实时更新遮罩 + 气泡流
4. 全部揭示 -> 通关弹窗 -> 5秒后新一局
`

---

## 十一、已修复问题

| 问题 | 修复内容 |
|------|---------|
| 汤底遮罩 | server.py正则修正 + React字段映射(isContent->isContentWord) |
| React WS | 添加game_start/reveal_update/game_end handler |
| GameControls | 改为发送start_round到后端 |
| 防卡死 | 添加anti_stall_loop后台任务 |

---

> 文档版本: v1.0
> 生成日期: 2026-06-22
