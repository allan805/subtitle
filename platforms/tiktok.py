"""TikTok 平台 —— 标题/ID/字幕获取

策略:
1. yt-dlp 尝试获取 CC 字幕
2. 无字幕时，下载音频 + whisper 语音转文字（可选依赖）

whisper 安装:  pip install openai-whisper
"""
import subprocess
import json
import os
import tempfile

from core.cookies import cookie_args


def get_info(url: str, browser: str) -> dict:
    cmd = ["yt-dlp", "--dump-json", "--skip-download", url]
    cmd.extend(cookie_args(browser))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"yt-dlp 获取 TikTok 信息失败: {result.stderr[:200]}")

    data = json.loads(result.stdout)
    return {
        "platform": "tiktok",
        "id": data.get("id") or data.get("webpage_url_basename", "unknown"),
        "title": data.get("title") or data.get("description", "unknown")[:80],
    }


def get_subtitle(url: str, lang: str, browser: str = None, log_func=None) -> dict:
    result = _ytdlp_subtitle(url, lang, browser)
    if result:
        return result
    return _whisper_transcribe(url, lang, browser)


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


def _whisper_transcribe(url: str, lang: str, browser: str) -> dict:
    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "TikTok 视频无可用字幕，且未安装 whisper。\n"
            "如需自动转录，请运行:  pip install openai-whisper"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")

        cmd = [
            "yt-dlp", url,
            "-x", "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", audio_path,
        ]
        cmd.extend(cookie_args(browser))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.exists(audio_path):
            raise RuntimeError(f"下载音频失败: {result.stderr[:200]}")

        model = whisper.load_model("base")
        whisper_lang = lang.split("-")[0] if lang else None

        result = model.transcribe(audio_path, language=whisper_lang, verbose=False)

        segments = result.get("segments", [])
        text = result.get("text", "").strip()

        srt_lines = []
        for i, seg in enumerate(segments, 1):
            start = seg["start"]
            end = seg["end"]
            content = seg["text"].strip()
            srt_lines.append(
                f"{i}\n{_sec_to_srt_time(start)} --> {_sec_to_srt_time(end)}\n{content}\n"
            )

        return {
            "text": text,
            "srt": "\n".join(srt_lines),
            "source": "whisper",
        }


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
