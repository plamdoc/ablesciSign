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


TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"

READ_TASK_API = (
    "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list"
    "?taskType=2&pageNo=1&pageSize=15&reset=true"
)

TARGET_INDEX = 1          # 第二个任务，下标从 0 开始，所以第二个是 1
READ_WAIT_MIN = 18        # 阅读页最短停留秒数
READ_WAIT_MAX = 30        # 阅读页最长停留秒数


def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    """
    将浏览器复制出来的 Cookie 字符串转换为 Playwright 可用格式
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


def safe_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


def fetch_api_json(page, api_url: str):
    """
    通过浏览器页面内 fetch 请求接口。
    这样会自动携带当前浏览器里的 Cookie。
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
        print(f"❌ 接口请求失败：{str(e)}")
        return None


def check_cookie_valid_by_api(page) -> bool:
    """
    用接口判断 Cookie 是否有效。
    不再通过页面里是否有“登录、验证码”等文字判断，避免误判。
    """
    data = fetch_api_json(page, READ_TASK_API)

    if not data:
        print("❌ Cookie 检测失败：接口无返回。")
        return False

    error_code = data.get("errorCode")
    message = data.get("message", "")

    print(f"📡 Cookie 检测接口返回：errorCode={error_code}, message={message}")

    if str(error_code) == "0":
        print("✅ 接口判断 Cookie 有效。")
        return True

    print("❌ 接口判断 Cookie 可能无效。")
    return False


def get_read_tasks_by_api(page) -> list:
    """
    通过接口获取阅读任务列表
    """
    data = fetch_api_json(page, READ_TASK_API)

    if not data:
        return []

    error_code = data.get("errorCode")
    message = data.get("message", "")

    print(f"📡 任务接口返回：errorCode={error_code}, message={message}")

    if str(error_code) != "0":
        print("❌ 任务接口返回异常。")
        return []

    results = data.get("results") or data.get("result") or {}
    items = results.get("items", [])

    if not isinstance(items, list):
        return []

    return items


def is_task_completed_by_api(task: dict) -> bool:
    """
    根据接口字段判断任务是否完成。

    结合你截图里的数据：
    userStatus = 2 一般表示已完成
    userStatus = 1 一般表示未完成
    taskDingDang = 1 一般表示已获得奖励
    taskDingDang = 0 一般表示未获得奖励
    """
    user_status = safe_int(task.get("userStatus"), -1)
    task_dingdang = safe_int(task.get("taskDingDang"), 0)
    dingdang_limit = safe_int(task.get("dingDangLimit"), 1)

    if user_status == 2:
        return True

    if dingdang_limit > 0 and task_dingdang >= dingdang_limit:
        return True

    return False


def print_task_list(items: list):
    """
    打印阅读任务列表，方便你看状态
    """
    if not items:
        print("📋 没有获取到阅读任务。")
        return

    print("📋 当前阅读任务列表：")

    for i, task in enumerate(items, start=1):
        title = task.get("title", "")
        user_status = task.get("userStatus")
        task_dingdang = task.get("taskDingDang")
        button_title = task.get("buttonTitle", "")
        completed = is_task_completed_by_api(task)

        status_text = "已完成" if completed else "未完成"

        print(
            f"  {i}. {status_text} | "
            f"userStatus={user_status} | "
            f"taskDingDang={task_dingdang} | "
            f"button={button_title} | "
            f"{title}"
        )


def get_second_task_info(page):
    """
    获取第二个阅读任务
    """
    items = get_read_tasks_by_api(page)
    print_task_list(items)

    if len(items) <= TARGET_INDEX:
        print("❌ 接口返回的阅读任务不足 2 个，无法处理第二个任务。")
        return None

    task = items[TARGET_INDEX]

    title = task.get("title", "")
    content_url = task.get("contentUrl", "")
    user_status = task.get("userStatus")
    task_dingdang = task.get("taskDingDang")
    completed = is_task_completed_by_api(task)

    print("-" * 40)
    print("🎯 第二个阅读任务信息：")
    print(f"标题：{title}")
    print(f"userStatus：{user_status}")
    print(f"taskDingDang：{task_dingdang}")
    print(f"阅读链接：{content_url}")
    print(f"当前状态：{'已完成' if completed else '未完成'}")
    print("-" * 40)

    return task


def is_task_completed_by_button(btn) -> bool:
    """
    页面兜底判断：
    根据“去阅读”按钮向上查找任务卡片，判断是否有已完成文字或已完成水印。
    """
    try:
        return btn.evaluate("""
        (node) => {
            let parent = node.parentElement;

            for (let i = 0; i < 12; i++) {
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


def get_second_visible_read_button(page):
    """
    获取页面上第二个可见的“去阅读”按钮
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

    if len(visible_buttons) <= TARGET_INDEX:
        return None

    return visible_buttons[TARGET_INDEX]


def safe_click(locator) -> bool:
    """
    优先普通点击，失败后强制点击
    """
    try:
        locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass

    try:
        locator.click(timeout=10000)
        return True
    except Exception as e:
        print(f"⚠️ 普通点击失败，尝试强制点击：{str(e)}")

    try:
        locator.click(force=True, timeout=10000)
        return True
    except Exception as e:
        print(f"❌ 强制点击也失败：{str(e)}")
        return False


def simulate_reading(read_page):
    """
    模拟阅读停留和滚动
    """
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"⏳ 阅读页面停留 {wait_time} 秒，并模拟滚动...")

    start_time = time.time()

    while time.time() - start_time < wait_time:
        try:
            read_page.mouse.wheel(0, random.randint(400, 900))
        except Exception:
            pass

        time.sleep(random.uniform(2.0, 4.0))

    print("✅ 阅读停留完成。")


def click_second_read_button(context, page) -> bool:
    """
    点击页面上的第二个“去阅读”
    """
    second_btn = get_second_visible_read_button(page)

    if second_btn is None:
        print("❌ 页面上没有找到第二个可见的“去阅读”按钮。")
        return False

    if is_task_completed_by_button(second_btn):
        print("✅ 页面判断：第二个任务已经显示已完成，不需要点击。")
        return True

    print("👉 准备点击第二个“去阅读”按钮。")

    old_url = page.url

    try:
        try:
            with context.expect_page(timeout=6000) as new_page_info:
                click_ok = safe_click(second_btn)

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

        except PlaywrightTimeoutError:
            print("📌 点击后没有检测到新标签页，可能是在当前页面跳转或原页面内完成。")

            time.sleep(3)

            if page.url != old_url:
                print(f"📖 当前页面已跳转到阅读页：{page.url}")

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass

                simulate_reading(page)

                print("🔙 返回任务页。")
                try:
                    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    try:
                        page.go_back(wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
            else:
                print("📌 当前页面没有明显跳转，等待任务状态同步。")
                time.sleep(random.randint(12, 18))

        return True

    except Exception as e:
        print(f"❌ 点击第二个“去阅读”失败：{str(e)}")
        return False


def check_second_task_completed_after_read(page, old_task: dict = None) -> bool:
    """
    阅读后再次通过接口检查第二个任务是否完成。
    优先用任务 id 匹配，避免刷新后顺序变化。
    """
    print("🔄 正在刷新任务页并重新检查任务状态...")

    try:
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(6)
    except Exception as e:
        print(f"⚠️ 刷新任务页失败：{str(e)}")

    items = get_read_tasks_by_api(page)
    print_task_list(items)

    if not items:
        print("❌ 重新获取任务列表失败。")
        return False

    old_id = ""
    if old_task:
        old_id = str(old_task.get("id", ""))

    target_task = None

    if old_id:
        for task in items:
            if str(task.get("id", "")) == old_id:
                target_task = task
                break

    if target_task is None and len(items) > TARGET_INDEX:
        target_task = items[TARGET_INDEX]

    if target_task is None:
        print("❌ 没有找到第二个任务。")
        return False

    completed = is_task_completed_by_api(target_task)

    print("-" * 40)
    print("📌 阅读后检测结果：")
    print(f"标题：{target_task.get('title', '')}")
    print(f"userStatus：{target_task.get('userStatus')}")
    print(f"taskDingDang：{target_task.get('taskDingDang')}")
    print(f"状态：{'已完成' if completed else '未完成'}")
    print("-" * 40)

    return completed


def run_one_account(browser, current_cookie: str, index: int):
    """
    执行单个账号
    """
    print("=" * 40)
    print(f"🚀 开始执行账号 {index}")

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="zh-CN"
    )

    context.add_cookies(parse_cookies(current_cookie))
    page = context.new_page()

    try:
        print(f"🌐 正在打开任务页面：{TASK_URL}")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)

        print("⏳ 等待页面渲染 6 秒...")
        time.sleep(6)

        if not check_cookie_valid_by_api(page):
            print("❌ 当前账号 Cookie 可能无效，请重新抓取 DXY_COOKIE。")
            return

        second_task = get_second_task_info(page)

        if second_task is None:
            print("❌ 未找到第二个阅读任务，本账号跳过。")
            return

        if is_task_completed_by_api(second_task):
            print("✅ 接口判断：第二个阅读任务已经完成，不需要点击。")
            return

        click_ok = click_second_read_button(context, page)

        if not click_ok:
            print("❌ 第二个“去阅读”点击失败。")
            return

        completed = check_second_task_completed_after_read(page, second_task)

        if completed:
            print(f"🎉 账号 {index}：第二个阅读任务已完成。")
        else:
            print(f"⚠️ 账号 {index}：暂未检测到完成，可能需要延长停留时间或稍后再运行。")

    except Exception as e:
        print(f"❌ 账号 {index} 执行异常：{str(e)}")

    finally:
        context.close()


def main():
    cookie_env = os.environ.get("DXY_COOKIE", "")

    if not cookie_env.strip():
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE！\033[0m")
        print("请在环境变量中添加 DXY_COOKIE。")
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

        for index, current_cookie in enumerate(account_cookies, start=1):
            run_one_account(browser, current_cookie, index)

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
