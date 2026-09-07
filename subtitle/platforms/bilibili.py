"""Bilibili 平台 —— 标题/ID/字幕获取

策略:
1. yt-dlp 优先（支持 cookies、wbi 签名、AI 字幕 ai-zh）
2. 官方 API 备用

语言映射包含 ai- 前缀（B站 AI 生成字幕）
"""
import requests
import re
import os
import tempfile
import subprocess

from core.cookies import cookie_args


BILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

LANG_MAP = {
    "zh-Hans": ["zh-CN", "zh", "zh-Hans", "chi", "ai-zh"],
    "zh-Hant": ["zh-TW", "zh-HK", "zh-Hant", "ai-zh-Hant"],
    "en":      ["en-US", "en-GB", "en", "eng", "ai-en"],
    "ja":      ["ja-JP", "ja", "jpn", "ai-ja"],
    "ko":      ["ko-KR", "ko", "kor", "ai-ko"],
}


def _extract_bv(url: str) -> str:
    m = re.search(r"BV[a-zA-Z0-9]+", url)
    if m:
        return m.group()
    if "b23.tv" in url:
        try:
            resp = requests.head(url, allow_redirects=True, timeout=10)
            m = re.search(r"BV[a-zA-Z0-9]+", resp.url)
            if m:
                return m.group()
        except Exception:
            pass
    return None


def get_info(url: str, browser: str = None) -> dict:
    bv = _extract_bv(url)
    if not bv:
        raise ValueError(f"无法从 URL 提取 BV 号: {url}")

    api = f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"
    resp = requests.get(api, headers=BILI_HEADERS, timeout=15)
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"B站 API 错误: {data.get('message', '未知错误')}")

    video_data = data["data"]
    return {
        "platform": "bilibili",
        "id": bv,
        "title": video_data.get("title") or "unknown_title",
        "cid": video_data.get("cid"),
        "aid": video_data.get("aid"),
    }


def get_subtitle(url: str, lang: str, browser: str = None, log_func=None) -> dict:
    def log(msg):
        if log_func:
            log_func(msg)

    log("\n[步骤1] 检测可用字幕轨道...\n")
    available_subs = _list_subs_with_ytdlp(url, browser)

    if available_subs:
        log(f"发现字幕轨道: {available_subs}\n")
    else:
        log("未检测到字幕轨道\n")

    log("[步骤2] 尝试 yt-dlp 下载字幕...\n")
    result = _ytdlp_subtitle(url, lang, browser, log)
    if result:
        return result

    log("yt-dlp 下载失败，尝试备用方案...\n")

    log("[步骤3] 尝试 B站官方 API...\n")
    result = _bilibili_api_subtitle(url, lang, log)
    if result:
        return result

    if not available_subs:
        raise RuntimeError(
            "该视频没有检测到字幕轨道。\n"
            "可能原因:\n"
            "1. UP主未上传字幕\n"
            "2. 该视频只有弹幕，没有CC字幕\n"
            "3. 需要登录才能查看AI字幕"
        )
    else:
        raise RuntimeError(
            f"检测到字幕轨道但下载失败。\n"
            f"可用轨道: {available_subs}\n"
            f"请尝试切换语言或确认浏览器已登录B站"
        )


def _list_subs_with_ytdlp(url: str, browser: str) -> list:
    cmd = ["yt-dlp", "--list-subs", "--skip-download", url]
    cmd.extend(cookie_args(browser))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        return []

    subs = []
    skip_keywords = ["available", "language", "formats", "---", "extracting", "extracted",
                     "downloading", "download", "error", "warning"]

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(kw in lower for kw in skip_keywords):
            continue
        if not re.search(r'[a-zA-Z]', line):
            continue
        parts = line.split()
        if parts and len(parts[0]) > 1:
            subs.append(parts[0].strip())
    return subs


def _ytdlp_subtitle(url: str, lang: str, browser: str, log) -> dict:
    bili_langs = LANG_MAP.get(lang, [lang])

    for try_lang in bili_langs:
        log(f"  尝试语言: {try_lang}... ")

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                "yt-dlp", url,
                "--skip-download",
                "--write-subs", "--write-auto-subs",
                "--sub-langs", try_lang,
                "--convert-subs", "srt",
                "-o", os.path.join(tmpdir, "sub.%(ext)s"),
            ]
            cmd.extend(cookie_args(browser))

            subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            found_files = []
            for f in sorted(os.listdir(tmpdir)):
                if f.startswith("sub.") and not f.endswith(".mp4"):
                    found_files.append(f)

            if not found_files:
                log(f"✗ (无字幕文件)\n")
                continue

            for f in found_files:
                path = os.path.join(tmpdir, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        srt_content = fh.read()
                except Exception:
                    continue
                if srt_content.strip():
                    text_content = _srt_to_text(srt_content)
                    log(f"✓ 成功 ({try_lang})\n")
                    return {
                        "text": text_content,
                        "srt": srt_content,
                        "source": f"yt-dlp ({try_lang})"
                    }

        log(f"✗ 失败\n")

    return None


def _bilibili_api_subtitle(url: str, lang: str, log) -> dict:
    try:
        info = get_info(url)
        bv = info["id"]
        cid = info["cid"]

        api = f"https://api.bilibili.com/x/player/wbi/v2?bvid={bv}&cid={cid}"
        resp = requests.get(api, headers=BILI_HEADERS, timeout=15)
        data = resp.json()

        if data.get("code") != 0:
            log(f"  API 错误: {data.get('message')}\n")
            return None

        subtitle_data = data.get("data", {}).get("subtitle", {})
        subtitles = subtitle_data.get("subtitles", [])

        if not subtitles:
            if subtitle_data.get("need_login_subtitle"):
                log("  该视频字幕需要登录\n")
            else:
                log("  API 返回无字幕\n")
            return None

        log(f"  API 发现字幕: {[s.get('lan_doc', s.get('lan', '?')) for s in subtitles]}\n")

        bili_langs = LANG_MAP.get(lang, [lang])
        sub_url = None
        matched_lang = None

        for sub in subtitles:
            sub_lang = sub.get("lan", "")
            for bl in bili_langs:
                if bl.lower() in sub_lang.lower() or sub_lang.lower().startswith(bl.lower()):
                    sub_url = sub["subtitle_url"]
                    matched_lang = sub_lang
                    break
            if sub_url:
                break

        if not sub_url:
            sub_url = subtitles[0]["subtitle_url"]
            matched_lang = subtitles[0].get("lan", "unknown")
            log(f"  未匹配到指定语言，使用第一个可用: {matched_lang}\n")

        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url

        sub_resp = requests.get(sub_url, headers=BILI_HEADERS, timeout=15)
        sub_data = sub_resp.json()

        text, srt = _convert_bilibili_subtitle(sub_data)
        log(f"  API 字幕下载成功 ({matched_lang})\n")
        return {"text": text, "srt": srt, "source": f"bilibili_api ({matched_lang})"}

    except Exception as e:
        log(f"  API 异常: {str(e)}\n")
        return None


def _convert_bilibili_subtitle(data: dict) -> tuple:
    body = data.get("body", [])
    text_lines = []
    srt_lines = []

    for i, item in enumerate(body, 1):
        content = item.get("content", "").strip()
        if not content:
            continue
        start = item.get("from", 0)
        end = item.get("to", 0)
        text_lines.append(content)
        srt_lines.append(
            f"{i}\n{_sec_to_srt_time(start)} --> {_sec_to_srt_time(end)}\n{content}\n"
        )

    return "\n".join(text_lines), "\n".join(srt_lines)


def _srt_to_text(srt_content: str) -> str:
    lines = []
    for line in srt_content.splitlines():
        line = line.strip()
        if not line or line.isdigit() or " --> " in line:
            continue
        lines.append(line)
    return "\n".join(lines)


def _sec_to_srt_time(sec: float) -> str:
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    millis = int((sec - int(sec)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
