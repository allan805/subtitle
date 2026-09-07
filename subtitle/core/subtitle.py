"""字幕下载统一接口"""
import os

from core.filename import make_filename
from core.detector import detect_platform


def _get_platform_module(platform: str):
    if platform == "youtube":
        import platforms.youtube as mod
    elif platform == "bilibili":
        import platforms.bilibili as mod
    elif platform == "tiktok":
        import platforms.tiktok as mod
    elif platform == "douyin":
        import platforms.douyin as mod
    else:
        return None
    return mod


def get_video_info(url: str, browser: str) -> dict:
    platform = detect_platform(url)
    if platform == "unknown":
        raise ValueError(f"无法识别平台: {url}")
    mod = _get_platform_module(platform)
    if mod is None:
        raise ValueError(f"不支持的平台: {platform}")
    return mod.get_info(url, browser)


def download_subtitle(url: str, lang: str, browser: str, log_func=None) -> dict:
    def log(msg):
        if log_func:
            log_func(msg)

    platform = detect_platform(url)
    log(f"\n平台: {platform}\n")

    mod = _get_platform_module(platform)
    if mod is None:
        raise ValueError(f"不支持的平台: {platform}")

    log("获取视频信息...\n")
    info = mod.get_info(url, browser)
    log(f"ID: {info['id']}\n")
    log(f"标题: {info['title']}\n")

    log("下载字幕...\n")
    try:
        result = mod.get_subtitle(url, lang, browser, log_func=log_func)
    except TypeError:
        # 兼容旧版平台模块（无 log_func 参数）
        result = mod.get_subtitle(url, lang, browser)

    if result is None or not result.get("text"):
        raise RuntimeError("未能获取到字幕，该视频可能没有字幕或需要登录")

    log(f"字幕来源: {result.get('source', 'unknown')}\n")
    log(f"字幕长度: {len(result['text'])} 字符\n")

    return {
        "info": info,
        "text": result["text"],
        "srt": result.get("srt", ""),
        "source": result.get("source", "unknown"),
    }


def save_subtitle(result: dict, folder: str, log_func=None):
    def log(msg):
        if log_func:
            log_func(msg)

    info = result["info"]
    filename = make_filename(info)
    os.makedirs(folder, exist_ok=True)

    txt_path = os.path.join(folder, filename + ".txt")
    srt_path = os.path.join(folder, filename + ".srt")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(result["text"])
    log(f"\n保存 TXT: {txt_path}\n")

    if result.get("srt"):
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(result["srt"])
        log(f"保存 SRT: {srt_path}\n")

    return txt_path, srt_path
