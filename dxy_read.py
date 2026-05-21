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

MAX_CLICKS = 5
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


def get_api_task_status(page):
    """
    【核心新增】从底层接口获取精确的已完成名单
    返回: (已完成数量, 总数量, 已完成标题列表)
    """
    data = fetch_task_list(page)
    if not data or "results" not in data:
        return 0, 0, []

    items = data.get("results", {}).get("items", [])
    if not isinstance(items, list):
        return 0, 0, []

    total = len(items)
    completed_titles = []
    
    for item in items:
        # userStatus == 2 表示真正在后端已完成的
        if item.get("userStatus") == 2:
            completed_titles.append(item.get("title", "").strip())
            
    return len(completed_titles), total, completed_titles


def wait_task_page(page):
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


def mark_next_unfinished_read_button(page, skip_titles=None, api_completed_titles=None):
    """
    结合前端 UI 和后端 API 的绝对真理进行过滤
    """
    if skip_titles is None: skip_titles = []
    if api_completed_titles is None: api_completed_titles = []

    result = page.evaluate(
        """
        (payload) => {
            const TARGET_ATTR = "data-dxy-click-target";
            const skipTitles = payload.skipTitles || [];
            const apiCompleted = payload.apiCompleted || [];

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
                const closest = el.closest("div.operate-btn, button, a, [role='button'], [class*='btn'], [class*='button']");
                if (closest && isVisible(closest)) return closest;
                return el;
            }

            function findCard(el) {
                let p = el;
                for (let i = 0; i < 20; i++) {
                    if (!p) break;
                    const text = p.innerText || "";
                    const rect = p.getBoundingClientRect();
                    const looksLikeTask = text.includes("阅读文章") && text.includes("去阅读");
                    const sizeOk = rect.width > 200 && rect.height > 60 && rect.height < window.innerHeight * 0.95;
                    if (looksLikeTask && sizeOk) return p;
                    p = p.parentElement;
                }
                return el.parentElement || el;
            }

            function isCompletedByUI(card) {
                if (!card) return false;
                const text = card.innerText || "";
                if (text.includes("已完成")) return true;
                const watermark = card.querySelector("img[alt='已完成水印'], img.watermark, .watermark");
                if (watermark) return true;
                return false;
            }

            function getTitle(card) {
                if (!card) return "未知文章";
                const lines = (card.innerText || "").split("\\n").map(x => x.trim()).filter(x => x.length > 0);
                for (const line of lines) {
                    if (line.includes("阅读文章")) return line;
                }
                for (const line of lines) {
                    if (line !== "去阅读" && !line.includes("完成阅读") && !line.includes("已完成") && line.length >= 6) {
                        return line;
                    }
                }
                return lines[0] || "未知文章";
            }
            
            // 【核心防漏逻辑】检查标题是否在 API 的已完成名单中
            function isCompletedByAPI(title) {
                const cleanTitle = normText(title);
                for(const apiTitle of apiCompleted) {
                    const cleanApi = normText(apiTitle);
                    // 互相包含即可，应对 UI 和 API 标题被截断的情况
                    if (cleanApi && cleanTitle && (cleanApi.includes(cleanTitle) || cleanTitle.includes(cleanApi))) {
                        return true;
                    }
                }
                return false;
            }

            let rawCandidates = Array.from(document.querySelectorAll("div.operate-btn"))
                .filter(el => normText(el.innerText || el.textContent).includes("去阅读"));
                
            if (rawCandidates.length === 0) {
                rawCandidates = Array.from(document.querySelectorAll("body *"))
                    .filter(el => normText(el.innerText || el.textContent) === "去阅读");
            }

            const buttons = [];
            for (const el of rawCandidates) {
                if (!isVisible(el)) continue;
                const clickEl = findClickable(el);
                if (!isVisible(clickEl)) continue;
                const card = findCard(clickEl);
                const title = getTitle(card);
                
                // 综合判定：UI 认为完成了，或者 API 认为完成了，统统算完成！
                const completed = isCompletedByUI(card) || isCompletedByAPI(title);
                const rect = clickEl.getBoundingClientRect();

                buttons.push({
                    el: clickEl, card, completed, title,
                    x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                    centerX: rect.x + rect.width / 2, centerY: rect.y + rect.height / 2
                });
            }

            // 去重
            const unique = [];
            for (const item of buttons) {
                const duplicated = unique.some(old => Math.abs(old.centerX - item.centerX) < 3 && Math.abs(old.centerY - item.centerY) < 3);
                if (!duplicated) unique.push(item);
            }

            // 过滤出真正未完成的
            const unfinished = unique.filter(item => {
                if (item.completed) return false;
                const title = normText(item.title);
                for (const oldTitle of skipTitles) {
                    if (oldTitle && title && title.includes(oldTitle)) return false;
                }
                return true;
            });

            if (unfinished.length === 0) {
                return {
                    ok: false, total: unique.length, unfinishedCount: 0,
                    buttons: unique.map((item, i) => ({
                        no: i + 1, title: item.title, completed: item.completed
                    }))
                };
            }

            const target = unfinished[0];
            target.el.setAttribute(TARGET_ATTR, "1");
            target.el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
            const rect2 = target.el.getBoundingClientRect();

            return {
                ok: true, total: unique.length, unfinishedCount: unfinished.length,
                target: {
                    title: target.title, centerX: rect2.x + rect2.width / 2, centerY: rect2.y + rect2.height / 2
                },
                buttons: unique.map((item, i) => ({
                    no: i + 1, title: item.title, completed: item.completed
                }))
            };
        }
        """,
        {
            "skipTitles": list(skip_titles),
            "apiCompleted": api_completed_titles # 注入 API 绝对真理名单
        }
    )

    print("📋 页面扫描结果 (结合 API 校对)：")
    for item in result.get("buttons", []):
        status = "已完成(跳过)" if item.get("completed") else "未完成"
        print(f"  {item.get('no')}. {status} | {item.get('title')}")

    if not result.get("ok"):
        print("✅ 页面上所有可见的“去阅读”任务均在底层记录中完成了。")
        return None

    target = result.get("target", {})
    print("-" * 40)
    print("🎯 已精准锁定真正未完成任务：")
    print(f"标题：{target.get('title')}")
    print("-" * 40)
    return target


def real_click_marked_button(page) -> bool:
    try:
        locator = page.locator('[data-dxy-click-target="1"]').first
        locator.scroll_into_view_if_needed(timeout=5000)
        time.sleep(random.uniform(0.6, 1.2))
        box = locator.bounding_box()
        if not box:
            locator.click(force=True, timeout=10000)
            return True
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
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
    try:
        locator = page.locator('[data-dxy-click-target="1"]').first
        locator.click(force=True, timeout=10000)
        return True
    except Exception as e:
        return False


def simulate_reading(read_page):
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"📖 正在深度阅读 {wait_time} 秒...")
    try:
        read_page.bring_to_front()
    except: pass

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
        except: pass
        time.sleep(random.uniform(3.0, 5.0))

    try: read_page.evaluate("window.scrollBy(0, -500)")
    except: pass
    time.sleep(2)
    print("✅ 阅读停留完成。")


def click_and_handle_reading(context, page) -> bool:
    old_url = page.url
    try:
        try:
            with context.expect_page(timeout=8000) as popup_info:
                if not real_click_marked_button(page): return False
            new_page = popup_info.value
            print("➡️ 已捕获新文章标签页。")
            try: new_page.wait_for_load_state("domcontentloaded", timeout=30000)
            except: pass
            simulate_reading(new_page)
            try: new_page.close()
            except: pass
            return True

        except PlaywrightTimeoutError:
            print("⚠️ 未捕获新标签页，检查是否当前页跳转。")
            time.sleep(5)
            if page.url != old_url:
                print(f"➡️ 当前页已跳转到文章页")
                simulate_reading(page)
                return True

            print("⚠️ 尝试兜底点击...")
            try:
                with context.expect_page(timeout=8000) as popup_info2:
                    if not force_click_marked_button(page): return False
                new_page2 = popup_info2.value
                simulate_reading(new_page2)
                try: new_page2.close()
                except: pass
                return True
            except:
                if page.url != old_url:
                    simulate_reading(page)
                    return True
                return False
    except Exception as e:
        print(f"❌ 点击处理异常：{str(e)}")
        return False


def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 50)
    print(f"🚀 开始执行账号 [{account_index}]")
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai"
    )
    context.add_cookies(parse_cookies(cookie_str))
    page = context.new_page()

    clicked_count = 0
    skip_titles = set()

    try:
        wait_task_page(page)

        # 获取底层真理名单
        initial_completed, total, api_completed_titles = get_api_task_status(page)
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
            except: pass

            load_all_task_cards(page)

            # 把 API 告诉我们的已完成名单传进去，强制拉黑
            target = mark_next_unfinished_read_button(page, skip_titles, api_completed_titles)

            if not target:
                break

            title = str(target.get("title", "")).strip()
            if title: skip_titles.add(title)

            if click_and_handle_reading(context, page):
                clicked_count += 1
                print(f"✅ 已完成第 {clicked_count} 次阅读流程。")
            
            print("🔄 返回任务页刷新状态...")
            try:
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(8)
            except: pass

            # 每跑完一轮，更新一次底层的已完成真理名单
            after_completed, after_total, api_completed_titles = get_api_task_status(page)
            print(f"📊 当前接口状态：已完成 {after_completed}/{after_total}")

            if after_total > 0 and after_completed >= after_total:
                print("🎉 接口显示今日任务已全部完成。")
                break

        print("\n" + "-" * 40)
        print("🔎 最终复查任务完成情况...")
        time.sleep(6)
        final_completed, final_total, _ = get_api_task_status(page)
        newly_completed = final_completed - initial_completed
        print(f"💰 成果核对：本轮新增完成 {newly_completed} 个任务，今日累计完成 {final_completed}/{final_total} 个。")

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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        for index, cookie_str in enumerate(account_cookies, start=1):
            run_one_account(browser, cookie_str, index)
            if index < len(account_cookies):
                time.sleep(random.randint(5, 10))
        browser.close()
    print("=" * 50)
    print("🎉 所有账号任务流程执行完毕。")

if __name__ == "__main__":
    time.sleep(random.randint(1, 10))
    main()
