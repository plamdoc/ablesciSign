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

# 【核心配置】单次运行最大点击数量
MAX_CLICKS = 5

# 阅读页停留时间 (模拟真实阅读的秒数)
READ_WAIT_MIN = 20
READ_WAIT_MAX = 35


def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
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
    keywords = ["我知道了", "知道了", "取消", "关闭", "暂不", "以后再说"]
    for word in keywords:
        try:
            btn = page.get_by_text(word, exact=True)
            if btn.count() > 0 and btn.first.is_visible(timeout=1000):
                btn.first.click(timeout=2000)
                time.sleep(1)
        except Exception:
            pass


def wait_task_page_ready(page):
    print(f"🌐 正在打开任务页面：{TASK_URL}")
    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
    print("⏳ 等待页面渲染 8 秒...")
    time.sleep(8)
    close_possible_popups(page)


def is_login_page(page) -> bool:
    url = page.url.lower()
    return "login" in url or "passport" in url


def is_completed_by_card(btn) -> bool:
    """
    【核心识别逻辑】判断按钮所在卡片是否已完成
    完美适配用户提供的 HTML 结构 <img class="watermark" alt="已完成水印">
    """
    try:
        return btn.evaluate("""
        (node) => {
            let parent = node.parentElement;
            for (let i = 0; i < 15; i++) {
                if (!parent) break;
                
                // 1. 检查文字
                const text = parent.innerText || "";
                if (text.includes("已完成")) return true;

                // 2. 检查丁香园专属的已完成印章水印
                const watermark = parent.querySelector('img[alt="已完成水印"], img.watermark');
                if (watermark) return true;

                parent = parent.parentElement;
            }
            return false;
        }
        """)
    except Exception:
        return False


def get_card_text(btn) -> str:
    try:
        text = btn.evaluate("""
        (node) => {
            let parent = node.parentElement;
            for (let i = 0; i < 10; i++) {
                if (!parent) break;
                const text = parent.innerText || "";
                if (text.includes("完成阅读即可得") || text.includes("去阅读")) {
                    return text.split('\\n')[0]; // 只提取最上面的标题
                }
                parent = parent.parentElement;
            }
            return "未命名任务";
        }
        """)
        return text
    except Exception:
        return "获取标题失败"


def real_mouse_click(page, locator) -> bool:
    """真实物理鼠标点击，穿透前端防护"""
    try:
        locator.scroll_into_view_if_needed(timeout=5000)
        time.sleep(random.uniform(0.5, 1.2))

        box = locator.bounding_box()
        if not box:
            locator.click(force=True, timeout=10000)
            return True

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        page.mouse.move(x, y, steps=random.randint(8, 15))
        time.sleep(random.uniform(0.2, 0.6))
        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.2))
        page.mouse.up()
        return True
    except Exception:
        try:
            locator.click(force=True, timeout=10000)
            return True
        except Exception:
            return False


def simulate_reading(read_page):
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"📖 正在认真阅读 {wait_time} 秒...")
    start = time.time()
    while time.time() - start < wait_time:
        try:
            # 模拟真人鼠标滚轮向下看文章
            read_page.mouse.wheel(0, random.randint(300, 900))
        except Exception:
            pass
        time.sleep(random.uniform(2.0, 4.0))


def process_read_tasks(context, page) -> int:
    """
    【全新主控逻辑】自动扫描、跳过已完成、最多点击 5 个
    """
    clicked_count = 0
    skip_count = 0

    print("=" * 40)
    print("🚀 开始扫描页面任务列表...")

    # 为了防止 DOM 在操作中失效，我们使用循环动态获取
    for attempt in range(15): # 最多探测页面上排名前 15 的按钮
        if clicked_count >= MAX_CLICKS:
            print(f"🛑 已达单次上限 ({MAX_CLICKS}个)，剩下的留给下个小时点。")
            break

        # 每次都重新抓取按钮列表
        buttons = page.get_by_text("去阅读", exact=True)
        if attempt >= buttons.count():
            break # 页面上的按钮已经全部检查完了

        btn = buttons.nth(attempt)

        try:
            if not btn.is_visible(timeout=2000):
                continue
        except Exception:
            continue

        if is_completed_by_card(btn):
            skip_count += 1
            continue

        # 如果没有跳过，说明这是一个未完成的任务！
        card_text = get_card_text(btn)
        print("-" * 30)
        print(f"🎯 发现未完成任务：【{card_text}】")
        
        old_url = page.url
        try:
            # 情况1：正常打开新标签页阅读
            try:
                with context.expect_page(timeout=6000) as new_page_info:
                    click_ok = real_mouse_click(page, btn)
                    if not click_ok: continue

                new_page = new_page_info.value
                print("   ➡️ 成功打开新文章页")
                simulate_reading(new_page)
                try:
                    new_page.close()
                    print("   ✅ 文章阅读完毕，已关闭")
                except Exception:
                    pass
                clicked_count += 1

            except PlaywrightTimeoutError:
                # 情况2：没弹新窗口，检查是不是直接在原网页跳转了
                time.sleep(4)
                if page.url != old_url:
                    print("   ➡️ 网页直接跳转到了文章页")
                    simulate_reading(page)
                    print("   🔙 读完返回任务列表...")
                    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(6)
                    clicked_count += 1
                    # 原网页刷新后，按钮的排序变了，直接打断最安全，剩下的等下一波定时任务
                    print("   ⚠️ 页面发生刷新重载，为保证稳定，提前结束本轮扫荡。")
                    break
                else:
                    # 情况3：没跳转也没弹窗，可能是在页面内弹出了视频或其他组件
                    print("   📌 触发了页面内操作，原地挂机等待...")
                    time.sleep(random.randint(12, 18))
                    clicked_count += 1

        except Exception as e:
            print(f"   ❌ 点击此任务时发生异常：{str(e)}")

        # 两个任务之间休息几秒，防风控
        if clicked_count < MAX_CLICKS:
            delay = random.randint(4, 8)
            print(f"   💤 假装喝口水，休息 {delay} 秒...")
            time.sleep(delay)

    print("-" * 40)
    print(f"📊 本轮总结：成功完成 {clicked_count} 个阅读，智能跳过了 {skip_count} 个已完成。")
    return clicked_count


def api_check_after_click(page):
    """点击后用后端接口核对一下今天的丁当状态"""
    print("🔎 正在通过底层接口核对收益...")
    try:
        data = page.evaluate(
            """
            async (apiUrl) => {
                const res = await fetch(apiUrl, { method: "GET", credentials: "include" });
                return await res.json();
            }
            """, READ_TASK_API
        )
        if data and "results" in data:
            items = data["results"].get("items", [])
            for item in items:
                title = item.get("title", "")
                if "阅读文章" in title:
                    print(f"💰 今日阅读进度: {item.get('taskDingDang')}/{item.get('dingDangLimit')}")
                    break
    except Exception:
        print("⚠️ 接口核对跳过。")


def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 40)
    print(f"🚀 开始登录账号 [{account_index}]")
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900}
    )
    context.add_cookies(parse_cookies(cookie_str))
    page = context.new_page()

    try:
        wait_task_page_ready(page)
        if is_login_page(page):
            print("❌ Cookie 似乎已过期，页面跳转到了登录。")
            return

        # 🚀 启动自动扫荡模式
        process_read_tasks(context, page)

        api_check_after_click(page)

    except Exception as e:
        print(f"❌ 账号 {account_index} 执行异常：{str(e)}")
    finally:
        context.close()


def main():
    cookie_env = os.environ.get("DXY_COOKIE", "")
    if not cookie_env.strip():
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE！\033[0m")
        return

    account_cookies = [c.strip() for c in cookie_env.splitlines() if c.strip()]
    print("=" * 40)
    print(f"🎉 识别到 {len(account_cookies)} 个账号，即将发车...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        for index, cookie_str in enumerate(account_cookies, start=1):
            run_one_account(browser, cookie_str, index)
            if index < len(account_cookies):
                time.sleep(random.randint(5, 10))

        browser.close()
    print("🎉 所有账号今天这波阅读任务已搞定！")


if __name__ == "__main__":
    # GitHub Action 定时任务可能会同时唤醒，随机抖动 1~15 秒避免高并发特征
    time.sleep(random.randint(1, 15))
    main()
