#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random
import re

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

MAX_CLICKS = 5
READ_WAIT_MIN = 45
READ_WAIT_MAX = 55


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
    except Exception:
        return None


def get_task_status(page):
    data = fetch_api_data(page)
    if not data or "results" not in data: return 0, 0, []
    items = data.get("results", {}).get("items", [])
    
    total = len(items)
    completed = len([t for t in items if t.get("userStatus") == 2])
    # 提取所有未完成的任务列表
    uncompleted_tasks = [t for t in items if t.get("userStatus") == 1]
    
    return completed, total, uncompleted_tasks


def simulate_reading(read_page):
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"   📖 正在深度挂机阅读 {wait_time} 秒...")
    
    try:
        read_page.bring_to_front()
        # 欺骗浏览器前台状态，防止后台失焦导致计时器暂停
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
                print("   ⬇️ 已滑动至文章最底部，触发完成判定...")
            else:
                read_page.evaluate(f"window.scrollBy(0, {random.randint(400, 800)})")
        except: pass
        time.sleep(random.uniform(4.0, 6.0))

    print("   ✅ 阅读停留完成。")


def process_task(context, page, task):
    """
    分离战术：JS 触发前端埋点信号 -> Python 手动跳转真实链接阅读
    """
    title = task.get("title", "")
    url = task.get("contentUrl", "")
    
    if not url:
        print(f"   ⚠️ 任务【{title[:15]}...】缺少有效文章链接，跳过。")
        return False

    print(f"\n📍 锁定未完成任务: 【{title}】")
    
    # 1. 提取核心搜索词 (去除多余字符，保留汉字字母，取前15位)
    clean_title = re.sub(r'[^\w\u4e00-\u9fa5]', '', title.replace("阅读文章", ""))
    search_str = clean_title[:15]

    # 2. 注入 JS：精准定位按钮并触发点击埋点 (屏蔽弹窗防止拦截报错)
    js_clicked = page.evaluate("""
        (searchStr) => {
            // 劫持弹窗，我们不需要它弹，只需要它发埋点信号
            window.open = function() { return null; };
            
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
            const allBtnNodes = [];
            let node;
            while (node = walker.nextNode()) {
                if (node.nodeValue.trim() === '去阅读') {
                    allBtnNodes.push(node.parentElement);
                }
            }
            
            for (let btn of allBtnNodes) {
                let p = btn;
                for (let i = 0; i < 15; i++) {
                    if (!p) break;
                    let text = (p.innerText || "").replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '');
                    if (text.includes(searchStr)) {
                        btn.click();
                        // 兜底连击
                        if (btn.firstElementChild) btn.firstElementChild.click();
                        return true;
                    }
                    p = p.parentElement;
                }
            }
            return false;
        }
    """, search_str)

    if js_clicked:
        print("   🔫 JS 信号枪已发射，成功触发前端统计。")
    else:
        print("   ⚠️ UI 层未找到按钮，直接强制进入文章...")

    # 3. Python 开启传送门：手动接管新标签页跳往文章
    print("   ➡️ 开启传送门，跳往文章真实链接...")
    new_page = context.new_page()
    try:
        # 伪造 Referer 欺骗服务器是从主页跳过来的
        new_page.goto(url, referer=TASK_URL, wait_until="domcontentloaded", timeout=45000)
        simulate_reading(new_page)
    except Exception as e:
        print(f"   ❌ 阅读过程发生异常: {str(e)}")
    finally:
        try: new_page.close()
        except: pass

    return True


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
        print(f"🌐 正在打开任务主页...")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)

        # 暴力滚动把所有懒加载数据刷出来
        print("⬇️ 正在向下滚动加载完整卡片列表...")
        for _ in range(4):
            page.mouse.wheel(0, 1000)
            time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(2)

        # 直接从 API 获取真相
        initial_completed, total, uncompleted_tasks = get_task_status(page)
        print(f"📊 接口真相：今日总任务 {total} 个 | 已完成 {initial_completed} 个")

        if total > 0 and initial_completed >= total:
            print("🎉 今日阅读任务已全部完成，无需执行。")
            return

        if not uncompleted_tasks:
            print("⚠️ 没有获取到待阅读的任务列表。")
            return

        # 取前 5 个未完成的任务进行执行
        tasks_to_do = uncompleted_tasks[:MAX_CLICKS]
        print(f"🎯 提取出 {len(tasks_to_do)} 个未读任务，准备执行阅读流程...")

        clicked_count = 0
        for task in tasks_to_do:
            if process_task(context, page, task):
                clicked_count += 1
            time.sleep(random.randint(4, 7))  # 任务之间的安全间隔

        print("\n" + "-" * 40)
        print("🔄 正在刷新页面，同步最新积分数据...")
        try:
            page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
        except: pass
        
        final_completed, final_total, _ = get_task_status(page)
        newly_completed = final_completed - initial_completed
        print(f"💰 成果核对：本轮新增完成 {newly_completed} 个任务，今日累计完成 {final_completed}/{final_total} 个。")

    except Exception as e:
        print(f"❌ 账号 {account_index} 执行发生严重异常：{str(e)}")
    finally:
        context.close()


def main():
    cookie_env = os.environ.get("DXY_COOKIE", "")
    if not cookie_env.strip():
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE！\033[0m")
        return
    
    account_cookies = [c.strip() for c in cookie_env.splitlines() if c.strip()]
    print("=" * 50)
    print(f"🎉 成功识别到 {len(account_cookies)} 个账号配置。")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        for index, cookie_str in enumerate(account_cookies, start=1):
            run_one_account(browser, cookie_str, index)
            if index < len(account_cookies):
                time.sleep(random.randint(5, 10))
                
        browser.close()
        
    print("=" * 50)
    print("🎉 所有账号打卡流程全部执行完毕。")

if __name__ == "__main__":
    # 定时任务随机错峰启动
    time.sleep(random.randint(1, 10))
    main()
