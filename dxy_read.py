#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("【错误】缺少 playwright 库。")
    print("请先执行：pip install playwright")
    print("然后执行：playwright install chromium")
    exit(1)


# =========================
# 基础配置
# =========================

TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"

READ_TASK_API = (
    "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list"
    "?taskType=2&pageNo=1&pageSize=15&reset=true"
)

# 点击第几个“去阅读”
# 1 = 第一个，2 = 第二个
TARGET_BUTTON_NO = 2

# 阅读页停留时间
READ_WAIT_MIN = 25
READ_WAIT_MAX = 40


def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    """
    把浏览器复制出来的一整串 Cookie 转换成 Playwright 可用格式
    """
    cookies = []

    for item in cookie_str.split(";"):
        item = item.strip()

        if not item or "=" not in item:
            continue

        name, value = item.split("=", 1)

        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": domain,
            "path": "/",
            "secure": True,
            "sameSite": "Lax"
        })

    return cookies


def close_possible_popups(page):
    """
    尝试关闭可能出现的弹窗，不影响主流程
    """
    keywords = [
        "我知道了",
        "知道了",
        "取消",
        "关闭",
        "暂不",
        "以后再说"
    ]

    for word in keywords:
        try:
            btn = page.get_by_text(word, exact=True)
            if btn.count() > 0 and btn.first.is_visible(timeout=1000):
                btn.first.click(timeout=2000)
                time.sleep(1)
        except Exception:
            pass


def wait_task_page_ready(page):
    """
    等待任务页面加载完成
    """
    print(f"🌐 正在打开任务页面：{TASK_URL}")

    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)

    print("⏳ 等待页面渲染 8 秒...")
    time.sleep(8)

    close_possible_popups(page)

    try:
        page.wait_for_selector("text=去阅读", timeout=20000)
        print("✅ 页面已检测到“去阅读”按钮。")
    except Exception:
        print("⚠️ 页面暂未检测到“去阅读”按钮，继续尝试解析页面。")


def is_login_page(page) -> bool:
    """
    只通过 URL 判断是否跳到登录页，避免误判
    """
    url = page.url.lower()

    if "login" in url:
        return True

    if "passport" in url:
        return True

    return False


def is_completed_by_card(btn) -> bool:
    """
    判断当前“去阅读”按钮所在任务卡片是否已完成
    依据：
    1. 是否有“已完成”文字
    2. 是否有已完成水印
    """
    try:
        return btn.evaluate("""
        (node) => {
            let parent = node.parentElement;

            for (let i = 0; i < 15; i++) {
                if (!parent) break;

                const text = parent.innerText || "";

                if (text.includes("已完成")) {
                    return true;
                }

                const watermark1 = parent.querySelector('img.watermark[alt="已完成水印"]');
                const watermark2 = parent.querySelector('img[alt="已完成水印"]');
                const watermark3 = parent.querySelector('.watermark');

                if (watermark1 || watermark2 || watermark3) {
                    return true;
                }

                parent = parent.parentElement;
            }

            return false;
        }
        """)
    except Exception:
        return False


def get_card_text(btn) -> str:
    """
    获取按钮所在任务卡片的文字，方便打印日志
    """
    try:
        text = btn.evaluate("""
        (node) => {
            let parent = node.parentElement;

            for (let i = 0; i < 10; i++) {
                if (!parent) break;

                const text = parent.innerText || "";

                if (
                    text.includes("阅读文章") ||
                    text.includes("完成阅读") ||
                    text.includes("去阅读")
                ) {
                    return text;
                }

                parent = parent.parentElement;
            }

            return node.innerText || "";
        }
        """)
        return " ".join(text.split())
    except Exception:
        return ""


def get_visible_read_buttons(page):
    """
    获取页面上所有可见的“去阅读”按钮
    """
    buttons = page.get_by_text("去阅读", exact=True)
    total = buttons.count()

    print(f"🔍 页面共找到 {total} 个“去阅读”文本。")

    visible_buttons = []

    for i in range(total):
        btn = buttons.nth(i)

        try:
            if btn.is_visible(timeout=2000):
                visible_buttons.append(btn)
        except Exception:
            continue

    print(f"🔍 可见的“去阅读”按钮数量：{len(visible_buttons)}")

    for i, btn in enumerate(visible_buttons, start=1):
        completed = is_completed_by_card(btn)
        card_text = get_card_text(btn)

        print("-" * 30)
        print(f"第 {i} 个“去阅读”")
        print(f"状态：{'已完成' if completed else '未完成'}")
        print(f"任务内容：{card_text[:120]}")

    print("-" * 30)

    return visible_buttons


def real_mouse_click(page, locator) -> bool:
    """
    用鼠标坐标真实点击按钮中心位置
    """
    try:
        locator.scroll_into_view_if_needed(timeout=5000)
        time.sleep(random.uniform(0.5, 1.2))

        box = locator.bounding_box()

        if not box:
            print("⚠️ 获取按钮坐标失败，改用 Playwright click。")
            locator.click(force=True, timeout=10000)
            return True

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2

        print(f"🖱️ 鼠标移动到按钮中心坐标：x={x:.1f}, y={y:.1f}")

        page.mouse.move(x, y, steps=random.randint(8, 15))
        time.sleep(random.uniform(0.2, 0.6))
        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.2))
        page.mouse.up()

        print("✅ 已完成真实鼠标点击。")
        return True

    except Exception as e:
        print(f"⚠️ 真实鼠标点击失败，尝试 force click：{str(e)}")

        try:
            locator.click(force=True, timeout=10000)
            print("✅ force click 成功。")
            return True
        except Exception as e2:
            print(f"❌ force click 也失败：{str(e2)}")
            return False


def simulate_reading(read_page):
    """
    阅读页停留并滚动
    """
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"📖 阅读页停留 {wait_time} 秒...")

    start = time.time()

    while time.time() - start < wait_time:
        try:
            read_page.mouse.wheel(0, random.randint(300, 900))
        except Exception:
            pass

        time.sleep(random.uniform(2.0, 4.0))

    print("✅ 阅读停留结束。")


def click_target_read_button(context, page) -> bool:
    """
    打开任务页后，真实点击第 TARGET_BUTTON_NO 个“去阅读”
    """
    visible_buttons = get_visible_read_buttons(page)

    target_index = TARGET_BUTTON_NO - 1

    if len(visible_buttons) <= target_index:
        print(f"❌ 页面上不足 {TARGET_BUTTON_NO} 个可见“去阅读”，无法点击。")
        return False

    target_btn = visible_buttons[target_index]

    card_text = get_card_text(target_btn)
    print("=" * 40)
    print(f"🎯 准备点击第 {TARGET_BUTTON_NO} 个“去阅读”")
    print(f"任务内容：{card_text}")
    print("=" * 40)

    if is_completed_by_card(target_btn):
        print(f"✅ 第 {TARGET_BUTTON_NO} 个任务页面显示已完成，不再点击。")
        return True

    old_url = page.url

    try:
        # 情况1：点击后打开新标签页
        try:
            with context.expect_page(timeout=6000) as new_page_info:
                click_ok = real_mouse_click(page, target_btn)

                if not click_ok:
                    return False

            new_page = new_page_info.value
            print("📖 点击后打开了新的阅读页面。")

            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass

            simulate_reading(new_page)

            try:
                new_page.close()
                print("✅ 新阅读页面已关闭。")
            except Exception:
                pass

            return True

        except PlaywrightTimeoutError:
            # 注意：这里不是没点击，而是点击后没有新标签页
            print("📌 点击后没有检测到新标签页，检查是否当前页跳转。")

            time.sleep(5)

            # 情况2：当前页面跳转到了阅读页
            if page.url != old_url:
                print(f"📖 当前页已跳转到阅读页：{page.url}")

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass

                simulate_reading(page)

                print("🔙 返回任务页。")
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(6)

                return True

            # 情况3：没有新标签页，也没有跳转，但可能页面内已经触发
            print("📌 当前页面没有跳转，等待任务状态同步。")
            time.sleep(random.randint(12, 18))
            return True

    except Exception as e:
        print(f"❌ 点击第 {TARGET_BUTTON_NO} 个“去阅读”失败：{str(e)}")
        return False


def fetch_api_json(page, api_url):
    """
    辅助函数：点击后用接口看一下是否获得丁当
    """
    try:
        data = page.evaluate(
            """
            async (apiUrl) => {
                const res = await fetch(apiUrl, {
                    method: "GET",
                    credentials: "include",
                    headers: {
                        "accept": "application/json, text/plain, */*"
                    }
                });
                return await res.json();
            }
            """,
            api_url
        )
        return data
    except Exception as e:
        print(f"⚠️ 接口辅助检测失败：{str(e)}")
        return None


def api_check_after_click(page):
    """
    点击后辅助检查丁当状态
    """
    print("🔎 点击后辅助检查任务接口状态...")

    try:
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
    except Exception:
        pass

    data = fetch_api_json(page, READ_TASK_API)

    if not data:
        print("⚠️ 未获取到接口数据。")
        return

    error_code = data.get("errorCode")
    message = data.get("message", "")

    print(f"📡 接口返回：errorCode={error_code}, message={message}")

    results = data.get("results") or data.get("result") or {}
    items = results.get("items", [])

    if not isinstance(items, list) or not items:
        print("⚠️ 接口没有返回任务列表。")
        return

    print("📋 接口辅助状态：")

    for i, item in enumerate(items, start=1):
        title = item.get("title", "")
        user_status = item.get("userStatus")
        task_dingdang = item.get("taskDingDang")
        dingdang_limit = item.get("dingDangLimit")

        print(
            f"{i}. userStatus={user_status} | "
            f"taskDingDang={task_dingdang}/{dingdang_limit} | "
            f"{title[:80]}"
        )


def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 40)
    print(f"🚀 开始执行账号 {account_index}")

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
        ignore_https_errors=True
    )

    context.add_cookies(parse_cookies(cookie_str))
    page = context.new_page()

    try:
        wait_task_page_ready(page)

        if is_login_page(page):
            print("❌ 当前页面跳转到了登录页，Cookie 可能失效。")
            return

        click_ok = click_target_read_button(context, page)

        if click_ok:
            print(f"✅ 账号 {account_index}：第 {TARGET_BUTTON_NO} 个“去阅读”点击流程完成。")
        else:
            print(f"❌ 账号 {account_index}：第 {TARGET_BUTTON_NO} 个“去阅读”点击失败。")

        api_check_after_click(page)

    except Exception as e:
        print(f"❌ 账号 {account_index} 执行异常：{str(e)}")

    finally:
        context.close()


def main():
    cookie_env = os.environ.get("DXY_COOKIE", "")

    if not cookie_env.strip():
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE！\033[0m")
        print("请在 GitHub Secrets 或本地环境变量中添加 DXY_COOKIE。")
        return

    account_cookies = [c.strip() for c in cookie_env.splitlines() if c.strip()]

    print("=" * 40)
    print(f"🎉 成功解析到 {len(account_cookies)} 个账号配置，准备开始执行。")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        for index, cookie_str in enumerate(account_cookies, start=1):
            run_one_account(browser, cookie_str, index)

            if index < len(account_cookies):
                delay = random.randint(5, 10)
                print(f"💤 切换账号，等待 {delay} 秒...")
                time.sleep(delay)

        browser.close()

    print("=" * 40)
    print("🎉 所有账号执行完成。")


if __name__ == "__main__":
    time.sleep(random.randint(1, 10))

    try:
        main()
    finally:
        if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
            input("按回车键退出...")
