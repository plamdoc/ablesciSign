#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    from playwright_stealth import stealth_sync
except ImportError:
    print("【错误】缺少依赖库。本地运行请先执行：")
    print("pip install playwright playwright-stealth")
    exit(1)

# =========================
# 基础配置
# =========================
TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"
API_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"

MAX_CLICKS = 5
READ_WAIT_MIN = 45
READ_WAIT_MAX = 60

def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        name, value = item.split("=", 1)
        cookies.append({
            "name": name.strip(), "value": value.strip(),
            "domain": domain, "path": "/", "secure": True, "sameSite": "Lax"
        })
    return cookies

def fetch_api_data(page):
    try:
        return page.evaluate(f"""
            async () => {{
                const res = await fetch("{API_URL}", {{
                    method: "GET", credentials: "include",
                    headers: {{ "accept": "application/json, text/plain, */*" }}
                }});
                return await res.json();
            }}
        """)
    except Exception: return None

def get_task_status(page):
    data = fetch_api_data(page)
    if not data or "results" not in data: return 0, 0, []
    items = data.get("results", {}).get("items", [])
    total = len(items)
    completed = len([t for t in items if t.get("userStatus") == 2])
    completed_titles = [t.get("title", "").strip() for t in items if t.get("userStatus") == 2]
    return completed, total, completed_titles

def simulate_reading(read_page):
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"   📖 正在深度挂机阅读 {wait_time} 秒...")
    try:
        read_page.bring_to_front()
        read_page.evaluate("""
            Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: true});
            Object.defineProperty(document, 'hidden', {value: false, writable: true});
        """)
    except: pass

    start_time = time.time()
    scroll_count = 0
    while time.time() - start_time < wait_time:
        try:
            scroll_count += 1
            if scroll_count == 3:
                read_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                print("   ⬇️ 已滑动至文章最底部...")
            else:
                read_page.evaluate(f"window.scrollBy(0, {random.randint(400, 800)})")
        except: pass
        time.sleep(random.uniform(4.0, 6.0))
        
    try: read_page.evaluate("window.scrollBy(0, -600)")
    except: pass
    time.sleep(2)
    print("   ✅ 阅读停留完成。")

def click_and_handle_reading(context, page) -> bool:
    old_url = page.url
    try:
        locator = page.locator('[data-dxy-click-target="1"]').first
        locator.evaluate("el => el.scrollIntoView({block: 'center', inline: 'center'})")
        time.sleep(1.5)

        new_page = None
        is_same_page = False

        print("   🖱️ 注入油猴同款原生 JS 强制点击...")
        try:
            with context.expect_page(timeout=8000) as popup_info:
                locator.evaluate("""el => {
                    el.click();
                    if (el.firstElementChild) el.firstElementChild.click();
                }""")
            new_page = popup_info.value
            print("   ➡️ 成功捕获弹出的新文章标签页。")
        except PlaywrightTimeoutError:
            print("   ⚠️ 没检测到新标签页，检查是否直接跳转...")
            time.sleep(4)
            if page.url != old_url:
                print(f"   ➡️ 网页已在当前窗口跳转至文章。")
                new_page = page
                is_same_page = True

        if not new_page:
            print("   ❌ 点击失效，页面无任何响应。")
            return False

        # 注入隐身衣到新页面
        if not is_same_page:
            stealth_sync(new_page)

        try: new_page.wait_for_load_state("domcontentloaded", timeout=20000)
        except: pass

        simulate_reading(new_page)

        if not is_same_page:
            try:
                new_page.close()
                print("   ✅ 文章标签页已自动关闭。")
            except: pass
            
        return True
    except Exception as e:
        print(f"   ❌ 点击处理发生未知异常：{str(e)}")
        return False

def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 50)
    print(f"🚀 开始执行账号 [{account_index}]")
    
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        viewport={"width": 1536, "height": 960}, 
        locale="zh-CN", timezone_id="Asia/Shanghai",
        extra_http_headers={
            "Sec-Ch-Ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
    )
    context.add_cookies(parse_cookies(cookie_str))
    
    page = context.new_page()
    # 【核心反侦察】：启动隐身模式，对抗极验指纹检测
    stealth_sync(page)

    clicked_count = 0
    skip_titles = set()

    try:
        print(f"🌐 正在打开任务主页...")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)

        initial_completed, total, api_completed_titles = get_task_status(page)
        print(f"📊 接口摸底：今日总任务 {total} 个 | 已完成 {initial_completed} 个")

        if total > 0 and initial_completed >= total:
            print("🎉 今日阅读任务已全部完成，无需执行。")
            return

        while clicked_count < MAX_CLICKS:
            print("\n" + "-" * 40)
            print(f"🔄 第 {clicked_count + 1} 轮扫描未完成任务...")

            try:
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(6)
            except: pass

            print("⬇️ 正在向下滚动加载完整卡片列表...")
            try:
                for _ in range(4):
                    page.mouse.wheel(0, 1000)
                    time.sleep(1)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(2)
            except: pass

            result = page.evaluate("""
                (payload) => {
                    const TARGET_ATTR = "data-dxy-click-target";
                    const skipTitles = payload.skipTitles || [];
                    const apiCompleted = payload.apiCompleted || [];
                    
                    document.querySelectorAll("[" + TARGET_ATTR + "]").forEach(el => el.removeAttribute(TARGET_ATTR));
                    
                    let btns = Array.from(document.querySelectorAll("div.operate-btn"))
                        .filter(el => (el.innerText || el.textContent).includes("去阅读"));
                        
                    for (let btn of btns) {
                        let card = btn.closest('.task_item');
                        if (!card) continue;
                        
                        // 1. 检查 UI 水印
                        if (card.querySelector("img[alt='已完成水印'], img.watermark, .watermark")) continue;
                        
                        // 2. 检查标题 (结合 API 绝对真理与本地黑名单)
                        let title = (card.innerText || "").split('\\n').filter(x=>x.trim().length>0)[0] || "";
                        let cleanTitle = title.replace(/\\s+/g, "").trim();
                        
                        let shouldSkip = false;
                        
                        for (let st of skipTitles) {
                            if (st && cleanTitle && cleanTitle.includes(st.replace(/\\s+/g, "").trim())) { shouldSkip = true; break; }
                        }
                        
                        if (!shouldSkip) {
                            for(let apiTitle of apiCompleted) {
                                let cleanApi = apiTitle.replace(/\\s+/g, "").trim();
                                if (cleanApi && cleanTitle && (cleanApi.includes(cleanTitle) || cleanTitle.includes(cleanApi))) { 
                                    shouldSkip = true; break; 
                                }
                            }
                        }
                        
                        if (!shouldSkip) {
                            btn.setAttribute(TARGET_ATTR, "1");
                            return { ok: true, title: title };
                        }
                    }
                    return { ok: false };
                }
            """, {
                "skipTitles": list(skip_titles),
                "apiCompleted": api_completed_titles
            })

            if not result or not result.get("ok"):
                print("✅ 页面上所有可见的任务均已在后台完成。")
                break

            title = str(result.get("title", "")).strip()
            if title: skip_titles.add(title)
            print(f"🎯 锁定未完成任务: 【{title}】")

            if click_and_handle_reading(context, page):
                clicked_count += 1
                
            print("🔄 准备返回任务列表并刷新状态...")
            try:
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(6)
            except: pass

            after_completed, _, api_completed_titles = get_task_status(page)
            if after_completed >= total:
                break

        print("\n" + "-" * 40)
        print("🔎 正在等待数据入库并复查入账情况...")
        time.sleep(6)
        
        final_completed, final_total, _ = get_task_status(page)
        newly_completed = final_completed - initial_completed
        print(f"💰 成果核对：本轮新增完成 {newly_completed} 个任务，今日累计完成 {final_completed}/{final_total} 个。")

    except Exception as e:
        print(f"❌ 账号 {account_index} 执行发生异常：{str(e)}")
    finally:
        context.close()

def main():
    cookie_env = os.environ.get("DXY_COOKIE", "")
    if not cookie_env.strip():
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE，请在 GitHub Secrets 中配置！\033[0m")
        return
    
    account_cookies = [c.strip() for c in cookie_env.splitlines() if c.strip()]
    print("=" * 50)
    print(f"🎉 成功识别到 {len(account_cookies)} 个账号配置。")

    with sync_playwright() as p:
        # Actions 环境：headless=True，隐身参数拉满
        browser = p.chromium.launch(
            headless=True, 
            args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox',
                '--disable-popup-blocking',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        for index, cookie_str in enumerate(account_cookies, start=1):
            run_one_account(browser, cookie_str, index)
            if index < len(account_cookies):
                time.sleep(random.randint(5, 10))
                
        browser.close()
        
    print("=" * 50)
    print("🎉 所有账号打卡流程全部执行完毕。")

if __name__ == "__main__":
    time.sleep(random.randint(1, 15))
    main()
