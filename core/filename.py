"""文件名处理模块 —— 统一格式: 平台_ID_标题"""
import re

FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|]')


def clean(text: str) -> str:
    if not text:
        text = "unknown"
    text = FORBIDDEN_CHARS.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_filename(info: dict) -> str:
    platform = info.get("platform", "unknown")
    vid = info.get("id", "unknown")
    title = info.get("title", "unknown")
    return clean(f"{platform}_{vid}_{title}")
