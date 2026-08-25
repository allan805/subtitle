"""浏览器 Cookies 处理模块"""


def cookie_args(browser: str) -> list:
    if not browser or browser.lower() == "none":
        return []
    return ["--cookies-from-browser", browser.lower()]
