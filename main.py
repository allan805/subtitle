#!/usr/bin/env python3
"""全平台字幕助手 v3.0 —— PySide6 GUI

功能:
  字幕模式:
    - 下载单个视频字幕
    - 下载播放列表字幕
    - 下载频道字幕
  视频模式:
    - 下载单个视频
    - 下载播放列表视频
    - 下载频道视频

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
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QProgressBar, QFileDialog, QMessageBox, QGroupBox,
    QRadioButton, QButtonGroup, QSpinBox, QCheckBox,
    QStackedWidget, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QIcon

APP_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = APP_DIR / "subtitle_tool_config.json"

DEFAULT_CONFIG = {
    "lang": "zh-Hans",
    "browser": "none",
    "folder_subtitle": str(APP_DIR / "subtitle"),
    "folder_video": str(APP_DIR / "video"),
    "resolution": "1080",
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
    """判断 URL 类型: (is_collection, collection_type)
    collection_type: 'playlist' | 'channel' | 'single'
    """
    u = url.lower().strip()

    # YouTube 播放列表
    if "youtube.com/playlist" in u:
        return True, "playlist"
    if "list=" in u and "watch?v=" not in u:
        return True, "playlist"

    # YouTube 频道
    if re.search(r"youtube\.com/@[\w-]+", u):
        return True, "channel"
    if re.search(r"youtube\.com/channel/[\w-]+", u):
        return True, "channel"
    if re.search(r"youtube\.com/c/[\w-]+", u):
        return True, "channel"
    if re.search(r"youtube\.com/user/[\w-]+", u):
        return True, "channel"

    # Bilibili 列表/合集/收藏夹/频道
    if re.search(r"bilibili\.com/(list|medialist)/", u):
        return True, "playlist"
    if re.search(r"space\.bilibili\.com/\d+/channel/", u):
        return True, "playlist"
    if "bilibili.com/favlist" in u:
        return True, "playlist"

    # Bilibili UP主空间
    if re.search(r"space\.bilibili\.com/\d+/video", u):
        return True, "channel"

    return False, "single"


# ==================== 通用 yt-dlp 执行器 ====================

def run_ytdlp(args: list, log_func: Optional[Callable] = None,
              timeout: int = 300, cwd: Optional[str] = None) -> dict:
    """运行 yt-dlp，返回结构化结果，支持实时日志"""
    cmd = ["yt-dlp"] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
        )
        stdout_lines = []
        for line in proc.stdout:
            line = line.rstrip()
            stdout_lines.append(line)
            if log_func:
                log_func(line + "\n")
        proc.wait(timeout=timeout)
        return {
            "success": proc.returncode == 0,
            "stdout": "\n".join(stdout_lines),
            "stderr": "",
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"success": False, "stdout": "", "stderr": "⏱️ 执行超时", "returncode": -1}
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "❌ 未找到 yt-dlp。请先安装:  pip install yt-dlp",
            "returncode": -1,
        }


# ==================== 工作线程 ====================

class SubtitleWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)   # current, total
    file_signal = Signal(str, str)       # type, filepath
    finished_signal = Signal(bool, str)

    def __init__(self, url, lang, browser, folder, scope="auto"):
        super().__init__()
        self.url = url
        self.lang = lang
        self.browser = browser
        self.folder = folder
        self.scope = scope

    def log(self, msg: str):
        self.log_signal.emit(msg)

    def run(self):
        try:
            sys.path.insert(0, str(APP_DIR))
            from core.subtitle import download_subtitle, save_subtitle
            from core.playlist import download_collection_subtitles

            os.makedirs(self.folder, exist_ok=True)

            # 判断范围
            if self.scope == "auto":
                is_collection, _ = detect_url_type(self.url)
            else:
                is_collection = self.scope in ("playlist", "channel")

            if is_collection:
                self.log("🎯 批量字幕模式\n")

                def progress_cb(idx, total, url):
                    self.progress_signal.emit(idx, total)

                result = download_collection_subtitles(
                    self.url, self.lang, self.browser, self.folder,
                    log_func=self.log,
                    progress_callback=progress_cb,
                )
                msg = (f"批量完成! 总计 {result['total']}, "
                       f"成功 {result['success']}, 失败 {result['failed']}")
                self.finished_signal.emit(True, msg)
            else:
                self.log("🎯 单个视频字幕模式\n")
                result = download_subtitle(
                    self.url, self.lang, self.browser, log_func=self.log
                )
                txt_path, srt_path = save_subtitle(result, self.folder, log_func=self.log)
                self.file_signal.emit("TXT", str(txt_path))
                self.file_signal.emit("SRT", str(srt_path))
                self.finished_signal.emit(
                    True, f"字幕已保存:\nTXT: {txt_path}\nSRT: {srt_path}"
                )
        except Exception as e:
            self.log(f"\n❌ 错误: {e}\n")
            self.finished_signal.emit(False, str(e))


class VideoWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    file_signal = Signal(str, str)
    finished_signal = Signal(bool, str)

    def __init__(self, url, resolution, browser, folder, scope="auto"):
        super().__init__()
        self.url = url
        self.resolution = resolution
        self.browser = browser
        self.folder = folder
        self.scope = scope

    def log(self, msg: str):
        self.log_signal.emit(msg)

    def run(self):
        try:
            os.makedirs(self.folder, exist_ok=True)

            # 判断范围
            if self.scope == "auto":
                is_collection, _ = detect_url_type(self.url)
            else:
                is_collection = self.scope in ("playlist", "channel")

            # 构建 yt-dlp 参数
            if self.resolution == "best":
                fmt = "bestvideo*+bestaudio/best"
            else:
                h = self.resolution.replace("p", "")
                fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"

            if is_collection:
                # 播放列表/频道: 带序号命名
                out_tpl = str(Path(self.folder) / "%(playlist_title)s/%(playlist_index)03d - %(title).80B [%(id)s].%(ext)s")
                self.log(f"🎯 批量视频下载模式 ({self.resolution})\n")
            else:
                out_tpl = str(Path(self.folder) / "%(title).100B [%(id)s].%(ext)s")
                self.log(f"🎯 单个视频下载模式 ({self.resolution})\n")

            args = [
                "-f", fmt,
                "--merge-output-format", "mp4",
                "-o", out_tpl,
                "--newline",           # 每行一个进度更新
                "--progress",          # 显示进度
                "--no-warnings",
            ]

            if self.browser and self.browser.lower() != "none":
                args.extend(["--cookies-from-browser", self.browser.lower()])

            args.append(self.url)

            # 执行下载
            result = run_ytdlp(args, log_func=self.log, timeout=600, cwd=str(APP_DIR))

            if result["success"]:
                # 扫描下载的文件
                downloaded = list(Path(self.folder).rglob("*.mp4"))
                if downloaded:
                    files = "\n".join(f"  ✅ {f.relative_to(self.folder)}" for f in downloaded[-5:])
                    msg = f"视频下载完成!\n📁 目录: {self.folder}\n📄 文件:\n{files}"
                    if len(downloaded) > 5:
                        msg += f"\n  ... 共 {len(downloaded)} 个文件"
                    self.finished_signal.emit(True, msg)
                else:
                    self.finished_signal.emit(True, f"命令执行成功。\n📁 保存位置: {self.folder}")
            else:
                self.finished_signal.emit(False, result["stderr"] or "未知错误")

        except Exception as e:
            self.log(f"\n❌ 错误: {e}\n")
            self.finished_signal.emit(False, str(e))


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.worker = None

        self.setWindowTitle("全平台字幕助手 v3.0")
        self.setMinimumSize(1100, 800)
        self._setup_ui()
        self._apply_dark_theme()
        self._load_config_to_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---------- 标题 ----------
        title = QLabel("🎬 全平台字幕助手")
        title_font = QFont("SF Pro Display" if sys.platform == "darwin" else "Arial", 20, QFont.Bold)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ---------- URL 输入区 ----------
        url_group = QGroupBox("链接")
        url_layout = QHBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "粘贴视频/播放列表/频道链接 (支持 YouTube, Bilibili, TikTok, 抖音)"
        )
        url_layout.addWidget(self.url_input)

        self.paste_btn = QPushButton("📋 粘贴")
        self.paste_btn.setFixedWidth(90)
        self.paste_btn.clicked.connect(self._paste_url)
        url_layout.addWidget(self.paste_btn)
        layout.addWidget(url_group)

        # ---------- 模式选择区 ----------
        mode_group = QGroupBox("模式与范围")
        mode_layout = QVBoxLayout(mode_group)

        # 第一行: 功能模式 (字幕 / 视频)
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

        # 第二行: 范围选择 (单个 / 播放列表 / 频道 / 自动)
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

        # ---------- 参数区 (动态切换) ----------
        params_group = QGroupBox("参数")
        params_layout = QHBoxLayout(params_group)

        # 语言 (字幕模式)
        params_layout.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["zh-Hans", "zh-Hant", "en", "ja", "ko"])
        params_layout.addWidget(self.lang_combo)

        # 分辨率 (视频模式)
        params_layout.addWidget(QLabel("分辨率:"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(["best", "4K", "1080p", "720p", "480p", "360p"])
        self.res_combo.setCurrentText("1080p")
        params_layout.addWidget(self.res_combo)

        # 浏览器 Cookie
        params_layout.addWidget(QLabel("Cookie:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["none", "edge", "chrome", "firefox", "safari"])
        params_layout.addWidget(self.browser_combo)

        # 保存目录
        params_layout.addWidget(QLabel("保存到:"))
        self.folder_input = QLineEdit()
        self.folder_input.setMinimumWidth(200)
        params_layout.addWidget(self.folder_input, stretch=1)

        self.folder_btn = QPushButton("📁 选择")
        self.folder_btn.setFixedWidth(80)
        self.folder_btn.clicked.connect(self._choose_folder)
        params_layout.addWidget(self.folder_btn)

        layout.addWidget(params_group)

        # 模式切换时更新默认保存路径
        self.mode_subtitle.toggled.connect(self._update_folder_default)
        self.mode_video.toggled.connect(self._update_folder_default)

        # ---------- 操作按钮 ----------
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.download_btn = QPushButton("⬇ 开始下载")
        self.download_btn.setFixedSize(180, 44)
        btn_font = QFont("Arial", 13, QFont.Bold)
        self.download_btn.setFont(btn_font)
        self.download_btn.clicked.connect(self._start_download)
        btn_layout.addWidget(self.download_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setFixedSize(100, 44)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_download)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ---------- 进度条 ----------
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("就绪")
        self.progress_bar.setFixedHeight(24)
        layout.addWidget(self.progress_bar)

        # ---------- 日志区 ----------
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        mono_font = QFont("SF Mono" if sys.platform == "darwin" else "Consolas", 11)
        self.log_box.setFont(mono_font)
        log_layout.addWidget(self.log_box)
        layout.addWidget(log_group, stretch=1)

        # 状态栏
        self.statusBar().showMessage("就绪 | 支持平台: YouTube, Bilibili, TikTok, 抖音")

    def _apply_dark_theme(self):
        """应用暗色主题"""
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor("#1e1e2e"))
        dark_palette.setColor(QPalette.WindowText, QColor("#cdd6f4"))
        dark_palette.setColor(QPalette.Base, QColor("#1e1e2e"))
        dark_palette.setColor(QPalette.AlternateBase, QColor("#313244"))
        dark_palette.setColor(QPalette.Text, QColor("#cdd6f4"))
        dark_palette.setColor(QPalette.Button, QColor("#45475a"))
        dark_palette.setColor(QPalette.ButtonText, QColor("#cdd6f4"))
        dark_palette.setColor(QPalette.Highlight, QColor("#89b4fa"))
        dark_palette.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
        self.setPalette(dark_palette)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QGroupBox {
                font-weight: bold; font-size: 13px;
                border: 1px solid #45475a; border-radius: 8px;
                margin-top: 10px; padding-top: 8px;
                padding-left: 12px; padding-right: 12px; padding-bottom: 12px;
                color: #cdd6f4;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 12px; padding: 0 6px;
                color: #89b4fa;
            }
            QPushButton {
                background-color: #89b4fa; color: #1e1e2e;
                border: none; border-radius: 6px; padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:pressed { background-color: #74c7ec; }
            QPushButton:disabled { background-color: #313244; color: #6c7086; }
            QLineEdit, QComboBox {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 5px 8px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background-color: #313244; color: #cdd6f4;
                selection-background-color: #89b4fa;
            }
            QTextEdit {
                background-color: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 6px;
                padding: 8px;
            }
            QProgressBar {
                border: 1px solid #45475a; border-radius: 6px;
                text-align: center; background-color: #313244;
                color: #cdd6f4;
            }
            QProgressBar::chunk {
                background-color: #a6e3a1; border-radius: 6px;
            }
            QRadioButton { color: #cdd6f4; spacing: 6px; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QLabel { color: #cdd6f4; }
            QStatusBar { color: #6c7086; }
        """)

    def _load_config_to_ui(self):
        self.lang_combo.setCurrentText(self.config.get("lang", "zh-Hans"))
        self.browser_combo.setCurrentText(self.config.get("browser", "none"))
        self.res_combo.setCurrentText(self.config.get("resolution", "1080p"))
        self._update_folder_default()

    def _update_folder_default(self):
        if self.mode_subtitle.isChecked():
            default = self.config.get("folder_subtitle", str(APP_DIR / "subtitle"))
        else:
            default = self.config.get("folder_video", str(APP_DIR / "video"))
        self.folder_input.setText(default)

    # ==================== 槽函数 ====================

    @Slot()
    def _paste_url(self):
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)
            # 自动检测并提示
            is_collection, ctype = detect_url_type(text)
            if is_collection:
                self.statusBar().showMessage(f"检测到 {ctype} 链接", 5000)

    @Slot()
    def _choose_folder(self):
        current = self.folder_input.text() or str(APP_DIR)
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
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
            QMessageBox.warning(self, "提示", "请输入视频链接")
            return

        # 确定参数
        is_subtitle = self.mode_subtitle.isChecked()
        scope = "auto"
        for btn, val in [(self.scope_single, "single"),
                         (self.scope_playlist, "playlist"),
                         (self.scope_channel, "channel")]:
            if btn.isChecked():
                scope = val
                break

        folder = self.folder_input.text().strip() or str(APP_DIR / ("subtitle" if is_subtitle else "video"))
        os.makedirs(folder, exist_ok=True)

        # 保存配置
        self.config["lang"] = self.lang_combo.currentText()
        self.config["browser"] = self.browser_combo.currentText()
        self.config["resolution"] = self.res_combo.currentText()
        save_config(self.config)

        # 准备 UI
        self.log_box.clear()
        self.download_btn.setEnabled(False)
        self.download_btn.setText("下载中...")
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备中...")

        # 启动 Worker
        browser = self.browser_combo.currentText()

        if is_subtitle:
            self.worker = SubtitleWorker(
                url=url,
                lang=self.lang_combo.currentText(),
                browser=browser,
                folder=folder,
                scope=scope,
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
        self.worker.file_signal.connect(self._on_file_saved)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    @Slot()
    def _stop_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(2000)
            self._append_log("\n⏹ 用户取消下载\n")
            self._reset_ui()

    @Slot(str)
    def _append_log(self, text: str):
        self.log_box.append(text.rstrip("\n"))
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(int, int)
    def _update_progress(self, current: int, total: int):
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"进度: {current}/{total} ({pct}%)")
        else:
            self.progress_bar.setFormat("处理中...")

    @Slot(str, str)
    def _on_file_saved(self, ftype: str, path: str):
        self.statusBar().showMessage(f"已保存 {ftype}: {path}", 8000)

    @Slot(bool, str)
    def _on_finished(self, success: bool, msg: str):
        self._reset_ui()
        self.progress_bar.setValue(100 if success else 0)
        self.progress_bar.setFormat("完成" if success else "失败")

        if success:
            self.statusBar().showMessage("✅ " + msg.replace("\n", " ")[:80], 10000)
            QMessageBox.information(self, "完成", msg)
        else:
            self.statusBar().showMessage("❌ " + msg[:80], 10000)
            QMessageBox.critical(self, "错误", msg)

    def _reset_ui(self):
        self.download_btn.setEnabled(True)
        self.download_btn.setText("⬇ 开始下载")
        self.stop_btn.setEnabled(False)


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
