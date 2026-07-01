# 抖音海龟汤 — 完整改进实施方案 v3

> 目标：基于「CCcat猜词大挑战」原版的商业思维改造「抖音海龟汤」
> 场景：主播直播 → 观众发弹幕/送礼物 → 游戏实时反应
> 目的：提升观众付费率（礼物送出频次） + 优化游戏逻辑

---

## 〇、项目现状速览

### 文件结构
```
C:\Users\27871\OneDrive\Documents\抖音海龟汤\
├── backend/
│   ├── server.py              # 主服务（FastAPI + WebSocket + LLM）
│   ├── data_soups.py          # 15 道海龟汤题库
│   ├── embedded_ui.py         # 嵌入式前端（实际主用）
│   ├── barrage-relay.mjs      # 弹幕中继（可选）
│   ├── tts-relay.cjs          # TTS（可选）
│   └── requirements.txt
├── meoo_frontend/             # React 版前端（暂未深度使用）
├── docs/
│   ├── 原版CCcat猜词解析报告.md  ✅ 已有
│   ├── 游戏优化规划_v2.md      ✅ 已有
│   ├── 付费转化规划_v3_直播场景.md ✅ 已有
│   └── 本文档.md              ✅ 实施手册
├── .env
└── CCcat海龟汤.exe (42MB)
```

### 已完成部分（位于 `backend/server.py`）
- ✅ `CoinSystem` 类（第 78-140 行附近）
- ✅ `GIFT_PRICES` 礼物定价表
- ✅ REST API：`/api/coin/*`、`/api/gift/shop`、`/api/coin/leaderboard`、`/api/coin/state`
- ✅ `handle_gift` 已集成扣费+连击奖励
- ✅ `claim_daily` 每日签到接口

### 待实施部分
- 段位系统（10级）
- 礼物别名映射（让小礼物合并触发）
- 触发器配置（让主播灵活配）
- 嵌入式 UI：金币展示、商店面板、签到、段位徽章、连击指示器
- 难度选择
- 进度里程碑
- 礼物动画增强
- 排行榜增强

---

## 一、目标与成功标准

### 1.1 商业目标
1. **付费率提升**：观众送礼物频次提升 3-5 倍
2. **付费深度**：人均礼物价值提升 2 倍
3. **留存**：日活观众（同一抖音用户连续 3 天进入）提升 5 倍
4. **段位分布**：30% 观众达到黄金段位及以上

### 1.2 体验目标
- 观众送礼物后 1 秒内看到全屏动画反馈
- 段位提升时全屏庆祝
- 进度停滞时自动提示可送的礼物
- 主播无需操作，配置后全自动

### 1.3 验证标准
- 服务启动后游戏在 `http://localhost:3010/` 正常运行
- WebSocket 连接稳定（断线重连）
- 礼物送出后游戏响应 < 200ms
- 前端在 1080p 分辨率下不溢出
- 段位/积分/签到数据在服务重启后保留（SQLite 持久化）

---

## 二、待修改文件清单

| 文件 | 状态 | 主要变更 |
|------|------|---------|
| `backend/server.py` | 🔄 增量修改 | 段位、别名、触发器、积分持久化、签到完整版 |
| `backend/embedded_ui.py` | 🆕 大改 | 金币/段位展示、商店、签到、动画、连击指示器 |
| `backend/data_soups.py` | 🔄 增字段 | 给每道题加 `difficulty`、`tags` 字段 |
| `backend/soups_questions.py` | 🆕 新建 | 海龟汤题目数据（继承自 data_soups.py） |
| `backend/requirements.txt` | 🔄 检查 | 确认 `pywebview` 或类似库 |
| `meoo_frontend/src/stores/gameStore.ts` | 🔄 增字段 | 同步后端字段 |
| `meoo_frontend/src/components/game/GiftPanel.tsx` | 🔄 增强 | 显示价格/购买确认 |
| `docs/本文件.md` | ✅ 本文档 | 实施手册 |

---

## 三、后端实施细节

### 3.1 数据库持久化（新建 `data/persistent.db`）

#### 关键决策
- **存储位置**：`backend/data/persistent.db`（与原版 CCcat 一致）
- **库选择**：SQLite（WAL 模式，原版同款）
- **API**：仅在内存中有，**未持久化**（重启会丢），需新建持久化层

#### 表结构

```sql
-- 用户表：累计积分/段位/连击
CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY,
    score INTEGER DEFAULT 0,         -- 累计积分
    combo INTEGER DEFAULT 0,         -- 当前连击数
    max_combo INTEGER DEFAULT 0,     -- 最高连击
    last_seen REAL,                  -- 最后活跃时间
    achievements TEXT,                -- JSON 数组
    total_gifts INTEGER DEFAULT 0,   -- 礼物总数
    total_coins INTEGER DEFAULT 0    -- 累计消费金币
);

-- 段位历史
CREATE TABLE IF NOT EXISTS tier_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    from_tier TEXT,
    to_tier TEXT,
    score INTEGER,
    timestamp REAL
);

-- 签到表
CREATE TABLE IF NOT EXISTS checkins (
    name TEXT PRIMARY KEY,
    last_day TEXT,
    streak INTEGER DEFAULT 0,
    total_days INTEGER DEFAULT 0
);

-- 礼物别名映射（主播配置）
CREATE TABLE IF NOT EXISTS gift_aliases (
    alias TEXT PRIMARY KEY,
    gifts TEXT,        -- 逗号分隔的真实礼物名
    effect TEXT,       -- 触发效果: like/fan_light/popularity/beer/lollipop/sunglasses
    enabled INTEGER DEFAULT 1
);

-- 触发器（礼物/点赞 → 效果）
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,          -- gift/like/follow/light
    target TEXT,        -- 礼物名或 "*" 任意
    effect TEXT,        -- 效果
    value TEXT,         -- 附加值（如数字）
    enabled INTEGER DEFAULT 1
);

-- 礼物映射默认（双十一）
CREATE TABLE IF NOT EXISTS gift_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    gift_name TEXT,
    amount INTEGER,
    timestamp REAL
);
```

#### 实现步骤
1. 新建 `backend/persistent.py` 模块
2. 封装 `PersistentDB` 类，提供 upsert/select/insert 接口
3. 在 `server.py` 启动时初始化
4. 关闭时关闭连接

### 3.2 段位系统

#### 段位定义（与原版一致）
```python
TIERS = [
    {"id": 0, "name": "黑铁",   "color": "#6B7280", "min_score": 0,        "icon": "🛡️"},
    {"id": 1, "name": "青铜",   "color": "#B45309", "min_score": 100,      "icon": "🥉"},
    {"id": 2, "name": "黄金",   "color": "#F59E0B", "min_score": 500,      "icon": "🥇"},
    {"id": 3, "name": "铂金",   "color": "#06B6D4", "min_score": 2000,     "icon": "💎"},
    {"id": 4, "name": "钻石",   "color": "#3B82F6", "min_score": 5000,     "icon": "💠"},
    {"id": 5, "name": "白银",   "color": "#E5E7EB", "min_score": 10000,    "icon": "⚪"},
    {"id": 6, "name": "王者",   "color": "#A855F7", "min_score": 25000,    "icon": "👑"},
    {"id": 7, "name": "宗师",   "color": "#DC2626", "min_score": 50000,    "icon": "🔥"},
    {"id": 8, "name": "大师",   "color": "#FBBF24", "min_score": 100000,   "icon": "🌟"},
    {"id": 9, "name": "超级王者", "color": "#FF1493", "min_score": 200000, "icon": "⚡"},
]

def get_tier(score: int) -> dict:
    """根据积分返回段位"""
    for tier in reversed(TIERS):
        if score >= tier["min_score"]:
            return tier
    return TIERS[0]
```

#### 积分规则（参考原版 5 档难度）
- 猜对简单题 +10
- 猜对一般题 +15
- 猜对困难题 +20
- 猜对地狱题 +30
- 猜对无人区题 +50
- 礼物（按价格）：`1 抖币 = 1 积分`
- 点赞不加分（避免刷分）

#### 升级判定
```python
def check_tier_up(old_score: int, new_score: int) -> dict | None:
    """积分变化时检查是否升级，返回新段位或 None"""
    old_tier = get_tier(old_score)
    new_tier = get_tier(new_score)
    if new_tier["id"] > old_tier["id"]:
        return {"from": old_tier, "to": new_tier, "delta": new_tier["id"] - old_tier["id"]}
    return None
```

#### WS 消息新增
```json
{
  "type": "tier_up",
  "user": "观众",
  "from_tier": {"id": 1, "name": "青铜"},
  "to_tier": {"id": 2, "name": "黄金"},
  "score": 550,
  "msg": "🎉 恭喜升级到黄金！"
}
```

### 3.3 礼物别名映射

#### 数据模型
```python
# gift_aliases 表
{
  "alias": "玫瑰",           # 显示用别名
  "gifts": "玫瑰花,玫瑰雨,玫瑰棒棒糖",  # 真实礼物名
  "effect": "popularity",     # 触发效果
  "enabled": true
}
```

#### API
- `GET /api/gift/aliases` — 获取所有别名
- `POST /api/gift/aliases` — 新增别名
- `DELETE /api/gift/aliases/{alias}` — 删除
- `PUT /api/gift/aliases/{alias}` — 修改

#### 解析逻辑（核心）
```python
def resolve_gift(gift_name: str) -> str:
    """
    接收真实礼物名，找出对应别名和效果
    优先级：精确匹配别名 > 别名内任一礼物名 > 默认
    """
    aliases = db.get_aliases()  # list[dict]
    for alias in aliases:
        gift_list = alias["gifts"].split(",")
        if gift_name in gift_list:
            return alias["effect"]
    # 默认映射
    default_map = {
        "点赞": "like",
        "粉丝灯牌": "fan_light",
        "人气票": "popularity",
        "啤酒": "beer",
        "棒棒糖": "lollipop",
        "墨镜": "sunglasses",
    }
    return default_map.get(gift_name, "")
```

### 3.4 触发器系统（让主播配置）

#### 配置示例（数据库中）
```
type    target          effect              value
gift    玫瑰花          popularity          -
gift    棒棒糖          lollipop            -
gift    嘉年华          sunglasses          -
gift    *               like                100  # 任意礼物 +100 赞
like    1000            reveal_high_freq    -    # 每1000赞揭示高频字
follow  *               bonus_score         50   # 关注 +50分
```

#### 解析函数
```python
def match_triggers(event_type: str, target: str) -> list:
    """返回匹配的所有触发器"""
    triggers = db.get_enabled_triggers()
    return [t for t in triggers 
            if t["type"] == event_type 
            and (t["target"] == target or t["target"] == "*")]
```

### 3.5 修改 `server.py` 的具体步骤

#### 步骤 1：导入新增模块
```python
# server.py 顶部
from persistent import PersistentDB
from tiers import TIERS, get_tier, check_tier_up
from gift_resolver import resolve_gift
```

#### 步骤 2：初始化数据库（在 app 启动前）
```python
# server.py 中
DB_PATH = Path(__file__).parent / "data" / "persistent.db"
db = PersistentDB(DB_PATH)

# 启动时建表 + 加载
@app.on_event("startup")
async def startup():
    db.init_tables()
    # 默认别名（首次启动时插入）
    if not db.get_aliases():
        db.insert_default_aliases()
```

#### 步骤 3：替换 `handle_danmaku` 加积分
```python
async def handle_danmaku(msg: dict):
    # ... 现有逻辑 ...
    
    # 弹幕猜对加分
    if result in ("是", "是也不是"):
        # 根据 difficulty 加分（需要在 game_start 时存当前难度）
        diff = room.current_difficulty or "medium"
        score_map = {"easy": 10, "medium": 15, "hard": 20, "hell": 30, "void": 50}
        delta = score_map.get(diff, 15)
        await add_score(user, delta)
```

#### 步骤 4：替换 `handle_gift` 集成别名+段位
```python
async def handle_gift(msg: dict):
    user = msg.get("nickname", "观众")
    gift_name = msg.get("giftName", "")
    
    # 通过别名解析真实效果
    effect = resolve_gift(gift_name)
    if not effect:
        return
    
    # 扣金币
    price = GIFT_PRICES.get(effect, 0)
    if price > 0 and not coins.spend(user, price):
        await manager.broadcast({"type":"gift_error", "msg":"金币不足"})
        return
    
    # 加分（按礼物抖币价值）
    gift_value = msg.get("diamondCount", 0)  # 抖音真实抖币
    if gift_value > 0:
        await add_score(user, gift_value)
    
    # 更新连击
    combo = coins.update_combo(user)
    # ... 触发对应效果 ...
```

#### 步骤 5：新增 `add_score` 函数
```python
async def add_score(user: str, delta: int):
    """加分，检查升级"""
    user_data = db.get_user(user)
    if not user_data:
        user_data = {"name": user, "score": 0, "combo": 0, "max_combo": 0}
    old_score = user_data["score"]
    new_score = old_score + delta
    tier_up = check_tier_up(old_score, new_score)
    
    db.upsert_user({
        **user_data,
        "score": new_score,
        "last_seen": time.time(),
        "total_coins": user_data.get("total_coins", 0) + delta,
    })
    
    if tier_up:
        await manager.broadcast({
            "type": "tier_up",
            "user": user,
            **tier_up,
        })
    
    await manager.broadcast({
        "type": "score_update",
        "user": user,
        "score": new_score,
        "tier": get_tier(new_score),
    })
```

#### 步骤 6：新增签到完整版
```python
@app.post("/api/signin")
async def signin(user: str = "default"):
    today = time.strftime("%Y-%m-%d")
    checkin = db.get_checkin(user)
    
    if checkin and checkin["last_day"] == today:
        return {"status": "repeat", "msg": "今天已签到", "streak": checkin["streak"]}
    
    # 判定连续
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if checkin and checkin["last_day"] == yesterday:
        new_streak = checkin["streak"] + 1
    else:
        new_streak = 1
    
    # 计算奖励
    reward_map = {1: 30, 2: 30, 3: 30, 4: 50, 5: 80, 6: 100, 7: 150}
    reward = reward_map.get(new_streak, 50)
    
    db.upsert_checkin({
        "name": user,
        "last_day": today,
        "streak": new_streak,
        "total_days": (checkin or {}).get("total_days", 0) + 1,
    })
    
    coins.add_coins(user, reward)
    return {
        "status": "ok",
        "reward": reward,
        "streak": new_streak,
        "balance": coins.get_balance(user),
    }
```

#### 步骤 7：新增排行榜
```python
@app.get("/api/leaderboard")
async def leaderboard(limit: int = 10):
    users = db.get_top_users(limit)
    result = []
    for u in users:
        tier = get_tier(u["score"])
        result.append({
            "name": u["name"],
            "score": u["score"],
            "tier": tier,
            "combo": u.get("combo", 0),
        })
    return {"leaderboard": result}
```

---

## 四、前端实施细节（embedded_ui.py）

### 4.1 头部改造

#### 当前样式
```
┌─ Header ──────────────────────────────┐
│ 🐢 CCcat海龟汤          🟢 已连接    │
└───────────────────────────────────────┘
```

#### 目标样式
```
┌─ Header ──────────────────────────────────────────────┐
│ 🐢 CCcat海龟汤  📅签到 🔥连击x3   🛡️青铜  🪙100  ⚙️ │
└───────────────────────────────────────────────────────┘
```

#### 改动点
1. 在 header 右上角加 `📅签到` 按钮（点击调签到）
2. 加 `🔥连击x3` 指示器（仅在连击时显示，闪烁）
3. 加 `🛡️青铜` 段位徽章
4. 加 `🪙100` 金币余额
5. 保留 `⚙️` 设置按钮

#### 位置（header HTML 约第 207 行）
```html
<header>
  <div class="header-left">...</div>
  <div class="header-right" style="display:flex;gap:8px;align-items:center;">
    <button class="header-btn" onclick="openSignin()">📅 签到</button>
    <div id="comboIndicator" class="combo-badge" style="display:none">🔥x<span>0</span></div>
    <div id="tierBadge" class="tier-badge" style="display:flex;align-items:center;gap:4px">
      <span id="tierIcon">🛡️</span>
      <span id="tierName">黑铁</span>
    </div>
    <div id="coinBalance" class="coin-badge">🪙 <span>100</span></div>
    <button class="btn btn-ghost" onclick="openSettings()" title="设置">⚙️</button>
  </div>
</header>
```

### 4.2 礼物商店面板

#### UI 设计
```
┌─ 🎁 礼物商店 ─────────────────────────────┐
│  你的余额：🪙 100                            │
│                                              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐│
│  │  啤酒   │ │ 棒棒糖  │ │  人气票  │ │  墨镜  ││
│  │  🍺   │ │  🍭   │ │  ⚡   │ │  🕶  ││
│  │ 50金币  │ │ 80金币  │ │ 30金币  │ │200金币││
│  │ 揭示一字 │ │ 揭示一句 │ │ 方向提示 │ │直接通关││
│  │[购买]   │ │[购买]   │ │[购买]   │ │[购买] ││
│  └────────┘ └────────┘ └────────┘ └────────┘│
│                                              │
│  💎 充值入口（暂未开放）                       │
│                                              │
│              [关闭]                           │
└──────────────────────────────────────────────┘
```

#### HTML 插入位置（控件区下方，约第 213 行 `<div class="main-grid">` 之前）
```html
<!-- 礼物商店触发按钮（放在 gift-grid 上方） -->
<button class="btn btn-outline" onclick="openGiftShop()" style="margin: 4px 0; width: 100%;">
  🎁 礼物商店（升级/效果说明）
</button>

<!-- 礼物商店 overlay -->
<div class="settings-overlay" id="giftShopOverlay" style="display:none">
  <div class="settings-card">
    <h2>🎁 礼物商店</h2>
    <p style="color:#94a3b8;font-size:12px">你的余额：🪙 <span id="shopBalance">100</span></p>
    <div class="gift-shop-grid" id="giftShopGrid">
      <!-- JS 动态渲染 -->
    </div>
    <div class="actions">
      <button class="btn btn-ghost" onclick="closeGiftShop()">关闭</button>
    </div>
  </div>
</div>
```

#### JS 渲染逻辑
```javascript
async function openGiftShop() {
  const overlay = document.getElementById('giftShopOverlay');
  const grid = document.getElementById('giftShopGrid');
  // 拉取礼物列表
  const resp = await fetch('/api/gift/shop').then(r => r.json());
  // 渲染
  const giftIcons = {
    like: '❤️', fan_light: '⭐', popularity: '⚡',
    beer: '🍺', lollipop: '🍭', sunglasses: '🕶️'
  };
  const giftNames = {
    like: '点赞', fan_light: '粉丝灯牌', popularity: '人气票',
    beer: '啤酒', lollipop: '棒棒糖', sunglasses: '墨镜'
  };
  const giftEffects = {
    like: '500赞=1字', fan_light: '揭示1句(限3次)',
    popularity: 'AI方向提示', beer: '揭示1字',
    lollipop: '揭示1整句', sunglasses: '直接通关'
  };
  grid.innerHTML = resp.gifts.filter(g => g.price > 0).map(g => `
    <div class="shop-item">
      <div class="shop-icon">${giftIcons[g.type]}</div>
      <div class="shop-name">${giftNames[g.type]}</div>
      <div class="shop-effect">${giftEffects[g.type]}</div>
      <div class="shop-price">🪙 ${g.price}</div>
      <button class="btn btn-primary" onclick="buyGift('${g.type}')">购买</button>
    </div>
  `).join('');
  // 更新余额
  const user = 'default';
  const bal = await fetch(`/api/coin/balance?user=${user}`).then(r => r.json());
  document.getElementById('shopBalance').textContent = bal.balance;
  overlay.style.display = 'flex';
}

function closeGiftShop() {
  document.getElementById('giftShopOverlay').style.display = 'none';
}

async function buyGift(giftType) {
  // 调接口扣金币
  const resp = await fetch('/api/gift/buy', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({gift_type: giftType, user: 'default'})
  }).then(r => r.json());
  if (resp.ok) {
    showToast(`🎉 购买成功！${giftType} 效果已生效`);
    updateBalanceUI(resp.balance);
    closeGiftShop();
  } else {
    showToast(`❌ ${resp.msg || '购买失败'}`, 'error');
  }
}
```

### 4.3 签到面板

#### UI 设计
```
┌─ 📅 每日签到 ────────────────────────┐
│  今日签到: 第 3 天                    │
│                                       │
│  🎁 奖励：+30 🪙                      │
│                                       │
│  ┌─────────────────────────────────┐ │
│  │      📥 立即签到                │ │
│  └─────────────────────────────────┘ │
│                                       │
│  连续签到奖励：                        │
│  D1  D2  D3  D4  D5  D6  D7          │
│  ✓   ✓   ◉   ─   ─   ─   🎁         │
│  30  30  30  50  80  100 150+棒棒糖  │
│                                       │
│  💎 VIP用户双倍                        │
└───────────────────────────────────────┘
```

#### HTML
```html
<div class="settings-overlay" id="signinOverlay" style="display:none">
  <div class="settings-card">
    <h2>📅 每日签到</h2>
    <div class="signin-info">
      <p>连续签到第 <span id="signinDay">0</span> 天</p>
      <p>今日奖励：+<span id="signinReward">30</span> 🪙</p>
    </div>
    <div class="signin-row" id="signinDays">
      <!-- JS 渲染 7 天格子 -->
    </div>
    <div class="actions">
      <button class="btn btn-primary" id="signinBtn" onclick="doSignin()">📥 立即签到</button>
      <button class="btn btn-ghost" onclick="closeSignin()">关闭</button>
    </div>
  </div>
</div>
```

#### JS
```javascript
async function openSignin() {
  // 拉取签到状态
  const resp = await fetch('/api/signin?user=default').then(r => r.json());
  document.getElementById('signinDay').textContent = resp.streak || 0;
  // 渲染 7 天格子
  const days = [
    {d:1, r:30}, {d:2, r:30}, {d:3, r:30}, {d:4, r:50},
    {d:5, r:80}, {d:6, r:100}, {d:7, r:'150+🎁'}
  ];
  document.getElementById('signinDays').innerHTML = days.map(item => `
    <div class="signin-day ${item.d <= (resp.streak || 0) ? 'done' : ''}">
      <div class="day-num">D${item.d}</div>
      <div class="day-reward">${item.r}</div>
    </div>
  `).join('');
  // 按钮状态
  document.getElementById('signinBtn').disabled = resp.status === 'repeat';
  document.getElementById('signinBtn').textContent = resp.status === 'repeat' ? '✅ 已签到' : '📥 立即签到';
  document.getElementById('signinOverlay').style.display = 'flex';
}

async function doSignin() {
  const resp = await fetch('/api/signin', {method: 'POST'}).then(r => r.json());
  if (resp.status === 'ok') {
    showToast(`🎉 签到成功！+${resp.reward} 金币 (连续 ${resp.streak} 天)`);
    updateBalanceUI(resp.balance);
    setTimeout(() => openSignin(), 500);  // 重新打开刷新
  }
}
```

### 4.4 连击指示器

#### UI 设计
游戏中顶部显示，仅连击时出现，30秒倒计时
```
┌─ 连击 ─────────────────────┐
│  🔥 x3  下次揭示双倍！       │
│  ████████░░░░ 剩余 12秒      │
└─────────────────────────────┘
```

#### HTML（放在控件区下方）
```html
<div id="comboIndicator" class="combo-panel" style="display:none">
  <div class="combo-fire">🔥 x<span id="comboCount">0</span></div>
  <div class="combo-msg" id="comboMsg">连击中！下个礼物有加成！</div>
  <div class="combo-bar">
    <div class="combo-bar-fill" id="comboBarFill"></div>
  </div>
  <div class="combo-timer" id="comboTimer">剩余 30秒</div>
</div>
```

#### CSS（追加到 styles）
```css
.combo-panel {
  background: linear-gradient(135deg, rgba(251,191,36,0.15), rgba(245,158,11,0.05));
  border: 1px solid rgba(251,191,36,0.3);
  border-radius: 12px;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
  overflow: hidden;
}
.combo-panel::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent);
  animation: comboShine 2s infinite;
}
@keyframes comboShine {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
.combo-fire { font-size: 22px; font-weight: 800; color: #fbbf24; }
.combo-msg { font-size: 12px; color: #fde68a; flex: 1; }
.combo-bar {
  flex: 1; height: 4px; background: rgba(255,255,255,0.1);
  border-radius: 2px; overflow: hidden; max-width: 100px;
}
.combo-bar-fill {
  height: 100%; background: linear-gradient(90deg, #fbbf24, #f59e0b);
  width: 100%; transition: width 0.5s linear;
}
.combo-timer { font-size: 11px; color: #fbbf24; }
```

#### JS
```javascript
let comboInterval = null;
let comboSeconds = 0;

function showCombo(count, multiplier) {
  clearInterval(comboInterval);
  comboSeconds = 30;
  const el = document.getElementById('comboIndicator');
  document.getElementById('comboCount').textContent = count;
  const msgMap = {1: '基础效果', 1.5: '下次揭示×1.5', 2: '双倍揭示！', 3: '三倍暴击！'};
  document.getElementById('comboMsg').textContent = msgMap[multiplier] || '';
  el.style.display = 'flex';
  updateComboBar();
  comboInterval = setInterval(() => {
    comboSeconds--;
    if (comboSeconds <= 0) {
      clearInterval(comboInterval);
      el.style.display = 'none';
      return;
    }
    updateComboBar();
    if (comboSeconds <= 5) {
      el.classList.add('urgent');
    }
  }, 1000);
}

function updateComboBar() {
  document.getElementById('comboBarFill').style.width = (comboSeconds / 30 * 100) + '%';
  document.getElementById('comboTimer').textContent = `剩余 ${comboSeconds}秒`;
}
```

#### 触发（在 handle 函数里）
```javascript
// 收到 gift_effect 消息时
if (msg.combo && msg.combo > 1) {
  showCombo(msg.combo, msg.multiplier);
}
```

### 4.5 段位徽章

#### HTML
```html
<div id="tierBadge" class="tier-badge" style="display:flex;align-items:center;gap:4px;padding:4px 10px;border-radius:8px;background:rgba(255,255,255,0.05)">
  <span id="tierIcon">🛡️</span>
  <span id="tierName" style="font-size:12px;font-weight:600">黑铁</span>
</div>
```

#### JS（在 handle score_update 时更新）
```javascript
function updateTierBadge(tier) {
  document.getElementById('tierIcon').textContent = tier.icon;
  document.getElementById('tierName').textContent = tier.name;
  document.getElementById('tierBadge').style.color = tier.color;
}

// 段位升级时全屏动画
function showTierUp(fromTier, toTier) {
  const overlay = document.createElement('div');
  overlay.className = 'tier-up-overlay';
  overlay.innerHTML = `
    <div class="tier-up-content">
      <div class="tier-up-from" style="color:${fromTier.color}">${fromTier.icon} ${fromTier.name}</div>
      <div class="tier-up-arrow">⬇️</div>
      <div class="tier-up-to" style="color:${toTier.color}">${toTier.icon} ${toTier.name}</div>
      <div class="tier-up-msg">🎉 段位提升！</div>
    </div>
  `;
  document.body.appendChild(overlay);
  setTimeout(() => overlay.remove(), 4000);
}
```

#### CSS
```css
.tier-up-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 300; animation: fadeIn 0.3s;
}
.tier-up-content {
  text-align: center; padding: 40px 60px;
  background: linear-gradient(135deg, rgba(0,212,255,0.1), rgba(124,58,237,0.1));
  border: 2px solid #fbbf24; border-radius: 16px;
  animation: scaleIn 0.5s;
}
.tier-up-from, .tier-up-to {
  font-size: 32px; font-weight: 800; margin: 12px 0;
}
.tier-up-arrow { font-size: 36px; color: #fbbf24; }
.tier-up-msg { font-size: 24px; color: #fbbf24; margin-top: 16px; }
@keyframes scaleIn { from { transform: scale(0); } to { transform: scale(1); } }
```

### 4.6 礼物动画增强

#### 当前
```javascript
function showGiftToast(msg) {
  // 简单 toast
}
```

#### 目标
每个礼物有独特的全屏反馈：

| 礼物 | 动画 |
|------|------|
| 🍺 啤酒 | 大啤酒图标从顶部掉落 + 干杯音效 + 揭示字闪烁金色 |
| 🍭 棒棒糖 | 粉色粒子爆裂 + 揭示句子高亮 3 秒 |
| 🕶️ 墨镜 | 遮罩碎裂特效 + 屏幕震动 + 全屏闪光 |
| ⚡ 人气票 | 蓝色电流特效 + 提示弹幕走马灯 |
| ⭐ 灯牌 | 金色光环从中心扩散 |

#### 实现
```javascript
function showGiftEffect(giftType, user, script) {
  switch (giftType) {
    case '啤酒':
    case 'beer':
      showBeerEffect(user);
      break;
    case '棒棒糖':
    case 'lollipop':
      showLollipopEffect(user);
      break;
    case '墨镜':
    case 'sunglasses':
      showSunglassesEffect(user);
      break;
    // ...
  }
}

function showBeerEffect(user) {
  // 大啤酒图标
  const beer = document.createElement('div');
  beer.className = 'gift-fx-beer';
  beer.innerHTML = '🍺';
  document.body.appendChild(beer);
  setTimeout(() => beer.remove(), 1500);
  
  // 弹幕走马灯
  const banner = document.createElement('div');
  banner.className = 'gift-banner';
  banner.innerHTML = `👑 ${user} 送了啤酒！`;
  document.getElementById('giftBannerRow').prepend(banner);
  setTimeout(() => banner.remove(), 5000);
}
```

#### CSS
```css
.gift-fx-beer {
  position: fixed; top: -100px; left: 50%; transform: translateX(-50%);
  font-size: 120px; z-index: 200;
  animation: beerDrop 1.5s cubic-bezier(0.5, 0, 0.5, 1);
}
@keyframes beerDrop {
  0% { top: -100px; transform: translateX(-50%) scale(0.5) rotate(0); }
  50% { top: 40%; transform: translateX(-50%) scale(1.5) rotate(15deg); }
  100% { top: 110%; transform: translateX(-50%) scale(1) rotate(0); opacity: 0; }
}
.gift-banner {
  background: linear-gradient(90deg, rgba(251,191,36,0.2), rgba(245,158,11,0.05));
  border-left: 3px solid #fbbf24;
  padding: 6px 12px; border-radius: 4px;
  font-size: 12px; color: #fbbf24;
  animation: slideIn 0.3s;
}
```

### 4.7 进度里程碑提示

#### 触发点
```javascript
// 在 handle reveal_update 时
const oldPct = lastRevealPct;
const newPct = getPct(msg.charStates);
if (Math.floor(newPct / 25) > Math.floor(oldPct / 25)) {
  const milestones = [25, 50, 75, 90];
  const current = Math.floor(newPct / 25) * 25;
  showMilestone(current);
}
lastRevealPct = newPct;

function showMilestone(pct) {
  const msgs = {
    25: '💡 进展不错！送个🔥人气票获取更多提示？',
    50: '🎯 完成一半了！棒棒糖🍭限时8折！',
    75: '🚀 就差一点了！送墨镜🕶直接通关！',
    90: '🔥 最后冲刺！限时特惠包来一个？'
  };
  const msg = msgs[pct];
  if (msg) {
    const div = document.createElement('div');
    div.className = 'milestone-hint';
    div.innerHTML = msg;
    div.onclick = () => { div.remove(); openGiftShop(); };
    document.getElementById('hintFloat').appendChild(div);
    setTimeout(() => div.remove(), 8000);
  }
}
```

---

## 五、原版 CCcat 商业思维迁移清单

### 5.1 必做（已在新版游戏缺失）

| # | 机制 | 来源 | 实施位置 | 优先级 |
|---|------|------|---------|-------|
| 1 | 段位系统 | `tiers` 字段 | 后端 + 前端徽章 | P0 |
| 2 | 累计积分 | `users.score` 字段 | 后端持久化 + 前端 | P0 |
| 3 | 每日签到 | `checkins` 表 | 已有基础，补全 UI | P0 |
| 4 | 礼物别名映射 | `gift_aliases` 表 | 后端 API + 前端配置 | P1 |
| 5 | 触发器配置 | `triggers` 表 | 后端 + 管理面板 | P1 |
| 6 | 难度 5 档 | `difficulty` 字段 | 题库 + 选择 UI | P1 |
| 7 | 礼物动画 | 前端 | CSS 动画 + JS | P1 |
| 8 | 排行榜 | `users.score` 排序 | 后端 API + 前端 | P1 |
| 9 | 成就系统 | `achievements` 字段 | 后端 + 前端弹窗 | P2 |
| 10 | 主播后台配置 | PyQt5 面板或 web 配置页 | 后端 API | P2 |

### 5.2 不做（不适合海龟汤）
- 主题 24+ 类轮换（海龟汤是故事型不是主题型）
- Boss 战（海龟汤不需要战斗）
- AI 出题（海龟汤有固定故事）

### 5.3 保留（沿用原版逻辑）
- 段位图标 10 级
- 难度倍率 ×1/×1.5/×2/×3/×5
- 礼物别名 → 真实礼物名映射
- 累计积分 → 段位判定

---

## 六、实施步骤（按依赖顺序）

### 阶段 1：数据持久化基础（1 小时）
1. ✅ 已完成：CoinSystem（无需修改）
2. ⬜ 新建 `backend/persistent.py` 实现 `PersistentDB` 类
3. ⬜ 在 `server.py` 启动时初始化 DB
4. ⬜ 添加积分、签到、段位历史的持久化

### 阶段 2：段位系统（1.5 小时）
5. ⬜ 新建 `backend/tiers.py`，实现 `TIERS`、`get_tier`、`check_tier_up`
6. ⬜ 在 `server.py` 加 `add_score` 函数
7. ⬜ `handle_danmaku` 命中加分（按难度）
8. ⬜ `handle_gift` 命中加分（按礼物价值）
9. ⬜ 加 WS 消息 `tier_up` 和 `score_update`

### 阶段 3：礼物别名与触发器（1.5 小时）
10. ⬜ 新建 `backend/gift_resolver.py`，实现别名映射
11. ⬜ 加 API：`/api/gift/aliases` (GET/POST/DELETE)
12. ⬜ 加 API：`/api/triggers` (GET/POST/DELETE)
13. ⬜ 初始化时插入默认别名和触发器

### 阶段 4：签到完整版（1 小时）
14. ⬜ 替换现有 `claim_daily` 为读 DB 版本
15. ⬜ 加 API：`/api/signin` 返回完整状态
16. ⬜ 加 API：`/api/leaderboard` 排行榜

### 阶段 5：前端头部与余额（1.5 小时）
17. ⬜ Header 加签到按钮、连击指示器、段位徽章、金币余额
18. ⬜ 启动时拉取用户状态
19. ⬜ WS 收到 `tier_up`、`score_update` 时更新 UI

### 阶段 6：礼物商店面板（2 小时）
20. ⬜ 写商店 HTML overlay
21. ⬜ 写 `openGiftShop/closeGiftShop/buyGift` JS
22. ⬜ 接 `/api/gift/shop` 渲染列表
23. ⬜ 购买时扣金币、播效果

### 阶段 7：签到面板（1.5 小时）
24. ⬜ 写签到 overlay HTML
25. ⬜ 写 7 天格子渲染
26. ⬜ 调 `/api/signin` 接口

### 阶段 8：礼物动画增强（2 小时）
27. ⬜ 写各礼物专属 CSS 动画
28. ⬜ 写 `showBeerEffect/showLollipopEffect/showSunglassesEffect` 等
29. ⬜ 加弹幕走马灯

### 阶段 9：连击指示器（1 小时）
30. ⬜ 写 combo 面板 HTML+CSS
31. ⬜ 写 `showCombo/updateComboBar` JS
32. ⬜ 收到 `gift_effect.combo` 时触发

### 阶段 10：进度里程碑（1 小时）
33. ⬜ 写 `showMilestone` JS
34. ⬜ 在 reveal_update 时检测
35. ⬜ 浮动气泡 UI

### 阶段 11：难度选择（0.5 小时）
36. ⬜ 写难度选择按钮（开始游戏前）
37. ⬜ 传 difficulty 给后端
38. ⬜ 后端按难度选汤题、算分

### 阶段 12：测试与集成（1.5 小时）
39. ⬜ 启动服务验证 HTTP 200
40. ⬜ 测试 WS 连接
41. ⬜ 测试所有交互流程
42. ⬜ 编写 README 更新

**总工作量约 16 小时**（按 1 人 1 天 8 小时计算，约 2 天）

---

## 七、API 接口契约汇总

### 7.1 已有 API（保持不变）
- `GET /api/coin/balance?user=X`
- `POST /api/coin/daily?user=X`
- `POST /api/coin/recharge?user=X&amount=N`
- `GET /api/coin/leaderboard`
- `GET /api/gift/shop`
- `GET /api/coin/state?user=X`

### 7.2 新增 API

```
POST /api/signin
  参数: ?user=X
  返回: {status, reward, streak, balance}

GET /api/leaderboard?limit=10
  返回: {leaderboard: [{name, score, tier, combo}]}

GET /api/gift/aliases
  返回: {aliases: [{alias, gifts, effect, enabled}]}

POST /api/gift/aliases
  body: {alias, gifts, effect, enabled}
  返回: {ok, alias}

DELETE /api/gift/aliases/{alias}
  返回: {ok}

GET /api/triggers
  返回: {triggers: [{id, type, target, effect, value, enabled}]}

POST /api/triggers
  body: {type, target, effect, value, enabled}
  返回: {ok}

POST /api/gift/buy
  body: {gift_type, user}
  返回: {ok, balance} 或 {ok: false, msg}

POST /api/game/start?difficulty=medium
  返回: {ok, surface}

GET /api/game/state
  返回: 完整房间状态
```

### 7.3 新增 WS 消息（客户端 → 服务端）

```json
{ "type": "buy_gift", "gift_type": "beer", "user": "default" }
{ "type": "open_signin" }
{ "type": "open_shop" }
```

### 7.4 新增 WS 消息（服务端 → 客户端）

```json
{ "type": "score_update", "user": "X", "score": 550, "tier": {"id": 2, "name": "黄金", "icon": "🥇", "color": "#F59E0B"} }
{ "type": "tier_up", "user": "X", "from_tier": {...}, "to_tier": {...}, "delta": 1 }
{ "type": "leaderboard_update", "leaderboard": [...] }
{ "type": "signin_status", "streak": 3, "reward": 30, "today_done": true }
{ "type": "milestone", "pct": 50, "msg": "🎯 完成一半了！" }
{ "type": "gift_anim", "gift_type": "beer", "user": "X" }
{ "type": "combo_start", "count": 3, "multiplier": 1.5 }
{ "type": "combo_end" }
```

---

## 八、视觉设计规范

### 8.1 颜色
```
主色（青色）: #00d4ff
次色（紫色）: #7c3aed
强调（金）:   #fbbf24
成功（绿）:   #22c55e
警告（黄）:   #f59e0b
错误（红）:   #ef4444
段位颜色:
  黑铁: #6B7280, 青铜: #B45309, 黄金: #F59E0B
  铂金: #06B6D4, 钻石: #3B82F6, 白银: #E5E7EB
  王者: #A855F7, 宗师: #DC2626, 大师: #FBBF24
  超级王者: #FF1493
```

### 8.2 尺寸
- Header 高度：48px
- 主区域最小宽度：1024px
- 礼物按钮：80x80px
- 浮动提示：右下角 320x80px

### 8.3 动效时长
- Toast 显示：3 秒
- 全屏动画：1.5-2 秒
- 段位升级：4 秒
- 连击倒计时：1 秒/格
- 进度里程碑提示：8 秒

---

## 九、测试场景

### 9.1 单元测试（手动验证清单）
- [ ] 启动服务，访问 `http://localhost:3010/` 正常
- [ ] 点击「开始游戏」进入游戏
- [ ] 发送弹幕，QA 气泡出现
- [ ] 弹幕命中字，汤底字揭示
- [ ] 送「啤酒」礼物，揭示1字 + 触发连击
- [ ] 连击 3 次后，揭示变 1.5 倍
- [ ] 点击「签到」按钮，签到成功 +30 金币
- [ ] 点击「礼物商店」，显示列表
- [ ] 购买啤酒，扣金币
- [ ] 累计积分达到 100，段位从黑铁升到青铜
- [ ] 段位升级时全屏动画
- [ ] 进度达 25% 时弹里程碑提示
- [ ] 进度达 100% 时通关
- [ ] 重启服务后用户数据保留
- [ ] 关掉浏览器重开连得上 WS
- [ ] douyinLive 断开时守护自动重连

### 9.2 性能测试
- [ ] 1000 条弹幕不卡顿
- [ ] 礼物 5/秒不丢消息
- [ ] 动画在 1080p 60fps 流畅

### 9.3 边界测试
- [ ] 金币 < 礼物价：送礼失败，弹提示
- [ ] 未开始游戏送礼：不响应
- [ ] 已通关后再送礼：忽略
- [ ] douyinLive 断开：游戏继续（不依赖弹幕输入）

---

## 十、风险与回滚

| 风险 | 缓解 |
|------|------|
| 持久化数据库损坏 | 加 try/except，启动失败时回到内存模式 |
| 段位判定错误 | 单元测试覆盖边界（99/100, 100/101） |
| UI 改动影响旧版 | 保留原版所有元素，新元素默认隐藏 |
| 动画掉帧 | 减少粒子数 + 用 transform 而非 left/top |
| 礼物映射漏配 | 默认映射兜底 |

---

## 十一、文档交付清单

完成后需更新：
- [ ] `README.md` — 启动方式 + 新功能说明
- [ ] `docs/原版CCcat猜词解析报告.md` — 已在 ✅
- [ ] `docs/本文件.md` — 本文档
- [ ] `docs/CHANGELOG.md` — 版本变更记录

---

## 十二、成功验收标准

实施完成后，必须满足：
1. ✅ 段位徽章在头部常驻显示
2. ✅ 累计积分随弹幕/礼物变化
3. ✅ 升级时有全屏动画
4. ✅ 礼物商店可购买 + 扣金币
5. ✅ 每日签到可领金币
6. ✅ 连击有顶部指示器和倒计时
7. ✅ 进度到 25/50/75/90% 有提示
8. ✅ 礼物有专属全屏动画
9. ✅ 数据持久化（重启不丢）
10. ✅ 排行榜功能

---

> **执行者**：Claude Code（或任何支持文件编辑的 AI 编程助手）
> **预计时间**：16 小时工作量（2 个工作日）
> **风险等级**：中（涉及数据库新增、UI 大改）
> **可回滚**：是（所有改动都集中在新增文件 + 增量修改，不动核心 handle_danmaku/handle_gift 逻辑）

---

## 附：当前已有代码位置参考

| 已有逻辑 | 文件 | 行数（约） |
|---------|------|-----------|
| CoinSystem 类 | `backend/server.py` | 78-140 |
| GIFT_PRICES | `backend/server.py` | 62-75 |
| API 端点 | `backend/server.py` | 320-380 |
| handle_danmaku | `backend/server.py` | 523-555 |
| handle_gift | `backend/server.py` | 555-620 |
| 嵌入式 HTML | `backend/embedded_ui.py` | 36KB |
| 礼物面板 HTML | `backend/embedded_ui.py` | 搜索 `gift-grid` |
| 礼物 JS 发送 | `backend/embedded_ui.py` | 搜索 `sendGift` |
| WS 处理 | `backend/embedded_ui.py` | 搜索 `handle(msg)` |
| 题库 | `backend/data_soups.py` | 全文（15 题） |
