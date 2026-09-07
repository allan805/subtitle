#!/usr/bin/env python3
"""全平台字幕助手 v4.0 —— PySide6 GUI (全自动模式)

功能:
  字幕模式:
    - 下载单个视频字幕
    - 下载播放列表字幕
    - 下载频道字幕
    - 自动 fallback: 无字幕 → 下载音频 → whisper.cpp 转录
  视频模式:
    - 下载单个视频
    - 下载播放列表视频
    - 下载频道视频
  智能功能:
    - 剪贴板自动监听，检测到视频链接自动运行
    - 完成后自动切回 Edge 第1个标签页，粘贴提示词并回车

依赖:
    conda activate subtitle
    pip install PySide6 yt-dlp youtube-transcript-api clipboard requests

运行:
    python gui.py
"""
import sys
import os
import json
import subprocess
import re
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QProgressBar, QFileDialog, QMessageBox, QGroupBox,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QColor, QPalette

APP_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = APP_DIR / "subtitle_tool_config.json"

DEFAULT_CONFIG = {
    "lang": "zh-Hans",
    "browser": "none",
    "folder_subtitle": str(APP_DIR / "subtitle"),
    "folder_video": str(APP_DIR / "video"),
    "resolution": "1080p",
    "auto_clipboard": True,
    "auto_whisper_fallback": True,
    "whisper_cpp_path": "/Users/or/gitc/whisper.cpp",
    "whisper_model": "ggml-medium.bin",
    "auto_browser_back": True,
    "browser_tab": 1,
    "prompt_text": "根据文本详细总结这个字幕文件",
    "theme": "dark",
}


# ==================== 配置管理 ====================

def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ==================== URL 检测工具 ====================

def detect_url_type(url: str) -> tuple:
    """判断 URL 类型: (is_collection, collection_type)"""
    u = url.lower().strip()
    if "youtube.com/playlist" in u:
        return True, "playlist"
    if "list=" in u and "watch?v=" not in u:
        return True, "playlist"
    if re.search(r"youtube\.com/@[\w-]+", u):
        return True, "channel"
    if re.search(r"youtube\.com/channel/[\w-]+", u):
        return True, "channel"
    if re.search(r"youtube\.com/c/[\w-]+", u):
        return True, "channel"
    if re.search(r"youtube\.com/user/[\w-]+", u):
        return True, "channel"
    if re.search(r"bilibili\.com/(list|medialist)/", u):
        return True, "playlist"
    if re.search(r"space\.bilibili\.com/\d+/channel/", u):
        return True, "playlist"
    if "bilibili.com/favlist" in u:
        return True, "playlist"
    if re.search(r"space\.bilibili\.com/\d+/video", u):
        return True, "channel"
    return False, "single"


def is_video_url(text: str) -> bool:
    sites = ["youtube.com", "youtu.be", "bilibili.com", "b23.tv",
             "douyin.com", "v.douyin.com", "tiktok.com"]
    return any(s in text.lower() for s in sites)


# ==================== 通用执行器 ====================

def run_cmd(cmd: list, log_func: Optional[Callable] = None,
            timeout: int = 300, cwd: Optional[str] = None) -> dict:
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd,
        )
        lines = []
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if log_func:
                log_func(line + "\n")
        proc.wait(timeout=timeout)
        return {
            "success": proc.returncode == 0,
            "stdout": "\n".join(lines),
            "stderr": "", "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"success": False, "stdout": "", "stderr": "⏱️ 超时", "returncode": -1}
    except FileNotFoundError as e:
        return {"success": False, "stdout": "", "stderr": f"❌ 未找到命令: {e}", "returncode": -1}


def run_ytdlp(args: list, log_func=None, timeout=300, cwd=None) -> dict:
    return run_cmd(["yt-dlp"] + args, log_func, timeout, cwd)


# ==================== 工作线程 ====================

class SubtitleWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    file_signal = Signal(str, str)
    finished_signal = Signal(bool, str, str)  # success, msg, subtitle_text

    def __init__(self, url, lang, browser, folder, scope="auto",
                 whisper_fallback=True, whisper_path="", whisper_model=""):
        super().__init__()
        self.url = url
        self.lang = lang
        self.browser = browser
        self.folder = folder
        self.scope = scope
        self.whisper_fallback = whisper_fallback
        self.whisper_path = whisper_path
        self.whisper_model = whisper_model
        self._is_running = True

    def log(self, msg: str):
        if self._is_running:
            self.log_signal.emit(msg)

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            sys.path.insert(0, str(APP_DIR))
            from core.subtitle import download_subtitle, save_subtitle
            from core.playlist import download_collection_subtitles

            os.makedirs(self.folder, exist_ok=True)

            if self.scope == "auto":
                is_collection, _ = detect_url_type(self.url)
            else:
                is_collection = self.scope in ("playlist", "channel")

            subtitle_text = ""

            if is_collection:
                self.log("🎯 批量字幕模式\n")
                def progress_cb(idx, total, url):
                    self.progress_signal.emit(idx, total)
                result = download_collection_subtitles(
                    self.url, self.lang, self.browser, self.folder,
                    log_func=self.log, progress_callback=progress_cb,
                )
                msg = (f"批量完成! 总计 {result['total']}, "
                       f"成功 {result['success']}, 失败 {result['failed']}")
                self.finished_signal.emit(True, msg, "")
                return

            # 单个视频
            self.log("🎯 单个视频字幕模式\n")
            try:
                result = download_subtitle(
                    self.url, self.lang, self.browser, log_func=self.log
                )
                txt_path, srt_path = save_subtitle(result, self.folder, log_func=self.log)
                subtitle_text = result.get("text", "")
                self.file_signal.emit("TXT", str(txt_path))
                self.file_signal.emit("SRT", str(srt_path))
                self.finished_signal.emit(
                    True, f"字幕已保存:\nTXT: {txt_path}\nSRT: {srt_path}", subtitle_text
                )
                return
            except Exception as e:
                err_msg = str(e)
                self.log(f"\n⚠️ 字幕获取失败: {err_msg}\n")

                # 检查是否是"无字幕"错误
                no_sub_keywords = ["没有字幕", "未能获取到字幕", "NoTranscriptFound",
                                   "TranscriptsDisabled", "no subtitle"]
                is_no_sub = any(k in err_msg for k in no_sub_keywords)

                if not (self.whisper_fallback and is_no_sub):
                    self.finished_signal.emit(False, err_msg, "")
                    return

                # ====== Fallback: 下载音频 → whisper.cpp 转录 ======
                self.log("\n🔄 未找到字幕，启动 Whisper 语音转录...\n")
                self._whisper_fallback()

        except Exception as e:
            self.log(f"\n❌ 错误: {e}\n")
            self.finished_signal.emit(False, str(e), "")

    def _whisper_fallback(self):
        """无字幕时的 fallback 流程: 下载音频 → whisper.cpp 转录"""
        try:
            # 1. 下载音频
            self.log("📥 步骤1: 下载音频...\n")
            audio_dir = Path(self.folder) / ".temp_audio"
            audio_dir.mkdir(exist_ok=True)

            audio_path = audio_dir / "temp_audio.wav"
            ytdlp_args = [
                "-x", "--audio-format", "wav", "--audio-quality", "0",
                "-o", str(audio_path).replace(".wav", ".%(ext)s"),
                "--no-playlist",
            ]
            if self.browser and self.browser.lower() != "none":
                ytdlp_args.extend(["--cookies-from-browser", self.browser.lower()])
            ytdlp_args.append(self.url)

            result = run_ytdlp(ytdlp_args, log_func=self.log, timeout=300)
            if not result["success"]:
                self.finished_signal.emit(False, f"音频下载失败: {result['stderr']}", "")
                return

            # 找到下载的音频文件
            audio_files = list(audio_dir.glob("temp_audio.*"))
            if not audio_files:
                self.finished_signal.emit(False, "音频下载成功但找不到文件", "")
                return
            actual_audio = audio_files[0]
            self.log(f"✅ 音频已下载: {actual_audio}\n")

            # 2. whisper.cpp 转录
            self.log("🎙 步骤2: Whisper.cpp 语音转文字...\n")
            whisper_dir = Path(self.whisper_path)
            model_path = whisper_dir / "models" / self.whisper_model

            if not model_path.exists():
                # 尝试其他位置
                alt_model = whisper_dir / self.whisper_model
                if alt_model.exists():
                    model_path = alt_model
                else:
                    self.finished_signal.emit(
                        False, f"Whisper 模型未找到: {model_path}\n"
                                f"请先下载模型到 {whisper_dir}/models/ 目录", ""
                    )
                    return

            main_bin = whisper_dir / "main"
            if not main_bin.exists():
                main_bin = whisper_dir / "build" / "bin" / "main"
            if not main_bin.exists():
                self.finished_signal.emit(False, f"whisper.cpp 可执行文件未找到: {main_bin}", "")
                return

            out_wav = audio_dir / "temp_audio_16k.wav"
            # 重采样为 16kHz (whisper 要求)
            ffmpeg_resample = [
                "ffmpeg", "-y", "-i", str(actual_audio),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)
            ]
            self.log("🔧 重采样音频为 16kHz...\n")
            res = run_cmd(ffmpeg_resample, log_func=self.log, timeout=60)
            if not res["success"] or not out_wav.exists():
                out_wav = actual_audio  # fallback 用原文件

            whisper_args = [
                str(main_bin), "-m", str(model_path),
                "-f", str(out_wav),
                "-l", self.lang if self.lang != "zh-Hans" else "zh",
                "-osrt",  # 输出 SRT
                "-of", str(audio_dir / "whisper_output"),
            ]
            self.log(f"🚀 运行 Whisper: {' '.join(whisper_args)}\n")
            w_result = run_cmd(whisper_args, log_func=self.log, timeout=600, cwd=str(whisper_dir))

            if not w_result["success"]:
                self.finished_signal.emit(False, f"Whisper 转录失败: {w_result['stderr']}", "")
                return

            # 3. 读取转录结果
            srt_file = audio_dir / "whisper_output.srt"
            txt_file = audio_dir / "whisper_output.txt"

            subtitle_text = ""
            srt_content = ""
            if srt_file.exists():
                srt_content = srt_file.read_text(encoding="utf-8")
                subtitle_text = self._srt_to_text(srt_content)
            elif txt_file.exists():
                subtitle_text = txt_file.read_text(encoding="utf-8")
                srt_content = self._text_to_srt(subtitle_text)
            else:
                # 尝试从 stdout 提取
                subtitle_text = w_result["stdout"]
                srt_content = self._text_to_srt(subtitle_text)

            if not subtitle_text.strip():
                self.finished_signal.emit(False, "Whisper 转录结果为空", "")
                return

            # 4. 保存到目标目录
            from core.filename import make_filename
            from core.subtitle import save_subtitle

            # 获取视频信息用于文件名
            info_result = run_ytdlp(["--print", "%(title)s", "--skip-download", self.url], timeout=30)
            title = info_result["stdout"].strip() or "unknown"
            info = {"platform": "whisper", "id": "audio", "title": title}
            filename = make_filename(info)

            result_dict = {
                "info": info,
                "text": subtitle_text,
                "srt": srt_content,
                "source": "whisper.cpp",
            }
            txt_path, srt_path = save_subtitle(result_dict, self.folder, log_func=self.log)

            # 清理临时文件
            shutil.rmtree(audio_dir, ignore_errors=True)

            self.file_signal.emit("TXT", str(txt_path))
            self.file_signal.emit("SRT", str(srt_path))
            self.finished_signal.emit(
                True,
                f"🎙 Whisper 转录完成!\nTXT: {txt_path}\nSRT: {srt_path}",
                subtitle_text
            )

        except Exception as e:
            self.log(f"\n❌ Whisper fallback 错误: {e}\n")
            self.finished_signal.emit(False, f"Whisper 转录失败: {e}", "")

    @staticmethod
    def _srt_to_text(srt_content: str) -> str:
        lines = []
        for line in srt_content.splitlines():
            line = line.strip()
            if not line or line.isdigit() or " --> " in line:
                continue
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _text_to_srt(text: str) -> str:
        lines = text.splitlines()
        srt_lines = []
        idx = 1
        for line in lines:
            line = line.strip()
            if not line:
                continue
            start_sec = (idx - 1) * 5
            end_sec = idx * 5
            srt_lines.append(f"{idx}")
            srt_lines.append(f"{SubtitleWorker._sec_to_time(start_sec)} --> {SubtitleWorker._sec_to_time(end_sec)}")
            srt_lines.append(line)
            srt_lines.append("")
            idx += 1
        return "\n".join(srt_lines)

    @staticmethod
    def _sec_to_time(sec: int) -> str:
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d},000"


class VideoWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    file_signal = Signal(str, str)
    finished_signal = Signal(bool, str, str)

    def __init__(self, url, resolution, browser, folder, scope="auto"):
        super().__init__()
        self.url = url
        self.resolution = resolution
        self.browser = browser
        self.folder = folder
        self.scope = scope
        self._is_running = True

    def log(self, msg: str):
        if self._is_running:
            self.log_signal.emit(msg)

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            os.makedirs(self.folder, exist_ok=True)

            if self.scope == "auto":
                is_collection, _ = detect_url_type(self.url)
            else:
                is_collection = self.scope in ("playlist", "channel")

            if self.resolution == "best":
                fmt = "bestvideo*+bestaudio/best"
            else:
                h = self.resolution.replace("p", "")
                fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"

            if is_collection:
                out_tpl = str(Path(self.folder) / "%(playlist_title)s/%(playlist_index)03d - %(title).80B [%(id)s].%(ext)s")
                self.log(f"🎯 批量视频下载 ({self.resolution})\n")
            else:
                out_tpl = str(Path(self.folder) / "%(title).100B [%(id)s].%(ext)s")
                self.log(f"🎯 单个视频下载 ({self.resolution})\n")

            args = [
                "-f", fmt, "--merge-output-format", "mp4",
                "-o", out_tpl, "--newline", "--progress", "--no-warnings",
            ]
            if self.browser and self.browser.lower() != "none":
                args.extend(["--cookies-from-browser", self.browser.lower()])
            args.append(self.url)

            result = run_ytdlp(args, log_func=self.log, timeout=600, cwd=str(APP_DIR))

            if result["success"]:
                downloaded = list(Path(self.folder).rglob("*.mp4"))
                files = "\n".join(f"  ✅ {f.relative_to(self.folder)}" for f in downloaded[-5:])
                msg = f"视频下载完成!\n📁 {self.folder}\n📄 文件:\n{files}"
                if len(downloaded) > 5:
                    msg += f"\n  ... 共 {len(downloaded)} 个"
                self.finished_signal.emit(True, msg, "")
            else:
                self.finished_signal.emit(False, result["stderr"] or "未知错误", "")
        except Exception as e:
            self.log(f"\n❌ 错误: {e}\n")
            self.finished_signal.emit(False, str(e), "")


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.worker = None
        self.last_clipboard = ""
        self.is_processing = False

        self.setWindowTitle("全平台字幕助手 v4.0")
        self.setMinimumSize(1100, 820)
        self._setup_ui()
        self._apply_dark_theme()
        self._load_config()
        self._start_clipboard_monitor()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 标题
        title = QLabel("🎬 全平台字幕助手 v4.0")
        title.setFont(QFont("SF Pro Display" if sys.platform == "darwin" else "Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # URL
        url_group = QGroupBox("链接")
        url_layout = QHBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴视频/播放列表/频道链接...")
        url_layout.addWidget(self.url_input)
        self.paste_btn = QPushButton("📋 粘贴")
        self.paste_btn.setFixedWidth(80)
        self.paste_btn.clicked.connect(self._paste_url)
        url_layout.addWidget(self.paste_btn)
        layout.addWidget(url_group)

        # 模式
        mode_group = QGroupBox("模式")
        mode_layout = QVBoxLayout(mode_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("功能:"))
        self.mode_group = QButtonGroup(self)
        self.mode_subtitle = QRadioButton("📝 下载字幕")
        self.mode_video = QRadioButton("🎬 下载视频")
        self.mode_subtitle.setChecked(True)
        self.mode_group.addButton(self.mode_subtitle)
        self.mode_group.addButton(self.mode_video)
        row1.addWidget(self.mode_subtitle)
        row1.addWidget(self.mode_video)
        row1.addStretch()
        mode_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("范围:"))
        self.scope_group = QButtonGroup(self)
        self.scope_auto = QRadioButton("🔍 自动检测")
        self.scope_single = QRadioButton("📹 单个")
        self.scope_playlist = QRadioButton("📋 播放列表")
        self.scope_channel = QRadioButton("📡 频道")
        self.scope_auto.setChecked(True)
        for btn in [self.scope_auto, self.scope_single, self.scope_playlist, self.scope_channel]:
            self.scope_group.addButton(btn)
            row2.addWidget(btn)
        row2.addStretch()
        mode_layout.addLayout(row2)
        layout.addWidget(mode_group)

        # 参数
        params_group = QGroupBox("参数")
        params_layout = QHBoxLayout(params_group)

        params_layout.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["zh-Hans", "zh-Hant", "en", "ja", "ko"])
        params_layout.addWidget(self.lang_combo)

        params_layout.addWidget(QLabel("分辨率:"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(["best", "4K", "1080p", "720p", "480p", "360p"])
        self.res_combo.setCurrentText("1080p")
        params_layout.addWidget(self.res_combo)

        params_layout.addWidget(QLabel("Cookie:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["none", "edge", "chrome", "firefox", "safari"])
        params_layout.addWidget(self.browser_combo)

        params_layout.addWidget(QLabel("保存到:"))
        self.folder_input = QLineEdit()
        self.folder_input.setMinimumWidth(180)
        params_layout.addWidget(self.folder_input, stretch=1)

        self.folder_btn = QPushButton("📁")
        self.folder_btn.setFixedWidth(40)
        self.folder_btn.clicked.connect(self._choose_folder)
        params_layout.addWidget(self.folder_btn)
        layout.addWidget(params_group)

        # 智能选项
        smart_group = QGroupBox("智能选项")
        smart_layout = QHBoxLayout(smart_group)

        self.auto_clipboard_cb = QCheckBox("📋 剪贴板自动监听")
        self.auto_clipboard_cb.setChecked(True)
        self.auto_clipboard_cb.stateChanged.connect(self._toggle_clipboard)
        smart_layout.addWidget(self.auto_clipboard_cb)

        self.auto_whisper_cb = QCheckBox("🎙 无字幕自动 Whisper 转录")
        self.auto_whisper_cb.setChecked(True)
        smart_layout.addWidget(self.auto_whisper_cb)

        self.auto_browser_cb = QCheckBox("🔄 完成后切回浏览器粘贴")
        self.auto_browser_cb.setChecked(True)
        smart_layout.addWidget(self.auto_browser_cb)

        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.clicked.connect(self._open_settings)
        smart_layout.addWidget(self.settings_btn)
        smart_layout.addStretch()
        layout.addWidget(smart_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.download_btn = QPushButton("⬇ 开始下载")
        self.download_btn.setFixedSize(160, 42)
        self.download_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self.download_btn.clicked.connect(self._start_download)
        btn_layout.addWidget(self.download_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setFixedSize(90, 42)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_download)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("就绪")
        self.progress_bar.setFixedHeight(22)
        layout.addWidget(self.progress_bar)

        # 日志
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("SF Mono" if sys.platform == "darwin" else "Consolas", 11))
        log_layout.addWidget(self.log_box)
        layout.addWidget(log_group, stretch=1)

        self.statusBar().showMessage("就绪 | 剪贴板监听中...")

        # 模式切换更新默认路径
        self.mode_subtitle.toggled.connect(self._update_folder_default)

    def _apply_dark_theme(self):
        dark = QPalette()
        dark.setColor(QPalette.Window, QColor("#1e1e2e"))
        dark.setColor(QPalette.WindowText, QColor("#cdd6f4"))
        dark.setColor(QPalette.Base, QColor("#181825"))
        dark.setColor(QPalette.Text, QColor("#cdd6f4"))
        dark.setColor(QPalette.Button, QColor("#45475a"))
        dark.setColor(QPalette.ButtonText, QColor("#cdd6f4"))
        dark.setColor(QPalette.Highlight, QColor("#89b4fa"))
        dark.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
        self.setPalette(dark)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QGroupBox { font-weight: bold; font-size: 13px; border: 1px solid #45475a;
                        border-radius: 8px; margin-top: 10px; padding: 10px 14px;
                        color: #cdd6f4; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #89b4fa; }
            QPushButton { background-color: #89b4fa; color: #1e1e2e; border: none;
                          border-radius: 6px; padding: 6px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:pressed { background-color: #74c7ec; }
            QPushButton:disabled { background-color: #313244; color: #6c7086; }
            QLineEdit, QComboBox { background-color: #313244; color: #cdd6f4;
                                   border: 1px solid #45475a; border-radius: 6px; padding: 5px 8px; }
            QTextEdit { background-color: #181825; color: #cdd6f4;
                        border: 1px solid #313244; border-radius: 6px; padding: 8px; }
            QProgressBar { border: 1px solid #45475a; border-radius: 6px;
                           text-align: center; background-color: #313244; color: #cdd6f4; }
            QProgressBar::chunk { background-color: #a6e3a1; border-radius: 6px; }
            QRadioButton, QCheckBox { color: #cdd6f4; spacing: 6px; }
            QLabel { color: #cdd6f4; }
            QStatusBar { color: #6c7086; }
        """)

    def _load_config(self):
        self.lang_combo.setCurrentText(self.config.get("lang", "zh-Hans"))
        self.browser_combo.setCurrentText(self.config.get("browser", "none"))
        self.res_combo.setCurrentText(self.config.get("resolution", "1080p"))
        self.auto_clipboard_cb.setChecked(self.config.get("auto_clipboard", True))
        self.auto_whisper_cb.setChecked(self.config.get("auto_whisper_fallback", True))
        self.auto_browser_cb.setChecked(self.config.get("auto_browser_back", True))
        self._update_folder_default()

    def _update_folder_default(self):
        if self.mode_subtitle.isChecked():
            default = self.config.get("folder_subtitle", str(APP_DIR / "subtitle"))
        else:
            default = self.config.get("folder_video", str(APP_DIR / "video"))
        self.folder_input.setText(default)

    def _save_ui_config(self):
        self.config["lang"] = self.lang_combo.currentText()
        self.config["browser"] = self.browser_combo.currentText()
        self.config["resolution"] = self.res_combo.currentText()
        self.config["auto_clipboard"] = self.auto_clipboard_cb.isChecked()
        self.config["auto_whisper_fallback"] = self.auto_whisper_cb.isChecked()
        self.config["auto_browser_back"] = self.auto_browser_cb.isChecked()
        save_config(self.config)

    # ==================== 剪贴板监听 ====================

    def _start_clipboard_monitor(self):
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self._check_clipboard)
        self.clipboard_timer.start(2000)  # 每 2 秒检查

    def _toggle_clipboard(self, state):
        if state == Qt.Checked:
            self.clipboard_timer.start()
            self.statusBar().showMessage("剪贴板监听: 开启", 3000)
        else:
            self.clipboard_timer.stop()
            self.statusBar().showMessage("剪贴板监听: 关闭", 3000)

    @Slot()
    def _check_clipboard(self):
        if self.is_processing:
            return
        try:
            from PySide6.QtWidgets import QApplication
            text = QApplication.clipboard().text().strip()
            if not text or text == self.last_clipboard:
                return
            if not is_video_url(text):
                return
            self.last_clipboard = text
            self.url_input.setText(text)
            self.statusBar().showMessage(f"🎯 检测到视频链接，3秒后自动开始...", 5000)
            self.log_box.append(f"\n🎯 剪贴板检测到链接: {text}\n")
            # 3秒后自动开始
            QTimer.singleShot(3000, self._auto_start)
        except Exception:
            pass

    @Slot()
    def _auto_start(self):
        if not self.is_processing and self.url_input.text().strip():
            self.log_box.append("⏳ 自动开始下载...\n")
            self._start_download()

    # ==================== 操作 ====================

    @Slot()
    def _paste_url(self):
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)

    @Slot()
    def _choose_folder(self):
        current = self.folder_input.text() or str(APP_DIR)
        folder = QFileDialog.getExistingDirectory(self, "选择目录", current)
        if folder:
            self.folder_input.setText(folder)
            if self.mode_subtitle.isChecked():
                self.config["folder_subtitle"] = folder
            else:
                self.config["folder_video"] = folder
            save_config(self.config)

    @Slot()
    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入链接")
            return
        if self.is_processing:
            return

        scope = "auto"
        for btn, val in [(self.scope_single, "single"),
                         (self.scope_playlist, "playlist"),
                         (self.scope_channel, "channel")]:
            if btn.isChecked():
                scope = val
                break

        folder = self.folder_input.text().strip() or str(APP_DIR)
        os.makedirs(folder, exist_ok=True)
        self._save_ui_config()

        self.is_processing = True
        self.log_box.clear()
        self.download_btn.setEnabled(False)
        self.download_btn.setText("下载中...")
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备中...")
        self.statusBar().showMessage("处理中...")

        browser = self.browser_combo.currentText()

        if self.mode_subtitle.isChecked():
            self.worker = SubtitleWorker(
                url=url,
                lang=self.lang_combo.currentText(),
                browser=browser,
                folder=folder,
                scope=scope,
                whisper_fallback=self.auto_whisper_cb.isChecked(),
                whisper_path=self.config.get("whisper_cpp_path", "/Users/or/gitc/whisper.cpp"),
                whisper_model=self.config.get("whisper_model", "ggml-medium.bin"),
            )
        else:
            self.worker = VideoWorker(
                url=url,
                resolution=self.res_combo.currentText(),
                browser=browser,
                folder=folder,
                scope=scope,
            )

        self.worker.log_signal.connect(self._append_log)
        self.worker.progress_signal.connect(self._update_progress)
        self.worker.file_signal.connect(self._on_file)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    @Slot()
    def _stop_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.terminate()
            self.worker.wait(3000)
            self._append_log("\n⏹ 用户取消\n")
        self._reset_ui()

    @Slot(str)
    def _append_log(self, text: str):
        self.log_box.append(text.rstrip("\n"))
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(int, int)
    def _update_progress(self, current, total):
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{current}/{total} ({pct}%)")
        else:
            self.progress_bar.setFormat("处理中...")

    @Slot(str, str)
    def _on_file(self, ftype, path):
        self.statusBar().showMessage(f"已保存 {ftype}: {Path(path).name}", 8000)

    @Slot(bool, str, str)
    def _on_finished(self, success, msg, subtitle_text):
        self._reset_ui()
        self.progress_bar.setValue(100 if success else 0)
        self.progress_bar.setFormat("完成" if success else "失败")

        if success:
            self.statusBar().showMessage("✅ " + msg.replace("\n", " ")[:80], 10000)
            self.log_box.append(f"\n{'='*50}\n✅ {msg}\n{'='*50}\n")

            # 自动浏览器回切
            if self.auto_browser_cb.isChecked() and self.mode_subtitle.isChecked():
                self._browser_back_and_paste(subtitle_text)
        else:
            self.statusBar().showMessage("❌ " + msg[:80], 10000)
            self.log_box.append(f"\n{'='*50}\n❌ {msg}\n{'='*50}\n")
            QMessageBox.critical(self, "错误", msg)

    def _reset_ui(self):
        self.is_processing = False
        self.download_btn.setEnabled(True)
        self.download_btn.setText("⬇ 开始下载")
        self.stop_btn.setEnabled(False)

    # ==================== 浏览器回切 ====================

    def _browser_back_and_paste(self, subtitle_text: str):
        """切回 Edge 第1个标签页，粘贴提示词并回车"""
        try:
            prompt = self.config.get("prompt_text",
                                     "根据文本详细总结这个字幕文件")
            tab_index = self.config.get("browser_tab", 1)

            # 复制字幕文本到剪贴板（用于粘贴）
            if subtitle_text and len(subtitle_text) > 10:
                from PySide6.QtWidgets import QApplication
                QApplication.clipboard().setText(subtitle_text)

            # AppleScript 控制 Edge
            script = f"""
tell application "Microsoft Edge"
    activate
    delay 0.3
    tell window 1
        set active tab index to {tab_index}
    end tell
end tell

tell application "System Events"
    delay 0.5
    keystroke "v" using command down
    delay 0.3
    key code 36
    delay 0.2
end tell
"""
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.log_box.append(f"\n🔄 已切回 Edge 第 {tab_index} 个标签页并粘贴\n")
                self.statusBar().showMessage(f"🔄 已切回 Edge 并粘贴提示词", 5000)
            else:
                self.log_box.append(f"\n⚠️ 浏览器切换失败: {result.stderr}\n")
        except Exception as e:
            self.log_box.append(f"\n⚠️ 浏览器回切失败: {e}\n")

    # ==================== 设置对话框 ====================

    @Slot()
    def _open_settings(self):
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox

        dlg = QDialog(self)
        dlg.setWindowTitle("设置")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(self.styleSheet())

        form = QFormLayout(dlg)

        # Whisper 路径
        self._set_whisper_path = QLineEdit(self.config.get("whisper_cpp_path", ""))
        form.addRow("Whisper.cpp 路径:", self._set_whisper_path)

        # Whisper 模型
        self._set_whisper_model = QLineEdit(self.config.get("whisper_model", "ggml-medium.bin"))
        form.addRow("Whisper 模型文件名:", self._set_whisper_model)

        # 浏览器标签页
        self._set_browser_tab = QSpinBox()
        self._set_browser_tab.setRange(1, 20)
        self._set_browser_tab.setValue(self.config.get("browser_tab", 1))
        form.addRow("切回浏览器第几个标签页:", self._set_browser_tab)

        # 提示词
        self._set_prompt = QLineEdit(self.config.get("prompt_text",
                                                      "根据文本详细总结这个字幕文件"))
        form.addRow("粘贴提示词:", self._set_prompt)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(lambda: self._save_settings(dlg))
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        dlg.exec()

    def _save_settings(self, dlg):
        self.config["whisper_cpp_path"] = self._set_whisper_path.text().strip()
        self.config["whisper_model"] = self._set_whisper_model.text().strip()
        self.config["browser_tab"] = self._set_browser_tab.value()
        self.config["prompt_text"] = self._set_prompt.text().strip()
        save_config(self.config)
        dlg.accept()
        QMessageBox.information(self, "设置", "设置已保存")


# ==================== 入口 ====================

def main():
    app = QApplication(sys.argv)
    if sys.platform == "darwin":
        app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
