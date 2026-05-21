#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("【错误】缺少 playwright 库，请先安装。")
    exit(1)

# =========================
# 基础配置
# =========================
TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"
API_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"


def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        name, value = item.split("=", 1)
        cookies.append({
            "name": name.strip(), "value": value.strip(),
            "domain": domain, "path": "/",
            "secure": True, "sameSite": "Lax"
        })
    return cookies


def fetch_task_list(page):
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
    except Exception:
        return None


def get_api_task_status(page):
    data = fetch_task_list(page)
    if not data or "results" not in data: return 0, 0
    items = data.get("results", {}).get("items", [])
    if not isinstance(items, list): return 0, 0
    total = len(items)
    completed = len([item for item in items if item.get("userStatus") == 2])
    return completed, total


def wait_and_load_page(page):
    print(f"🌐 正在打开任务页：{TASK_URL}")
    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
    print("⏳ 等待页面渲染 6 秒...")
    time.sleep(6)
    
    print("⬇️ 正在向下滚动页面，加载完整任务列表...")
    try:
        for _ in range(3):
            page.mouse.wheel(0, 1000)
            time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(2)
    except: pass


def execute_tampermonkey_script(page):
    """
    【核心变更】完美移植了用户提供的油猴核心逻辑！
    利用 TreeWalker 精准找词，利用 contains 锁定卡片，利用底层 el.click() 确保百分百命中。
    """
    js_code = """
    () => {
        const allBtnNodes = [];
        
        // 1. 穿透查找页面上所有纯文本为“去阅读”的节点
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        let node;
        while (node = walker.nextNode()) {
            if (node.nodeValue.trim() === '去阅读') {
                allBtnNodes.push(node.parentElement);
            }
        }

        if (allBtnNodes.length === 0) {
            return { clicked: 0, skipped: 0, msg: "未找到去阅读按钮" };
        }

        const nodesToClick = [];
        let skipCount = 0;

        // 2. 遍历这些按钮，判断它们所在的卡片是否已经完成
        allBtnNodes.forEach(btnEl => {
            let taskCard = btnEl;
            let parent = btnEl.parentElement;

            while(parent) {
                let containsCount = 0;
                for(let b of allBtnNodes) {
                    if (parent.contains(b)) containsCount++;
                }
                if (containsCount > 1) {
                    break;
                }
                taskCard = parent;
                parent = parent.parentElement;
                if (taskCard.tagName === 'BODY' || taskCard.tagName === 'HTML') break;
            }

            // 3. 在这个独立卡片内检查是否包含完成标志
            const htmlStr = taskCard.innerHTML.toLowerCase();
            const textStr = taskCard.textContent || '';

            const isCompleted = textStr.includes('已完成') ||
                                htmlStr.includes('已完成') ||
                                htmlStr.includes('finish') ||
                                htmlStr.includes('complete');

            if (!isCompleted) {
                nodesToClick.push(btnEl);
            } else {
                skipCount++;
            }
        });

        // 4. 执行点击 (限制单次最多点 5 个防风控)
        let clickedCount = 0;
        nodesToClick.slice(0, 5).forEach(el => {
            el.click();
            clickedCount++;
        });

        return { clicked: clickedCount, skipped: skipCount, msg: "success" };
    }
    """
    return page.evaluate(js_code)


def handle_opened_pages(context, main_page):
    """
    接管油猴点击后弹出的所有新标签页，执行批量挂机阅读
    """
    print("⏳ 等待 4 秒，让浏览器弹出并加载新标签页...")
    time.sleep(4)
    
    # 筛选出所有新打开的页面
    new_pages = [p for p in context.pages if p != main_page]
    
    if not new_pages:
        print("   ⚠️ 警告：执行了点击，但没有产生新标签页。")
        if main_page.url != TASK_URL:
            print("   ➡️ 原页面发生了跳转，将在原页面挂机阅读 40 秒...")
            for i in range(3):
                time.sleep(13)
                main_page.evaluate("window.scrollBy(0, 500)")
            main_page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)
        return

    print(f"   ➡️ 成功捕获到 {len(new_pages)} 个新打开的文章标签页！开始多线程并行挂机...")

    # 第一步：给所有新页面注入防挂机代码
    for p in new_pages:
        try:
            p.evaluate("""
                Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: true});
                Object.defineProperty(document, 'hidden', {value: false, writable: true});
            """)
            p.evaluate("window.scrollBy(0, 400)")
        except: pass

    # 第二步：挂机循环，每 15 秒全部滑动一次，持续 45 秒
    for step in range(1, 4):
        print(f"   📖 正在认真阅读中... (第 {step}/3 阶段)")
        time.sleep(15)
        for p in new_pages:
            try: p.evaluate(f"window.scrollBy(0, {random.randint(400, 800)})")
            except: pass

    # 第三步：划到底部，触发最终统计，然后关闭
    print("   ⏬ 划至所有文章底部，准备关闭标签页...")
    for p in new_pages:
        try: p.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except: pass
    time.sleep(3)

    for p in new_pages:
        try: p.close()
        except: pass
        
    print("   ✅ 所有文章阅读完毕并关闭。")


def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 50)
    print(f"🚀 开始执行账号 [{account_index}]")
    
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai"
    )
    context.add_cookies(parse_cookies(cookie_str))
    page = context.new_page()

    try:
        wait_and_load_page(page)

        initial_completed, total = get_api_task_status(page)
        print(f"📊 接口摸底：今日总任务 {total} 个 | 已完成 {initial_completed} 个")

        if total > 0 and initial_completed >= total:
            print("🎉 今日阅读任务已全部完成。")
            return

        print("\n" + "-" * 40)
        print("🎯 开始执行原生 JS (油猴同款) 扫描与点击...")
        
        # 1. 直接触发脚本
        result = execute_tampermonkey_script(page)
        clicked = result.get('clicked', 0)
        skipped = result.get('skipped', 0)
        
        print(f"📋 脚本反馈：智能跳过 {skipped} 个已完成，成功点击了 {clicked} 个新任务！")
        
        if clicked > 0:
            # 2. 批量处理刚刚点击出来的所有标签页
            handle_opened_pages(context, page)
        else:
            print("   ⚠️ 没有可点击的任务。")

        print("\n" + "-" * 40)
        print("🔎 正在刷新页面并复查最终入账情况...")
        try:
            page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        except: pass
        
        final_completed, final_total = get_api_task_status(page)
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
        # 【极其关键】：一定要加上 --disable-popup-blocking，否则你的油猴脚本在云端点不开新标签页！
        browser = p.chromium.launch(
            headless=True, 
            args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox',
                '--disable-popup-blocking'  
            ]
        )
        
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
