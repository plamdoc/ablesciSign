#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

# 修改了这里的异常捕获，确保如果缺少库会打印真实的详细原因
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    from playwright_stealth import stealth_sync
except ImportError as e:
    print(f"【致命错误】依赖库导入失败，真实原因是：{e}")
    print("本地运行请先执行：pip install playwright playwright-stealth")
    exit(1)

# =========================
# 基础配置
# =========================
TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"
API_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"

MAX_CLICKS = 5

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
    if not data or "results" not in data: return 0, 0
    items = data.get("results", {}).get("items", [])
    total = len(items)
    completed = len([t for t in items if t.get("userStatus") == 2])
    return completed, total

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
    stealth_sync(page)

    try:
        print(f"🌐 正在打开任务主页...")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)

        initial_completed, total = get_task_status(page)
        print(f"📊 接口摸底：今日总任务 {total} 个 | 已完成 {initial_completed} 个")

        if total > 0 and initial_completed >= total:
            print("🎉 今日阅读任务已全部完成，无需执行。")
            return

        print("⬇️ 正在向下滚动加载完整卡片列表...")
        try:
            for _ in range(4):
                page.mouse.wheel(0, 1000)
                time.sleep(1)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(2)
        except: pass

        print("🚀 尝试批量点击所有未完成任务...")
        clicked_count = page.evaluate("""
            (maxClicks) => {
                let btns = Array.from(document.querySelectorAll("div.operate-btn"))
                    .filter(el => (el.innerText || el.textContent).includes("去阅读"));
                
                let count = 0;
                for (let btn of btns) {
                    let card = btn.closest('.task_item');
                    if (card && card.querySelector("img[alt='已完成水印'], img.watermark, .watermark")) continue;
                    
                    if (count >= maxClicks) break;
                    
                    // 间隔 2.5 秒点击一个，防止被判定为瞬间并发异常
                    setTimeout(() => {
                        btn.click();
                        if (btn.firstElementChild) btn.firstElementChild.click();
                    }, count * 2500);
                    count++;
                }
                return count;
            }
        """, MAX_CLICKS)

        if clicked_count == 0:
            print("✅ 页面上所有可见的任务已标记为完成。")
            return

        print(f"🎯 已触发 {clicked_count} 个任务的并发阅读，正在等待标签页弹出...")
        time.sleep(clicked_count * 2.5 + 5)

        all_pages = context.pages
        print(f"📂 浏览器当前共挂载了 {len(all_pages)} 个标签页（含主页与弹窗）。")

        for p in all_pages:
            if p != page:
                try:
                    stealth_sync(p)
                    p.evaluate("Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: true});")
                except: pass

        print("\n" + "-" * 40)
        print("⏳ 触发【验证弹窗 10 分钟失效机制】...")
        print("💡 将在后台集中挂机 11 分钟，请勿关闭程序。")
        
        for i in range(1, 12):
            print(f"   [{i}/11] 深度挂机中，等待后端超时放行...")
            for p in all_pages:
                try: p.evaluate(f"window.scrollBy(0, {random.randint(200, 500)})")
                except: pass
            time.sleep(60)

        print("\n" + "-" * 40)
        print("🧹 挂机结束，正在清理阅读标签页...")
        for p in all_pages:
            if p != page:
                try: p.close()
                except: pass
                
        print("🔄 刷新任务主页，核对最终入账情况...")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        
        final_completed, final_total = get_task_status(page)
        newly_completed = final_completed - initial_completed
        print(f"💰 成果核对：本轮成功入账 {newly_completed} 个任务，今日累计完成 {final_completed}/{final_total} 个。")

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
