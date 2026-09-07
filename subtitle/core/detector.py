"""平台检测模块"""
import re


PLATFORM_PATTERNS = {
    "youtube": [r"youtube\.com", r"youtu\.be"],
    "bilibili": [r"bilibili\.com", r"b23\.tv"],
    "tiktok": [r"tiktok\.com"],
    "douyin": [r"douyin\.com", r"v\.douyin\.com"],
}


def detect_platform(url: str) -> str:
    """根据 URL 判断视频平台"""
    url_lower = url.lower().strip()
    for platform, patterns in PLATFORM_PATTERNS.items():
        if any(re.search(p, url_lower) for p in patterns):
            return platform
    return "unknown"
