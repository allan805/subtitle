"""核心模块"""
from core.detector import detect_platform
from core.filename import make_filename, clean
from core.cookies import cookie_args
from core.subtitle import get_video_info, download_subtitle, save_subtitle

__all__ = [
    "detect_platform",
    "make_filename",
    "clean",
    "cookie_args",
    "get_video_info",
    "download_subtitle",
    "save_subtitle",
]
