"""
CosyVoice3 / Edge TTS 双引擎封装
支持懒加载 CosyVoice3，内建 Edge TTS 轻量引擎。
"""

import io
import sys
import os
from pathlib import Path

_cosyvoice_engine = None
_spk_registered = False

COSYVOICE_DIR = Path(__file__).resolve().parent / "CosyVoice"
PROMPT_TEXT = "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。"
PROMPT_WAV = "zero_shot_prompt.wav"
SPK_ID = "default"

# ── Edge TTS ──
EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
EDGE_RATE = "+0%"
EDGE_VOLUME = "+0%"

# 中文发音人列表
EDGE_CN_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓 (女声·推荐)",
    "zh-CN-XiaoyiNeural": "晓伊 (女声·情感)",
    "zh-CN-YunxiNeural": "云希 (男声)",
    "zh-CN-YunjianNeural": "云健 (男声)",
    "zh-CN-XiaohanNeural": "晓涵 (女声·温柔)",
    "zh-CN-XiaomengNeural": "晓梦 (女声·活泼)",
    "zh-CN-XiaochenNeural": "晓辰 (女声·知性)",
    "zh-CN-XiaomoNeural": "晓墨 (女声·文学)",
    "zh-CN-XiaoruiNeural": "晓睿 (女声·成熟)",
    "zh-CN-XiaoshuangNeural": "晓双 (女声·元气)",
    "zh-CN-XiaoxuanNeural": "晓萱 (女声·亲和)",
    "zh-CN-XiaoyanNeural": "晓颜 (女声·自然)",
    "zh-CN-XiaozhenNeural": "晓珍 (女声·温柔)",
    "zh-CN-YunyangNeural": "云扬 (男声·阳光)",
    "zh-CN-YunyeNeural": "云野 (男声·随性)",
    "zh-CN-YunfanNeural": "云帆 (男声·深沉)",
    "zh-CN-YunhaoNeural": "云皓 (男声·活力)",
}


def list_edge_voices() -> dict:
    """返回 {voice_id: display_name}"""
    return dict(EDGE_CN_VOICES)


def _add_cuda_dlls_to_path():
    """将 pip 安装的 nvidia CUDA 库 DLL 目录加入 PATH，供 onnxruntime 使用。"""
    site_packages = Path(__file__).resolve().parent.parent / "Lib" / "site-packages"
    nvidia_dir = site_packages / "nvidia"
    if not nvidia_dir.exists():
        site_packages = Path(os.__file__).resolve().parent / "site-packages"
        nvidia_dir = site_packages / "nvidia"
    if not nvidia_dir.exists():
        return False
    found = []
    for pkg_name in ["cuda_runtime", "cublas", "cudnn", "cufft", "cusparse", "cuda_nvrtc", "nvjitlink"]:
        bin_dir = nvidia_dir / pkg_name / "bin"
        if bin_dir.exists():
            found.append(str(bin_dir.resolve()))
    if not found:
        return False
    os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")
    return True


# ==================== CosyVoice3 ====================

def _load_cosyvoice():
    global _cosyvoice_engine, _spk_registered
    if _cosyvoice_engine is not None:
        return _cosyvoice_engine

    _add_cuda_dlls_to_path()

    matcha = str(COSYVOICE_DIR / "third_party" / "Matcha-TTS")
    if matcha not in sys.path:
        sys.path.insert(0, matcha)
    cv = str(COSYVOICE_DIR)
    if cv not in sys.path:
        sys.path.insert(0, cv)

    from cosyvoice.cli.cosyvoice import AutoModel

    model_dir = COSYVOICE_DIR / "pretrained_models" / "Fun-CosyVoice3-0.5B"
    _cosyvoice_engine = AutoModel(model_dir=str(model_dir), fp16=True)
    print("[TTS] CosyVoice3 engine loaded")

    prompt_wav_path = str(COSYVOICE_DIR / "asset" / PROMPT_WAV)
    if os.path.exists(prompt_wav_path):
        _cosyvoice_engine.add_zero_shot_spk(PROMPT_TEXT, prompt_wav_path, SPK_ID)
        _spk_registered = True
        print(f"[TTS] Speaker '{SPK_ID}' registered from {PROMPT_WAV}")
    else:
        print(f"[TTS] WARNING: {prompt_wav_path} not found")
    return _cosyvoice_engine


def cosyvoice_available() -> bool:
    try:
        eng = _load_cosyvoice()
        return _spk_registered and SPK_ID in eng.frontend.spk2info
    except Exception:
        return False


def cosyvoice_generate(text: str) -> tuple:
    """Return (sample_rate, wav_bytes) or (None, None) on failure."""
    import soundfile as sf

    try:
        eng = _load_cosyvoice()
        if not _spk_registered:
            return None, None
        buf = io.BytesIO()
        for j in eng.inference_zero_shot(
            text, PROMPT_TEXT,
            str(COSYVOICE_DIR / "asset" / PROMPT_WAV),
            zero_shot_spk_id=SPK_ID, stream=False,
        ):
            sf.write(buf, j["tts_speech"].squeeze().cpu().numpy(), eng.sample_rate, format="WAV")
        buf.seek(0)
        return eng.sample_rate, buf.read()
    except Exception as e:
        print(f"[TTS] CosyVoice3 error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# ==================== Edge TTS ====================

def edge_available() -> bool:
    try:
        import edge_tts
        return True
    except ImportError:
        return False


async def edge_generate_async(text: str, voice: str = None, rate: float = None) -> tuple:
    """Return (sample_rate, mp3_bytes) — Edge TTS 输出 MP3."""
    import edge_tts
    # rate: float → edge-tts 格式 "+XX%" / "-XX%"
    rate_str = EDGE_RATE
    if rate is not None and rate != 1.0:
        pct = int(round((rate - 1.0) * 100))
        rate_str = f"{pct:+d}%"
    communicate = edge_tts.Communicate(
        text, voice=voice or EDGE_VOICE,
        rate=rate_str, volume=EDGE_VOLUME,
    )
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return 24000, audio


def edge_generate(text: str) -> tuple:
    """同步包裹，返回 (24000, mp3_bytes)"""
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            # 已经在 async 上下文中，用 run_coroutine_threadsafe
            import concurrent.futures
            new_loop = asyncio.new_event_loop()
            try:
                result = new_loop.run_until_complete(edge_generate_async(text))
                return result
            finally:
                new_loop.close()
        else:
            return asyncio.run(edge_generate_async(text))
    except Exception as e:
        print(f"[TTS] Edge TTS error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# ==================== 统一入口 ====================

async def async_generate_speech(text: str, engine: str = "cosyvoice", voice: str = None, rate: float = None) -> tuple:
    """
    异步统一入口。Server 端 await 此函数。
    Edge TTS 直接 await，CosyVoice3 用 run_in_executor 避免阻塞。
    """
    import asyncio
    if engine == "edge":
        return await edge_generate_async(text, voice, rate)
    else:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cosyvoice_generate(text))


ENGINES = {
    "cosyvoice": {"label": "CosyVoice3", "available": cosyvoice_available, "generate": cosyvoice_generate},
    "edge": {"label": "Edge TTS", "available": edge_available, "generate": edge_generate},
}


def list_engines() -> dict:
    """返回 {engine_id: {"label": ..., "available": bool}}"""
    return {eid: {"label": info["label"], "available": info["available"]()} for eid, info in ENGINES.items()}


def generate_speech(text: str, engine: str = "cosyvoice") -> tuple:
    """
    统一入口。
    Returns (sample_rate, audio_bytes) or (None, None).
    CosyVoice3 → WAV, Edge TTS → MP3.
    """
    info = ENGINES.get(engine)
    if info is None:
        print(f"[TTS] Unknown engine: {engine}")
        return None, None
    return info["generate"](text)


def is_available(engine: str = "cosyvoice") -> bool:
    info = ENGINES.get(engine)
    if info is None:
        return False
    return info["available"]()
