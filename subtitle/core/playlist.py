"""播放列表/频道批量字幕下载

支持:
- YouTube 播放列表 (playlist?list=...)
- YouTube 频道 (@channel, /channel/..., /c/..., /user/...)
- Bilibili 合集/列表 (/list/...)
- Bilibili 收藏夹 (/favlist?fid=...)
- Bilibili UP主空间视频 (/space/.../video)
- Bilibili 频道 (/space/.../channel/...)

核心依赖: yt-dlp --flat-playlist
"""
import re
import subprocess
import os

from core.detector import detect_platform
from core.subtitle import download_subtitle, save_subtitle


# ========== URL 类型判断 ==========

def is_collection_url(url: str) -> tuple:
    """
    判断 URL 是否为播放列表或频道
    返回: (is_collection, collection_type)
    collection_type: "playlist", "channel", "single"
    """
    url_lower = url.lower().strip()

    # YouTube 播放列表
    if "youtube.com/playlist" in url_lower:
        return True, "playlist"
    # YouTube 播放列表（短形式，含 list= 参数但不含 watch?v=）
    if "list=" in url_lower and "watch?v=" not in url_lower:
        return True, "playlist"

    # YouTube 频道
    youtube_channel_patterns = [
        r"youtube\.com/@[\w-]+",
        r"youtube\.com/channel/[\w-]+",
        r"youtube\.com/c/[\w-]+",
        r"youtube\.com/user/[\w-]+",
    ]
    for p in youtube_channel_patterns:
        if re.search(p, url_lower):
            return True, "channel"

    # Bilibili 播放列表/合集/收藏夹
    bilibili_list_patterns = [
        r"bilibili\.com/list/",
        r"bilibili\.com/medialist/",
        r"space\.bilibili\.com/\d+/channel/",
        r"bilibili\.com/favlist",
    ]
    for p in bilibili_list_patterns:
        if re.search(p, url_lower):
            return True, "playlist"

    # Bilibili UP主空间（视频页）
    if re.search(r"space\.bilibili\.com/\d+/video", url_lower):
        return True, "channel"

    return False, "single"


# ========== 视频列表提取 ==========

def extract_video_urls(url: str, browser: str, log_func=None) -> list:
    """使用 yt-dlp 提取播放列表/频道中的所有视频 URL"""
    def log(msg):
        if log_func:
            log_func(msg)

    log(f"\n🔍 正在提取视频列表，请稍候...\n")

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(webpage_url)s",
        "--skip-download",
        url,
    ]

    if browser and browser != "none":
        cmd.extend(["--cookies-from-browser", browser])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 频道可能视频很多，给 3 分钟
        )

        # yt-dlp 有时即使 stderr 有警告，stdout 也能输出结果
        urls = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and line.startswith("http"):
                urls.append(line)

        # 去重并保持顺序
        seen = set()
        unique_urls = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        log(f"✅ 发现 {len(unique_urls)} 个视频\n")
        return unique_urls

    except subprocess.TimeoutExpired:
        raise RuntimeError("提取视频列表超时（超过3分钟），请检查网络连接或链接是否有效")
    except Exception as e:
        raise RuntimeError(f"提取视频列表失败: {str(e)}")


# ========== 批量下载 ==========

def download_collection_subtitles(
    url: str,
    lang: str,
    browser: str,
    folder: str,
    log_func=None,
    progress_callback=None,
) -> dict:
    """
    批量下载播放列表/频道的字幕

    返回: {
        "total": 总数,
        "success": 成功数,
        "failed": 失败数,
        "failed_urls": 失败的URL列表,
        "folder": 保存目录,
    }
    """
    def log(msg):
        if log_func:
            log_func(msg)

    video_urls = extract_video_urls(url, browser, log_func=log_func)

    if not video_urls:
        raise RuntimeError("未从该链接中提取到任何视频，请确认链接正确且 yt-dlp 已安装")

    total = len(video_urls)
    success = 0
    failed = 0
    failed_urls = []

    log(f"\n{'='*50}\n")
    log(f"🚀 开始批量下载，共 {total} 个视频\n")
    log(f"{'='*50}\n")

    for idx, video_url in enumerate(video_urls, 1):
        log(f"\n📹 [{idx}/{total}] 处理中...\n")
        log(f"链接: {video_url}\n")

        if progress_callback:
            progress_callback(idx, total, video_url)

        try:
            result = download_subtitle(
                video_url, lang, browser,
                log_func=log_func,
            )

            save_subtitle(result, folder, log_func=log_func)
            success += 1
            log(f"✅ [{idx}/{total}] 完成\n")

        except Exception as e:
            failed += 1
            failed_urls.append(video_url)
            log(f"❌ [{idx}/{total}] 失败: {str(e)}\n")

    log(f"\n{'='*50}\n")
    log(f"📊 批量下载完成!\n")
    log(f"   总计: {total}\n")
    log(f"   成功: {success}\n")
    log(f"   失败: {failed}\n")
    log(f"{'='*50}\n")

    if failed_urls:
        log(f"\n⚠️ 失败的视频:\n")
        for u in failed_urls:
            log(f"   - {u}\n")

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "failed_urls": failed_urls,
        "folder": folder,
    }
