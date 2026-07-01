"""
CCcat 海龟汤 — LLM API 分类服务
兼容 OpenAI / DeepSeek / 任何 OpenAI-compatible API

Endpoints:
  POST /classify     — 弹幕三分类（是 / 不是 / 是也不是）
  POST /hint         — 根据问答历史生成方向引导提示
  POST /gift-solicit — 生成礼物索要话术
  GET  /health       — 健康检查
"""
import time
import re
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import uvicorn

# ── Config from env ──
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-your-key-here")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

app = FastAPI(title="Danmaku Classifier (LLM API)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Layer 1: Rule filter ──
IRRELEVANT_PATTERNS = [
    re.compile(r'^[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+$'),
    re.compile(r'^(6{2,}|666+|哈哈哈|呵呵|嘿嘿|哈哈+)+$'),
    re.compile(r'^(主播|老师|大佬|好厉害|加油|来了|签到|打卡|第一)+'),
    re.compile(r'^.{0,2}$'),
]

def rule_filter(text: str) -> str | None:
    for p in IRRELEVANT_PATTERNS:
        if p.search(text):
            return None
    return text

# ── Layer 2: LLM classify ──
CLASSIFY_SYSTEM_PROMPT = """你是海龟汤游戏的答案判断器。根据汤底和关键词，判断玩家弹幕与答案的相关性。
只回复以下三个选项之一：
- 是：弹幕内容非常接近正确答案或包含核心关键词
- 不是：弹幕内容与正确答案完全无关
- 是也不是：弹幕部分正确但不完整，或者方向对但细节不对"""

async def llm_classify(text: str, answer: str, keywords: list[str]) -> str:
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": f"汤底: {answer}\n关键词: {'、'.join(keywords)}\n玩家弹幕: \"{text}\""},
            ],
            max_tokens=10,
            temperature=0.1,
        )
        response = resp.choices[0].message.content.strip()
        if "是也不是" in response:
            return "是也不是"
        elif "是" in response:
            return "是"
        else:
            return "不是"
    except Exception as e:
        print(f"[LLM] API error: {e}")
        return "不是"

# ── Layer 3: Hint generation ──
HINT_SYSTEM_PROMPT = """你是海龟汤游戏的提示助手。根据问答历史记录，分析玩家已经猜过的方向和尚未探索的方面。
给出一个简短的方向引导提示，帮助玩家继续推理。提示应该:
1. 基于已提出的问题和回答
2. 引导玩家思考尚未被否定的方向
3. 不超过20字
4. 用中文回复，只说提示内容"""

async def llm_hint(qa_history: list[dict], answer: str, keywords: list[str]) -> str:
    try:
        history_text = "\n".join(
            [f"Q: {q.get('content', q.get('text', ''))}  →  A: {q.get('answerType', q.get('answer', ''))}"
             for q in qa_history[-10:]]  # 只看最近10条
        )
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": HINT_SYSTEM_PROMPT},
                {"role": "user", "content": f"汤底: {answer}\n关键词: {'、'.join(keywords)}\n问答历史:\n{history_text}"},
            ],
            max_tokens=50,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] Hint error: {e}")
        return "想想还有没有其他可能性？"

# ── Layer 4: Gift solicit generation ──
GIFT_SOLICIT_PROMPTS = {
    "人气票": "根据当前游戏气氛，生成一句引导观众送人气票的提示。",
    "啤酒": "根据当前游戏气氛，生成一句引导观众送啤酒来揭示一个字的提示。",
    "棒棒糖": "根据当前游戏气氛，生成一句引导观众送棒棒糖来揭示一句话的提示。",
    "墨镜": "根据当前游戏气氛，生成一句引导观众送墨镜直接通关的提示。",
    "粉丝灯牌": "根据当前游戏气氛，生成一句引导观众上粉丝灯牌的提示。",
    "点赞": "根据当前游戏气氛，生成一句引导观众点赞的提示。",
}

GIFT_SOLICIT_SYSTEM_PROMPT = """你是海龟汤游戏的主播助手。根据游戏当前状态和礼物类型，生成一句自然、有趣的礼物索要话术。
要求：
1. 话术要结合当前游戏进度
2. 自然流畅，像主播说出来的话
3. 不超过20字
4. 用中文回复，只说话术内容"""

async def llm_gift_solicit(gift_type: str, context: dict) -> str:
    try:
        context_str = f"当前进度: {context.get('revealProgress', 0)*100:.0f}%\n提问数: {context.get('questionCount', 0)}\n阶段: {context.get('phase', 'playing')}"
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": GIFT_SOLICIT_SYSTEM_PROMPT},
                {"role": "user", "content": f"礼物类型: {gift_type}\n{context_str}\n请生成一句礼物索要话术。"},
            ],
            max_tokens=50,
            temperature=0.8,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] Gift solicit error: {e}")
        # Fallback static prompts
        fallbacks = {
            "人气票": "动动小手送个人气票，给主播加加油！",
            "啤酒": "送一瓶啤酒，帮你揭示一个关键线索！",
            "棒棒糖": "来个棒棒糖，主播帮你揭开一句话！",
            "墨镜": "送个墨镜，直接通关看真相！",
            "粉丝灯牌": "点亮粉丝灯牌，加入粉丝团！",
            "点赞": "点点赞，攒到500赞自动揭示一个字！",
        }
        return fallbacks.get(gift_type, "感谢大家的支持！")

# ── Request / Response Models ──

class ClassifyRequest(BaseModel):
    text: str
    answer: str
    keywords: list[str]

class ClassifyResponse(BaseModel):
    text: str
    answerType: str
    layer: str
    latencyMs: float

class HintRequest(BaseModel):
    qaHistory: list[dict]
    answer: str
    keywords: list[str]
    questionCount: int = 0

class HintResponse(BaseModel):
    hint: str

class GiftSolicitRequest(BaseModel):
    giftType: str
    context: dict = {}

class GiftSolicitResponse(BaseModel):
    script: str
    giftType: str

# ── Endpoints ──

@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest):
    t0 = time.time()
    filtered = rule_filter(req.text)
    if filtered is None:
        return ClassifyResponse(text=req.text, answerType="不是", layer="rule", latencyMs=(time.time()-t0)*1000)
    result = await llm_classify(req.text, req.answer, req.keywords)
    return ClassifyResponse(text=req.text, answerType=result, layer="llm", latencyMs=(time.time()-t0)*1000)

@app.post("/hint", response_model=HintResponse)
async def hint(req: HintRequest):
    t0 = time.time()
    hint_text = await llm_hint(req.qaHistory, req.answer, req.keywords)
    return HintResponse(hint=hint_text)

@app.post("/gift-solicit", response_model=GiftSolicitResponse)
async def gift_solicit(req: GiftSolicitRequest):
    t0 = time.time()
    script = await llm_gift_solicit(req.giftType, req.context)
    return GiftSolicitResponse(script=script, giftType=req.giftType)

@app.get("/health")
async def health():
    return {"status": "ok", "model": LLM_MODEL, "api_base": LLM_BASE_URL}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3009)
