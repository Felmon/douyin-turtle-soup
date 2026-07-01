# CCcat 海龟汤 🐢

AI 驱动的抖音直播互动海龟汤游戏 — 合并版服务。

## 特性

- **单进程服务** — FastAPI + 嵌入式前端（端口 3010）
- **WebSocket 实时通信** — 弹幕分类、礼物特效、段位升级推送
- **SQLite 持久化** — 用户积分、段位历史、签到、礼物日志
- **10 级段位系统** — 黑铁 → 青铜 → 黄金 → 铂金 → 钻石 → 白银 → 王者 → 宗师 → 大师 → 超级王者
- **5 档难度选择** — 简单(×1.0) / 一般(×1.5) / 困难(×2.0) / 地狱(×3.0) / 无人区(×5.0)
- **礼物别名系统** — 支持抖音真实礼物名映射，7 预设别名
- **连击 Combo 系统** — 连续送礼触发倍率加成（3连×1.5 / 5连×2 / 10连×3）
- **每日签到** — 7 天循环奖励（最高 150 金币）
- **礼物商店** — 6 种可购买礼物（点赞 / 粉丝灯牌 / 人气票 / 啤酒 / 棒棒糖 / 墨镜）
- **里程碑提示** — 揭示进度 25%/50%/75% 自动弹出 AI 方向提示
- **签到/排行榜 API** — RESTful 接口

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 2. 安装依赖
pip install -r backend/requirements.txt

# 3. 启动服务
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe backend/server.py
```

访问 [http://localhost:3010](http://localhost:3010)

## 项目结构

```
backend/
├── server.py          # FastAPI 主服务（含 WebSocket）
├── embedded_ui.py     # 嵌入式前端（单 HTML 文件）
├── persistent.py      # SQLite 持久化层
├── tiers.py           # 段位系统定义
├── gift_resolver.py   # 礼物别名解析
├── data_soups.py      # 海龟汤题库（15 题）
└── data/
    └── persistent.db  # SQLite 数据库（自动创建）

start_all.bat          # 一键启动
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 嵌入式前端页面 |
| WS | `/ws` | WebSocket 游戏连接 |
| GET | `/api/game/difficulties` | 获取难度列表 |
| GET | `/api/leaderboard` | 排行榜 |
| GET | `/api/signin?user=` | 查询签到状态 |
| POST | `/api/signin?user=` | 执行签到 |
| GET | `/api/gift/aliases` | 礼物别名列表 |
| POST | `/api/gift/aliases` | 添加/更新别名 |
| DELETE | `/api/gift/aliases/{alias}` | 删除别名 |
| GET | `/api/triggers` | 触发器列表 |
| POST | `/api/triggers` | 添加触发器 |
| DELETE | `/api/triggers/{id}` | 删除触发器 |
| POST | `/api/gift/buy` | 购买礼物 |
| GET | `/api/coin/balance?user=` | 查询金币余额 |

## WebSocket 消息

- `score_update` — 积分变化通知
- `tier_up` — 段位升级动画
- `gift_effect` — 礼物特效 + 连击信息
- `reveal_update` — 揭示进度更新
- `milestone` — 里程碑提示
- `combo_start` / `combo_end` — 连击状态
- `game_start` — 游戏开始
- `signin_status` — 签到结果
