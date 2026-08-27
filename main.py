"""全平台字幕助手 —— GUI 入口

主题逻辑:
- 背景色: 窗口背景、输入框背景（统一）
- 按钮背景色: 按钮本身的背景色（可调整）
- 按键色: 按钮文字颜色（可调整）
- 文字色: 标签/输出框文字颜色
- 按钮边框: flat 模式，无浮雕，无系统边框
- 存储位置: 默认 ./subtitle/（本文件夹内）
- 浏览器标签: 设置里可选切回第几个标签页
- 设置即时生效
- 配置文件: 本文件夹内 subtitle_tool_config.json
"""
import sys
import os

# 程序所在目录
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, colorchooser

import threading
import subprocess
import clipboard
import json

from core.subtitle import download_subtitle, save_subtitle


# 配置文件放在程序目录下
CONFIG_PATH = os.path.join(APP_DIR, "subtitle_tool_config.json")

# 默认配置
DEFAULT_CONFIG = {
    "bg_color": "#1a1a1a",
    "btn_bg_color": "#1a1a1a",
    "key_color": "#e0e0e0",
    "fg_color": "#b0b0b0",
    "auto_paste_enter": False,
    "browser_tab": 1,
    "folder": "./subtitle",
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            # 强制默认保存目录为当前程序目录下的 subtitle
            cfg["folder"] = DEFAULT_CONFIG["folder"]
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class SubtitleAssistant:
    def __init__(self, root):
        self.root = root
        self.config = load_config()

        self.root.title("全平台字幕助手")
        self.root.geometry("1100x800")
        self.root.configure(bg=self.config["bg_color"])

        self._setup_ttk_style()

        self.last_clipboard = ""

        # ========== 顶部 ==========
        top_frame = tk.Frame(root, bg=self.config["bg_color"])
        top_frame.pack(fill="x", padx=15, pady=(15, 5))

        # URL 行
        url_frame = tk.Frame(top_frame, bg=self.config["bg_color"])
        url_frame.pack(fill="x", side="top")

        tk.Label(url_frame, text="视频链接:", font=("Arial", 12),
                 bg=self.config["bg_color"], fg=self.config["fg_color"]).pack(side="left")

        self.url_entry = tk.Entry(
            url_frame, font=("Arial", 12),
            bg=self.config["bg_color"],
            fg=self.config["fg_color"],
            insertbackground=self.config["fg_color"],
            highlightbackground=self.config["bg_color"],
            highlightcolor=self.config["fg_color"],
            relief="flat",
            bd=1,
        )
        self.url_entry.pack(side="left", expand=True, fill="x", padx=10)

        self.paste_btn = self._make_button(
            url_frame, "📋 粘贴链接", self.paste_link, font=("Arial", 12, "bold")
        )
        self.paste_btn.pack(side="right")

        # 设置按钮行
        btn_frame = tk.Frame(top_frame, bg=self.config["bg_color"])
        btn_frame.pack(fill="x", side="top", pady=(8, 0))

        self.settings_btn = self._make_button(
            btn_frame, "⚙ 设置", self.open_settings, font=("Arial", 11)
        )
        self.settings_btn.pack(side="left")

        # ========== 设置区 ==========
        setting = tk.Frame(root, bg=self.config["bg_color"])
        setting.pack(fill="x", padx=15, pady=5)

        tk.Label(setting, text="语言:", font=("Arial", 12),
                 bg=self.config["bg_color"], fg=self.config["fg_color"]).pack(side="left")
        self.lang = ttk.Combobox(
            setting,
            values=["zh-Hans", "zh-Hant", "en", "ja", "ko"],
            width=12,
        )
        self.lang.current(0)
        self.lang.pack(side="left", padx=10)

        tk.Label(setting, text="Cookies:", font=("Arial", 12),
                 bg=self.config["bg_color"], fg=self.config["fg_color"]).pack(side="left", padx=(20, 5))
        self.browser = ttk.Combobox(
            setting,
            values=["edge", "chrome", "firefox", "safari", "none"],
            width=12,
        )
        self.browser.current(0)
        self.browser.pack(side="left")

        tk.Label(setting, text="存储位置:", font=("Arial", 12),
                 bg=self.config["bg_color"], fg=self.config["fg_color"]).pack(side="left", padx=(20, 5))
        self.folder = tk.Entry(
            setting, width=25,
            bg=self.config["bg_color"],
            fg=self.config["fg_color"],
            insertbackground=self.config["fg_color"],
            highlightbackground=self.config["bg_color"],
            highlightcolor=self.config["fg_color"],
            relief="flat",
            bd=1,
        )
        self.folder.insert(0, DEFAULT_CONFIG["folder"])
        self.folder.pack(side="left")

        self.choose_btn = self._make_button(setting, "选择", self.choose_folder)
        self.choose_btn.pack(side="left", padx=5)

        self.download_btn = self._make_button(
            setting, "⬇ 开始下载字幕", self.start, font=("Arial", 14, "bold"), width=22, height=2
        )
        self.download_btn.pack(side="right")

        # ========== 输出区 ==========
        self.output = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            font=("Consolas", 12),
            bg=self.config["bg_color"],
            fg=self.config["fg_color"],
            insertbackground=self.config["fg_color"],
            highlightbackground=self.config["bg_color"],
            highlightcolor=self.config["fg_color"],
            relief="flat",
            bd=1,
        )
        self.output.pack(expand=True, fill="both", padx=15, pady=15)

        self._style_scrollbar()

        self.check_clipboard()

    # ==========================
    # 统一创建按钮（flat 无浮雕）
    # ==========================
    def _make_button(self, parent, text, command, font=("Arial", 11), width=None, height=None):
        kwargs = {
            "text": text,
            "font": font,
            "bg": self.config["btn_bg_color"],
            "fg": self.config["key_color"],
            "activebackground": self.config["fg_color"],
            "activeforeground": self.config["bg_color"],
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "command": command,
        }
        if width:
            kwargs["width"] = width
        if height:
            kwargs["height"] = height
        return tk.Button(parent, **kwargs)

    # ==========================
    # ttk 样式
    # ==========================
    def _setup_ttk_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        bg = self.config["bg_color"]
        fg = self.config["fg_color"]

        style.configure("TCombobox",
                        fieldbackground=bg,
                        background=bg,
                        foreground=fg,
                        arrowcolor=fg)
        style.map("TCombobox",
                  fieldbackground=[("readonly", bg)],
                  selectbackground=[("readonly", bg)],
                  selectforeground=[("readonly", fg)])

        self.root.option_add("*TCombobox*Listbox.background", bg)
        self.root.option_add("*TCombobox*Listbox.foreground", fg)
        self.root.option_add("*TCombobox*Listbox.selectBackground", bg)
        self.root.option_add("*TCombobox*Listbox.selectForeground", fg)

    def _style_scrollbar(self):
        style = ttk.Style()
        bg = self.config["bg_color"]
        fg = self.config["fg_color"]

        style.configure("Vertical.TScrollbar",
                        background=bg,
                        troughcolor=bg,
                        bordercolor=bg,
                        arrowcolor=fg)
        style.configure("Horizontal.TScrollbar",
                        background=bg,
                        troughcolor=bg,
                        bordercolor=bg,
                        arrowcolor=fg)

    # ==========================
    # 即时应用主题
    # ==========================
    def _apply_theme_now(self):
        bg = self.config["bg_color"]
        btn_bg = self.config["btn_bg_color"]
        key = self.config["key_color"]
        fg = self.config["fg_color"]

        self.root.configure(bg=bg)
        self._setup_ttk_style()
        self._style_scrollbar()

        def update_widget(w):
            try:
                w.configure(bg=bg)
            except Exception:
                pass
            try:
                if isinstance(w, tk.Button):
                    w.configure(bg=btn_bg, fg=key, activebackground=fg, activeforeground=bg,
                                relief="flat", bd=0, highlightthickness=0)
                elif isinstance(w, tk.Entry):
                    w.configure(bg=bg, fg=fg, insertbackground=fg,
                                highlightbackground=bg, highlightcolor=fg, relief="flat")
                elif isinstance(w, tk.Label):
                    w.configure(bg=bg, fg=fg)
                elif isinstance(w, tk.Frame):
                    w.configure(bg=bg)
                elif isinstance(w, tk.Checkbutton):
                    w.configure(bg=bg, fg=fg, selectcolor=bg,
                                activebackground=bg, activeforeground=fg)
                elif isinstance(w, tk.LabelFrame):
                    w.configure(bg=bg, fg=fg)
                elif isinstance(w, scrolledtext.ScrolledText):
                    w.configure(bg=bg, fg=fg, insertbackground=fg,
                                highlightbackground=bg, highlightcolor=fg, relief="flat")
            except Exception:
                pass

            for child in w.winfo_children():
                update_widget(child)

        update_widget(self.root)

    # ==========================
    # 设置面板
    # ==========================
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("420x480")
        win.configure(bg=self.config["bg_color"])
        win.transient(self.root)
        win.grab_set()

        # 自动粘贴+回车
        auto_var = tk.BooleanVar(value=self.config.get("auto_paste_enter", False))
        cb = tk.Checkbutton(
            win,
            text="切回浏览器后自动粘贴并回车",
            variable=auto_var,
            font=("Arial", 12),
            bg=self.config["bg_color"],
            fg=self.config["fg_color"],
            selectcolor=self.config["bg_color"],
            activebackground=self.config["bg_color"],
            activeforeground=self.config["fg_color"],
        )
        cb.pack(anchor="w", padx=20, pady=(20, 10))

        # 浏览器标签页选择
        tab_frame = tk.Frame(win, bg=self.config["bg_color"])
        tab_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(tab_frame, text="切回浏览器第几个标签页:", font=("Arial", 12),
                 bg=self.config["bg_color"], fg=self.config["fg_color"]).pack(side="left")
        self.tab_var = tk.StringVar(value=str(self.config.get("browser_tab", 1)))
        tab_spin = tk.Spinbox(tab_frame, from_=1, to=20, width=5, textvariable=self.tab_var,
                              font=("Arial", 12),
                              bg=self.config["bg_color"], fg=self.config["fg_color"],
                              insertbackground=self.config["fg_color"],
                              buttonbackground=self.config["btn_bg_color"])
        tab_spin.pack(side="left", padx=10)

        # 颜色设置
        color_frame = tk.LabelFrame(
            win,
            text="主题颜色",
            font=("Arial", 12, "bold"),
            bg=self.config["bg_color"],
            fg=self.config["fg_color"],
        )
        color_frame.pack(fill="x", padx=20, pady=10)

        colors = [
            ("背景色", "bg_color"),
            ("按钮背景", "btn_bg_color"),
            ("按键文字", "key_color"),
            ("文字颜色", "fg_color"),
        ]

        self._color_vars = {}
        for label, key in colors:
            row = tk.Frame(color_frame, bg=self.config["bg_color"])
            row.pack(fill="x", pady=5)

            tk.Label(row, text=label + ":", font=("Arial", 11),
                     bg=self.config["bg_color"], fg=self.config["fg_color"]).pack(side="left", padx=5)

            var = tk.StringVar(value=self.config.get(key, DEFAULT_CONFIG[key]))
            self._color_vars[key] = var

            entry = tk.Entry(row, textvariable=var, width=10, font=("Arial", 11),
                             bg=self.config["bg_color"], fg=self.config["fg_color"],
                             insertbackground=self.config["fg_color"],
                             relief="flat", bd=1)
            entry.pack(side="left", padx=5)

            preview = tk.Label(row, text="  ", font=("Arial", 11),
                               bg=var.get(), width=3)
            preview.pack(side="left", padx=5)

            def make_pick(k, v, p):
                return lambda: self._pick_color(k, v, p)

            pick_btn = self._make_button(row, "选择", make_pick(key, var, preview))
            pick_btn.pack(side="left", padx=5)

        # 保存按钮
        save_btn = self._make_button(
            win, "💾 保存并应用", lambda: self._apply_settings(win, auto_var), font=("Arial", 12, "bold")
        )
        save_btn.pack(pady=20)

        # 应用当前主题到设置窗口
        self._update_setting_window(win)

    def _update_setting_window(self, win):
        def update(w):
            try:
                w.configure(bg=self.config["bg_color"])
            except Exception:
                pass
            try:
                if isinstance(w, tk.Button):
                    w.configure(bg=self.config["btn_bg_color"], fg=self.config["key_color"],
                                activebackground=self.config["fg_color"],
                                activeforeground=self.config["bg_color"],
                                relief="flat", bd=0, highlightthickness=0)
                elif isinstance(w, tk.Entry):
                    w.configure(bg=self.config["bg_color"], fg=self.config["fg_color"],
                                insertbackground=self.config["fg_color"])
                elif isinstance(w, (tk.Label, tk.Checkbutton, tk.LabelFrame)):
                    w.configure(bg=self.config["bg_color"], fg=self.config["fg_color"])
                    if isinstance(w, tk.Checkbutton):
                        w.configure(selectcolor=self.config["bg_color"],
                                    activebackground=self.config["bg_color"],
                                    activeforeground=self.config["fg_color"])
                elif isinstance(w, tk.Frame):
                    w.configure(bg=self.config["bg_color"])
                elif isinstance(w, tk.Spinbox):
                    w.configure(bg=self.config["bg_color"], fg=self.config["fg_color"],
                                insertbackground=self.config["fg_color"],
                                buttonbackground=self.config["btn_bg_color"])
            except Exception:
                pass
            for child in w.winfo_children():
                update(child)
        update(win)

    def _pick_color(self, key, var, preview_label):
        color = colorchooser.askcolor(initialcolor=var.get(), title="选择颜色")[1]
        if color:
            var.set(color)
            preview_label.configure(bg=color)

    def _apply_settings(self, win, auto_var):
        self.config["auto_paste_enter"] = auto_var.get()
        self.config["browser_tab"] = int(self.tab_var.get() or 1)
        for key, var in self._color_vars.items():
            self.config[key] = var.get()

        save_config(self.config)
        self._apply_theme_now()
        messagebox.showinfo("设置", "设置已保存并生效")
        win.destroy()

    # ==========================
    # 工具方法
    # ==========================
    def log(self, text):
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def paste_link(self):
        text = clipboard.paste()
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, text)

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            # 如果选择的是程序目录下的子目录，显示相对路径
            if path.startswith(APP_DIR):
                rel = os.path.relpath(path, APP_DIR)
                display = "./" + rel.replace(os.sep, "/")
            else:
                display = path
            self.folder.delete(0, tk.END)
            self.folder.insert(0, display)
            self.config["folder"] = display
            save_config(self.config)

    # ==========================
    # 自动读取剪贴板
    # ==========================
    def check_clipboard(self):
        try:
            text = clipboard.paste().strip()
            if text != self.last_clipboard and self.is_video_url(text):
                self.last_clipboard = text
                self.url_entry.delete(0, tk.END)
                self.url_entry.insert(0, text)
                self.log("\n🎯 检测到视频链接，自动开始下载...\n")
                self.start()
        except Exception:
            pass

        self.root.after(2000, self.check_clipboard)

    def is_video_url(self, text):
        sites = [
            "youtube.com", "youtu.be",
            "bilibili.com", "b23.tv",
            "douyin.com", "v.douyin.com",
            "tiktok.com",
        ]
        return any(s in text.lower() for s in sites)

    # ==========================
    # 下载线程
    # ==========================
    def start(self):
        threading.Thread(target=self.download_flow, daemon=True).start()

    def download_flow(self):
        url = self.url_entry.get().strip()
        if not url:
            return

        self.output.delete("1.0", tk.END)
        lang = self.lang.get()
        browser = self.browser.get()
        folder = self.folder.get()

        if folder.startswith("./") or folder.startswith(".\\"):
            folder = os.path.join(APP_DIR, folder[2:])

        try:
            result = download_subtitle(
                url, lang, browser,
                log_func=self.log,
            )

            self.output.insert(tk.END, "\n" + "=" * 50 + "\n")
            self.output.insert(tk.END, result["text"])
            self.output.insert(tk.END, "\n" + "=" * 50 + "\n")

            clipboard.copy(result["text"])
            self.log("\n✅ 字幕已复制到剪贴板\n")

            txt_path, srt_path = save_subtitle(result, folder, log_func=self.log)
            self.back_to_browser()

        except Exception as e:
            self.log(f"\n❌ 错误: {str(e)}\n")

    # ==========================
    # 切回浏览器
    # ==========================
    def back_to_browser(self):
        browser = self.browser.get()
        tab_index = self.config.get("browser_tab", 1)
        auto_paste = self.config.get("auto_paste_enter", False)

        scripts = {
            "edge": self._chrome_edge_script("Microsoft Edge", tab_index, auto_paste),
            "chrome": self._chrome_edge_script("Google Chrome", tab_index, auto_paste),
            "safari": self._safari_script(tab_index, auto_paste),
            "firefox": self._firefox_script(tab_index, auto_paste),
        }

        script = scripts.get(browser)
        if not script:
            self.log(f"\n⚠️ 不支持切换该浏览器: {browser}\n")
            return

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0 and result.stderr:
                self.log(f"\n⚠️ 浏览器切换脚本错误: {result.stderr.strip()}\n")
                return

            app_name = {
                "edge": "Microsoft Edge",
                "chrome": "Google Chrome",
                "safari": "Safari",
                "firefox": "Firefox",
            }.get(browser, browser)

            if auto_paste:
                self.log(f"🔄 已切回 {app_name} 并自动粘贴回车\n")
            else:
                self.log(f"🔄 已切回 {app_name} 第 {tab_index} 个标签页\n")

        except Exception as e:
            self.log(f"\n浏览器切换失败: {str(e)}\n")

    def _chrome_edge_script(self, app_name, tab_index, auto_paste):
        base = f"""
tell application "{app_name}"
    activate
    delay 0.3
    tell window 1
        set active tab index to {tab_index}
    end tell
end tell
"""
        if auto_paste:
            base += """
tell application "System Events"
    delay 1
    keystroke "v" using command down
    delay 0.5
    key code 36
    delay 0.3
end tell
"""
        return base

    def _safari_script(self, tab_index, auto_paste):
        base = f"""
tell application "Safari"
    activate
    delay 0.3
    tell window 1
        set current tab to tab {tab_index}
    end tell
end tell
"""
        if auto_paste:
            base += """
tell application "System Events"
    delay 0.5
    keystroke "v" using command down
    delay 0.5
    key code 36
    delay 0.3
end tell
"""
        return base

    def _firefox_script(self, tab_index, auto_paste):
        key_codes = [18, 19, 20, 21, 23, 22, 26, 28, 25, 29]
        if tab_index <= 10:
            key_code = key_codes[tab_index - 1]
        else:
            key_code = 18

        base = f"""
tell application "Firefox"
    activate
    delay 0.5
end tell

tell application "System Events"
    tell process "Firefox"
        set frontmost to true
        delay 0.3
        key code {key_code} using command down
    end tell
end tell
"""
        if auto_paste:
            base += """
tell application "System Events"
    delay 0.5
    keystroke "v" using command down
    delay 0.5
    key code 36
    delay 0.3
end tell
"""
        return base


if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleAssistant(root)
    root.mainloop()
