"""YouTube 平台 —— 标题/ID/字幕获取

策略:
1. 标题: requests 抓取页面 HTML 提取 → 失败回退 yt-dlp
2. 字幕: youtube-transcript-api 优先 → yt-dlp 备用
   语言回退: 用户语言 → 英语 → 列出可用语言
"""
import re
import html as html_module
import requests
import subprocess
import os
import tempfile

from core.cookies import cookie_args


YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_video_id(url: str) -> str:
    patterns = [
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/live/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _get_title_from_html(video_id: str) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(url, headers=YT_HEADERS, timeout=15)
        html = resp.text

        m = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});\s*</script>', html, re.DOTALL)
        if m:
            import json
            try:
                data = json.loads(m.group(1))
                title = data.get("videoDetails", {}).get("title")
                if title:
                    return html_module.unescape(title)
            except (json.JSONDecodeError, AttributeError):
                pass

        m = re.search(
            r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
            html,
        )
        if m:
            return html_module.unescape(m.group(1))

        m = re.search(r'<title>([^<]+)</title>', html)
        if m:
            return html_module.unescape(m.group(1).replace(" - YouTube", "").strip())

    except Exception:
        pass
    return None


def _get_title_from_ytdlp(url: str, browser: str) -> str:
    cmd = ["yt-dlp", "--print", "%(title)s", "--skip-download", url]
    cmd.extend(cookie_args(browser))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        title = result.stdout.strip()
        if title:
            return title
    except Exception:
        pass
    return "unknown_title"


def get_info(url: str, browser: str = None) -> dict:
    video_id = _extract_video_id(url)
    if not video_id:
        raise ValueError(f"无法从 URL 提取 YouTube 视频 ID: {url}")

    title = _get_title_from_html(video_id)
    if not title:
        title = _get_title_from_ytdlp(url, browser)

    return {
        "platform": "youtube",
        "id": video_id,
        "title": title,
    }


def get_subtitle(url: str, lang: str, browser: str = None, log_func=None) -> dict:
    api_result = _try_transcript_api(url, lang)
    if api_result:
        return api_result

    ytdlp_result = _ytdlp_subtitle(url, lang, browser)
    if ytdlp_result:
        return ytdlp_result

    ytdlp_result = _ytdlp_subtitle(url, "all", browser)
    if ytdlp_result:
        return ytdlp_result

    raise RuntimeError("YouTube 字幕获取失败: API 和 yt-dlp 均无法获取字幕")


def _try_transcript_api(url: str, lang: str) -> dict:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

        video_id = _extract_video_id(url)
        if not video_id:
            return None

        api = YouTubeTranscriptApi()
        languages_to_try = [lang]
        if lang not in ("en", "en-US", "en-GB"):
            languages_to_try.append("en")

        for try_lang in languages_to_try:
            try:
                data = api.fetch(video_id, languages=[try_lang])
                text = "\n".join(x.text for x in data)
                srt = _transcript_to_srt(data)
                source_label = f"youtube_transcript_api ({try_lang})"
                if try_lang != lang:
                    source_label += f" [回退: 原语言 {lang} 不可用]"
                return {"text": text, "srt": srt, "source": source_label}
            except NoTranscriptFound:
                continue
            except TranscriptsDisabled:
                return None
    except Exception:
        pass
    return None


def _ytdlp_subtitle(url: str, lang: str, browser: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp", url,
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", lang,
            "--convert-subs", "srt",
            "-o", os.path.join(tmpdir, "sub.%(ext)s"),
        ]
        cmd.extend(cookie_args(browser))

        subprocess.run(cmd, capture_output=True, text=True)

        for ext in [".srt", ".vtt"]:
            for f in os.listdir(tmpdir):
                if f.endswith(ext):
                    path = os.path.join(tmpdir, f)
                    with open(path, "r", encoding="utf-8") as fh:
                        srt_content = fh.read()
                    if srt_content.strip():
                        text_content = _srt_to_text(srt_content)
                        return {"text": text_content, "srt": srt_content, "source": "yt-dlp"}
    return None


def _transcript_to_srt(data) -> str:
    lines = []
    for i, item in enumerate(data, 1):
        start = item.start
        duration = item.duration
        end = start + duration
        lines.append(
            f"{i}\n{_sec_to_srt_time(start)} --> {_sec_to_srt_time(end)}\n{item.text}\n"
        )
    return "\n".join(lines)


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
