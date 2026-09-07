# 全平台字幕助手

一个跨平台的视频字幕下载 GUI 工具，支持从 **YouTube、Bilibili、TikTok、抖音** 一键提取字幕，并自动切回浏览器指定标签页。

---

## ✨ 功能特性

| 特性 | 说明 |
|------|------|
| 🌐 **多平台支持** | YouTube、Bilibili、TikTok、抖音 |
| 📝 **双格式输出** | 同时保存纯文本 `.txt` 和带时间轴的 `.srt` 字幕 |
| 🍪 **浏览器 Cookie** | 自动读取已登录浏览器的 Cookie，解锁会员/登录限定的字幕 |
| 🎯 **剪贴板监听** | 自动检测剪贴板中的视频链接，粘贴即下载 |
| 🔄 **浏览器回切** | 下载完成后自动激活浏览器并跳转到指定标签页 |
| 🤖 **AI 语音转录** | 无字幕视频自动调用 Whisper 进行语音转文字（TikTok / 抖音） |
| 🎨 **主题自定义** | 支持自定义背景色、按钮色、文字色等暗色/亮色主题 |
| 🌍 **多语言字幕** | 支持简中、繁中、英语、日语、韩语等多种语言选择 |

---

## 📁 项目结构

```
subtitle/
├── main.py              # GUI 入口（tkinter 界面 + 主逻辑）
├── core/                # 核心模块
│   ├── __init__.py      # 模块统一导出
│   ├── cookies.py       # 浏览器 Cookie 参数生成
│   ├── detector.py      # URL 平台自动识别
│   ├── filename.py      # 统一文件名格式：平台_ID_标题
│   └── subtitle.py      # 字幕下载调度器
└── platforms/           # 各平台适配器
    ├── __init__.py
    ├── bilibili.py      # B站：yt-dlp 优先 + 官方 API 备用
    ├── douyin.py        # 抖音：yt-dlp 字幕 → Whisper 转录
    ├── tiktok.py        # TikTok：yt-dlp 字幕 → Whisper 转录
    └── youtube.py       # YouTube：transcript-api 优先 + yt-dlp 备用
```

---

## 🚀 快速开始

### 环境要求

- **Python 3.8+**
- **macOS**（浏览器回切功能依赖 AppleScript，目前仅支持 macOS）
- 以下工具需预先安装：

```bash
# 1. 安装 yt-dlp（核心下载引擎）
pip install yt-dlp

# 2. 安装 youtube-transcript-api（YouTube 字幕 API）
pip install youtube-transcript-api

# 3. 安装 GUI 依赖
pip install clipboard

# 4. 【可选】安装 Whisper（无字幕视频自动转录）
pip install openai-whisper
```

> 同时需要系统安装 **FFmpeg**，Whisper 和 yt-dlp 均依赖它。

### 运行

```bash
git clone https://github.com/allan805/subtitle.git
cd subtitle
python main.py
```

---

## 📖 使用指南

### 界面说明

1. **视频链接**：粘贴视频 URL，或开启「自动粘贴」后直接从浏览器复制
2. **语言**：选择目标字幕语言（如 `zh-Hans` 简体中文）
3. **Cookies**：选择已登录的浏览器，用于获取需要登录才能查看的字幕
4. **存储位置**：字幕文件保存目录，默认 `./subtitle/`
5. **开始下载**：一键下载并保存字幕

### 设置面板（⚙️ 设置）

| 选项 | 说明 |
|------|------|
| 切回浏览器后自动粘贴并回车 | 下载完成后自动将字幕粘贴到浏览器输入框并提交 |
| 切回浏览器第几个标签页 | 指定激活浏览器的第 N 个标签页 |
| 主题颜色 | 自定义背景色、按钮背景色、按键文字色、文字颜色 |

### 支持的链接格式

| 平台 | 示例链接 |
|------|----------|
| YouTube | `https://www.youtube.com/watch?v=xxxxx` / `https://youtu.be/xxxxx` |
| Bilibili | `https://www.bilibili.com/video/BV1xx411c7mD` / `https://b23.tv/xxxxx` |
| TikTok | `https://www.tiktok.com/@user/video/xxxxx` |
| 抖音 | `https://www.douyin.com/video/xxxxx` / `https://v.douyin.com/xxxxx` |

---

## 🔧 各平台字幕获取策略

### YouTube
1. `youtube-transcript-api` 直接获取官方字幕（最快）
2. 失败则回退 `yt-dlp` 下载
3. 语言回退：用户指定语言 → 英语 → 列出所有可用语言

### Bilibili
1. `yt-dlp` 优先（支持 Cookie、WBI 签名、AI 字幕 `ai-zh`）
2. 失败则调用 B站官方 API 获取 CC 字幕
3. 支持 AI 生成字幕识别

### TikTok / 抖音
1. `yt-dlp` 尝试获取平台自带字幕
2. 无字幕时，自动下载音频并调用 **Whisper** 进行语音转文字

---

## ⚙️ 配置存储

用户配置保存在：`~/.subtitle_tool_config.json`

```json
{
  "bg_color": "#1a1a1a",
  "btn_bg_color": "#1a1a1a",
  "key_color": "#e0e0e0",
  "fg_color": "#b0b0b0",
  "auto_paste_enter": false,
  "browser_tab": 1,
  "folder": "./subtitle"
}
```

---

## 🛠️ 依赖清单

| 依赖 | 用途 |
|------|------|
| `yt-dlp` | 视频信息提取、字幕/音频下载 |
| `youtube-transcript-api` | YouTube 官方字幕 API |
| `clipboard` | 剪贴板读写 |
| `openai-whisper` | 【可选】语音转文字 |
| `requests` | HTTP 请求（Bilibili / YouTube 页面抓取） |
| `tkinter` | Python 内置 GUI 框架 |

---

## 🖥️ 浏览器支持

- Microsoft Edge
- Google Chrome
- Safari
- Firefox

> 通过 `--cookies-from-browser` 参数让 yt-dlp 自动读取浏览器 Cookie。

---

## 📝 输出文件

下载完成后会在指定目录生成两个文件：

```
subtitle/
├── bilibili_BV1xx411c7mD_视频标题.txt   # 纯文本字幕
└── bilibili_BV1xx411c7mD_视频标题.srt   # 带时间轴字幕
```

同时字幕内容会自动复制到系统剪贴板。

---

## ⚠️ 注意事项

1. **macOS 独占功能**：浏览器回切（AppleScript）目前仅在 macOS 上可用
2. **Cookie 登录**：部分平台（如 B站 AI 字幕、YouTube 会员视频）需要选择已登录的浏览器
3. **Whisper 模型**：首次使用会自动下载模型文件，建议网络畅通
4. **B站短链**：支持 `b23.tv` 短链自动跳转解析

---

## 📜 License

本项目为个人开源工具，仅供学习交流使用。
