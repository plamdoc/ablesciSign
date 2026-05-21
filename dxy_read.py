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

API_URL = (
    "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list"
    "?taskType=2&pageNo=1&pageSize=15&reset=true"
)

# 单次最多点击几个未完成阅读任务
MAX_CLICKS = 5

# 阅读页停留时间，单位秒
READ_WAIT_MIN = 45
READ_WAIT_MAX = 60


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


def fetch_task_list(page):
    """
    API 只用于辅助核对任务状态，不用于直接完成任务
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
            API_URL
        )
        return data
    except Exception as e:
        print(f"❌ 接口请求失败：{str(e)}")
        return None


def get_completed_count_by_api(page):
    data = fetch_task_list(page)

    if not data or "results" not in data:
        print("⚠️ 接口数据获取失败，可能 Cookie 过期或接口异常。")
        return 0, 0

    items = data.get("results", {}).get("items", [])

    if not isinstance(items, list):
        return 0, 0

    total = len(items)
    completed = len([item for item in items if item.get("userStatus") == 2])

    return completed, total


def wait_task_page(page):
    """
    打开任务页并等待渲染
    """
    print(f"🌐 正在打开任务页：{TASK_URL}")
    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)

    print("⏳ 等待页面渲染 8 秒...")
    time.sleep(8)

    try:
        page.wait_for_selector("text=去阅读", timeout=20000)
        print("✅ 页面已检测到“去阅读”。")
    except Exception:
        print("⚠️ 暂未检测到“去阅读”，继续尝试扫描 DOM。")


def load_all_task_cards(page):
    """
    向下滚动，尽量加载完整任务列表
    """
    print("⬇️ 正在滚动页面，加载更多任务卡片...")

    try:
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

        for _ in range(4):
            page.mouse.wheel(0, 1000)
            time.sleep(1.2)

        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1.5)
    except Exception:
        pass


def mark_next_unfinished_read_button(page, skip_titles=None):
    """
    查找页面上第一个未完成的“去阅读”按钮，并打上临时标记。
    不依赖 .task_item，改为向上查找包含：
    阅读文章 + 完成阅读 + 去阅读
    的最小任务卡片。
    """
    if skip_titles is None:
        skip_titles = []

    result = page.evaluate(
        """
        (payload) => {
            const TARGET_ATTR = "data-dxy-click-target";
            const skipTitles = payload.skipTitles || [];

            document.querySelectorAll("[" + TARGET_ATTR + "]").forEach(el => {
                el.removeAttribute(TARGET_ATTR);
            });

            function normText(text) {
                return String(text || "").replace(/\\s+/g, " ").trim();
            }

            function isVisible(el) {
                if (!el) return false;

                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();

                if (style.display === "none") return false;
                if (style.visibility === "hidden") return false;
                if (Number(style.opacity) === 0) return false;
                if (rect.width <= 1 || rect.height <= 1) return false;

                return true;
            }

            function findClickable(el) {
                const closest = el.closest(
                    "div.operate-btn, button, a, [role='button'], [class*='btn'], [class*='button'], [class*='Button']"
                );

                if (closest && isVisible(closest)) {
                    return closest;
                }

                return el;
            }

            function findCard(el) {
                let p = el;

                for (let i = 0; i < 20; i++) {
                    if (!p) break;

                    const text = p.innerText || "";
                    const rect = p.getBoundingClientRect();

                    const looksLikeTask =
                        text.includes("阅读文章") &&
                        text.includes("完成阅读") &&
                        text.includes("去阅读");

                    const sizeOk =
                        rect.width > 200 &&
                        rect.height > 60 &&
                        rect.height < window.innerHeight * 0.95;

                    if (looksLikeTask && sizeOk) {
                        return p;
                    }

                    p = p.parentElement;
                }

                return el.parentElement || el;
            }

            function isCompleted(card) {
                if (!card) return false;

                const text = card.innerText || "";

                if (text.includes("已完成")) {
                    return true;
                }

                const watermark = card.querySelector(
                    "img[alt='已完成水印'], img.watermark, .watermark"
                );

                if (watermark) {
                    return true;
                }

                return false;
            }

            function getTitle(card) {
                if (!card) return "未知文章";

                const text = card.innerText || "";
                const lines = text
                    .split("\\n")
                    .map(x => x.trim())
                    .filter(x => x.length > 0);

                for (const line of lines) {
                    if (line.includes("阅读文章")) {
                        return line;
                    }
                }

                for (const line of lines) {
                    if (
                        line !== "去阅读" &&
                        !line.includes("完成阅读") &&
                        !line.includes("已完成") &&
                        line.length >= 6
                    ) {
                        return line;
                    }
                }

                return lines[0] || "未知文章";
            }

            let rawCandidates = [];

            const operateBtns = Array.from(
                document.querySelectorAll("div.operate-btn")
            ).filter(el => normText(el.innerText || el.textContent).includes("去阅读"));

            if (operateBtns.length > 0) {
                rawCandidates = operateBtns;
            } else {
                rawCandidates = Array.from(document.querySelectorAll("body *"))
                    .filter(el => normText(el.innerText || el.textContent) === "去阅读");
            }

            const buttons = [];

            for (const el of rawCandidates) {
                if (!isVisible(el)) continue;

                const clickEl = findClickable(el);

                if (!isVisible(clickEl)) continue;

                const card = findCard(clickEl);
                const completed = isCompleted(card);
                const title = getTitle(card);
                const rect = clickEl.getBoundingClientRect();

                buttons.push({
                    el: clickEl,
                    card,
                    completed,
                    title,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    centerX: rect.x + rect.width / 2,
                    centerY: rect.y + rect.height / 2
                });
            }

            buttons.sort((a, b) => {
                if (Math.abs(a.y - b.y) > 5) return a.y - b.y;
                return a.x - b.x;
            });

            const unique = [];

            for (const item of buttons) {
                const duplicated = unique.some(old => {
                    return (
                        Math.abs(old.centerX - item.centerX) < 3 &&
                        Math.abs(old.centerY - item.centerY) < 3
                    );
                });

                if (!duplicated) {
                    unique.push(item);
                }
            }

            const unfinished = unique.filter(item => {
                if (item.completed) return false;

                const title = normText(item.title);

                for (const oldTitle of skipTitles) {
                    if (oldTitle && title && title.includes(oldTitle)) {
                        return false;
                    }
                }

                return true;
            });

            if (unfinished.length === 0) {
                return {
                    ok: false,
                    total: unique.length,
                    unfinishedCount: 0,
                    buttons: unique.map((item, index) => ({
                        no: index + 1,
                        title: item.title,
                        completed: item.completed,
                        x: item.x,
                        y: item.y,
                        width: item.width,
                        height: item.height
                    }))
                };
            }

            const target = unfinished[0];

            target.el.setAttribute(TARGET_ATTR, "1");
            target.el.scrollIntoView({
                block: "center",
                inline: "center",
                behavior: "instant"
            });

            const rect2 = target.el.getBoundingClientRect();

            return {
                ok: true,
                total: unique.length,
                unfinishedCount: unfinished.length,
                target: {
                    title: target.title,
                    x: rect2.x,
                    y: rect2.y,
                    width: rect2.width,
                    height: rect2.height,
                    centerX: rect2.x + rect2.width / 2,
                    centerY: rect2.y + rect2.height / 2
                },
                buttons: unique.map((item, index) => ({
                    no: index + 1,
                    title: item.title,
                    completed: item.completed,
                    x: item.x,
                    y: item.y,
                    width: item.width,
                    height: item.height
                }))
            };
        }
        """,
        {"skipTitles": list(skip_titles)}
    )

    print("📋 页面扫描结果：")
    for item in result.get("buttons", []):
        status = "已完成" if item.get("completed") else "未完成"
        print(f"  {item.get('no')}. {status} | {item.get('title')}")

    if not result.get("ok"):
        print("✅ 页面上没有发现新的未完成“去阅读”任务。")
        return None

    target = result.get("target", {})
    print("-" * 40)
    print("🎯 已锁定未完成任务：")
    print(f"标题：{target.get('title')}")
    print(f"按钮中心坐标：x={target.get('centerX')}, y={target.get('centerY')}")
    print("-" * 40)

    return target


def real_click_marked_button(page) -> bool:
    """
    对标记后的按钮进行真实鼠标点击
    """
    try:
        locator = page.locator('[data-dxy-click-target="1"]').first
        locator.scroll_into_view_if_needed(timeout=5000)
        time.sleep(random.uniform(0.6, 1.2))

        box = locator.bounding_box()

        if not box:
            print("⚠️ 无法获取按钮坐标，尝试 locator.click。")
            locator.click(force=True, timeout=10000)
            return True

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2

        print(f"🖱️ 正在真实点击按钮中心：x={x:.1f}, y={y:.1f}")

        page.mouse.move(x, y, steps=random.randint(8, 15))
        time.sleep(random.uniform(0.2, 0.5))
        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.18))
        page.mouse.up()

        return True

    except Exception as e:
        print(f"❌ 鼠标点击失败：{str(e)}")
        return False


def force_click_marked_button(page) -> bool:
    """
    兜底点击
    """
    try:
        locator = page.locator('[data-dxy-click-target="1"]').first
        locator.click(force=True, timeout=10000)
        print("✅ 兜底 locator.click 成功。")
        return True
    except Exception as e:
        print(f"❌ 兜底点击失败：{str(e)}")
        return False


def simulate_reading(read_page):
    """
    阅读页面停留并滚动
    """
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"📖 正在阅读 {wait_time} 秒...")

    try:
        read_page.bring_to_front()
    except Exception:
        pass

    start_time = time.time()
    scroll_count = 0

    while time.time() - start_time < wait_time:
        try:
            scroll_count += 1

            if scroll_count == 3:
                read_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                print("   ⬇️ 已滚动到页面底部。")
            else:
                read_page.evaluate(f"window.scrollBy(0, {random.randint(300, 800)})")
        except Exception:
            pass

        time.sleep(random.uniform(3.0, 5.0))

    try:
        read_page.evaluate("window.scrollBy(0, -500)")
    except Exception:
        pass

    time.sleep(2)
    print("✅ 阅读停留完成。")


def click_and_handle_reading(context, page) -> bool:
    """
    点击当前标记的“去阅读”，处理新标签页或当前页跳转
    """
    old_url = page.url

    try:
        # 情况1：点击后打开新标签页
        try:
            with context.expect_page(timeout=8000) as popup_info:
                click_ok = real_click_marked_button(page)

                if not click_ok:
                    return False

            new_page = popup_info.value
            print("➡️ 已捕获新文章标签页。")

            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass

            simulate_reading(new_page)

            try:
                new_page.close()
                print("✅ 文章标签页已关闭。")
            except Exception:
                pass

            return True

        except PlaywrightTimeoutError:
            print("⚠️ 鼠标点击后未捕获新标签页，检查是否当前页跳转。")
            time.sleep(5)

            if page.url != old_url:
                print(f"➡️ 当前页已跳转到文章页：{page.url}")

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass

                simulate_reading(page)
                return True

            print("⚠️ 页面未跳转，尝试兜底点击。")

            try:
                with context.expect_page(timeout=8000) as popup_info2:
                    click_ok = force_click_marked_button(page)

                    if not click_ok:
                        return False

                new_page2 = popup_info2.value
                print("➡️ 兜底点击后捕获新文章标签页。")

                try:
                    new_page2.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass

                simulate_reading(new_page2)

                try:
                    new_page2.close()
                    print("✅ 文章标签页已关闭。")
                except Exception:
                    pass

                return True

            except PlaywrightTimeoutError:
                time.sleep(5)

                if page.url != old_url:
                    print(f"➡️ 当前页已跳转到文章页：{page.url}")

                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except Exception:
                        pass

                    simulate_reading(page)
                    return True

                print("❌ 点击后既没有新标签页，也没有当前页跳转。")
                return False

    except Exception as e:
        print(f"❌ 点击处理异常：{str(e)}")
        return False


def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 50)
    print(f"🚀 开始执行账号 [{account_index}]")

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        ignore_https_errors=True
    )

    context.add_cookies(parse_cookies(cookie_str))
    page = context.new_page()

    clicked_count = 0
    skip_titles = set()

    try:
        wait_task_page(page)

        initial_completed, total = get_completed_count_by_api(page)
        print(f"📊 接口摸底：今日总任务 {total} 个 | 已完成 {initial_completed} 个")

        if total > 0 and initial_completed >= total:
            print("🎉 今日阅读任务已全部完成。")
            return

        while clicked_count < MAX_CLICKS:
            print("\n" + "-" * 40)
            print(f"🔄 第 {clicked_count + 1} 轮扫描未完成任务...")

            try:
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(6)
            except Exception:
                pass

            load_all_task_cards(page)

            target = mark_next_unfinished_read_button(page, skip_titles)

            if not target:
                break

            title = str(target.get("title", "")).strip()
            if title:
                skip_titles.add(title)

            click_ok = click_and_handle_reading(context, page)

            if click_ok:
                clicked_count += 1
                print(f"✅ 已完成第 {clicked_count} 次阅读流程。")
            else:
                print("❌ 本次点击流程失败，继续尝试下一个任务。")

            print("🔄 返回任务页刷新状态...")
            try:
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(8)
            except Exception:
                pass

            after_completed, after_total = get_completed_count_by_api(page)
            print(f"📊 当前接口状态：已完成 {after_completed}/{after_total}")

            if after_total > 0 and after_completed >= after_total:
                print("🎉 接口显示今日任务已全部完成。")
                break

        print("\n" + "-" * 40)
        print("🔎 最终复查任务完成情况...")
        time.sleep(6)

        final_completed, final_total = get_completed_count_by_api(page)
        newly_completed = final_completed - initial_completed

        print(
            f"💰 成果核对：本轮新增完成 {newly_completed} 个任务，"
            f"今日累计完成 {final_completed}/{final_total} 个。"
        )

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

    print("=" * 50)
    print(f"🎉 识别到 {len(account_cookies)} 个账号配置。")

    headless_env = os.environ.get("HEADLESS", "true").lower()
    headless = headless_env != "false"

    print(f"🧭 浏览器模式：{'无头模式' if headless else '有界面模式'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
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

    print("=" * 50)
    print("🎉 所有账号任务流程执行完毕。")


if __name__ == "__main__":
    time.sleep(random.randint(1, 10))

    try:
        main()
    finally:
        if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
            input("按回车键退出...")
