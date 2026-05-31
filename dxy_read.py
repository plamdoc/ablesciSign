import os
import time
import requests
from playwright.sync_api import sync_playwright

LIST_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"
MAX_CLICKS = 5

def parse_cookie_string(cookie_str):
    """转换 Cookie 格式供 Playwright 使用"""
    return [{'name': k.strip(), 'value': v.strip(), 'domain': '.dxy.cn', 'path': '/'} 
            for item in cookie_str.split(';') if '=' in item for k, v in [item.split('=', 1)]]

def run_account(cookie_str, account_idx):
    print(f"\n========== 开始执行 [账号 {account_idx}] ==========")
    req_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookie_str,
        'Accept': 'application/json'
    }
    
    try:
        # 1. 获取任务列表
        res = requests.get(LIST_URL, headers=req_headers).json()
        items = res.get('results', {}).get('items', [])
        todo_tasks = [t for t in items if t.get('userStatus') != 2]
        
        print(f"✅ 发现 {len(todo_tasks)} 个未完成任务。")
        if not todo_tasks:
            return

        success_count = 0
        
        # 2. 启动真实无头浏览器
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled'] 
            )
            context = browser.new_context(
                user_agent=req_headers['User-Agent'],
                viewport={'width': 1280, 'height': 800}
            )
            context.add_cookies(parse_cookie_string(cookie_str))
            
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            for i, task in enumerate(todo_tasks):
                if success_count >= MAX_CLICKS:
                    print(f"🛑 达到每次运行最大限制 {MAX_CLICKS} 个，退出。")
                    break
                    
                task_id = task.get('id')
                print(f"[{i+1}/{len(todo_tasks)}] 📖 正在模拟阅读: {task.get('title')}")
                
                # ---------------- 核心防弹区域 ----------------
                try:
                    # 告诉浏览器去访问，如果发生 302 重定向报错，直接忽略
                    page.goto(f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}", timeout=15000)
                except Exception:
                    pass # 忽略 Playwright 的跳转打断错误
                
                # 给网页飞一会儿的时间（等待重定向彻底落地）
                page.wait_for_timeout(4000)
                
                try:
                    print(f"   -> 落地页面: {page.title()}")
                except Exception:
                    pass
                
                # 分段滑动，强行续命 12 秒。遇到上下文销毁直接无视。
                for _ in range(4):
                    try:
                        page.evaluate("window.scrollBy(0, 500)")
                    except Exception:
                        pass # 忽略所有执行环境被销毁的报错
                    page.wait_for_timeout(3000)
                # ----------------------------------------------
                
                # 重新拉取接口核对
                try:
                    verify_res = requests.get(LIST_URL, headers=req_headers).json()
                    new_status = next((t.get('userStatus') for t in verify_res.get('results', {}).get('items', []) if t.get('id') == task_id), 0)
                    
                    if new_status == 2:
                        print("   -> 🎉 校验成功！积分已到账。")
                        success_count += 1
                    else:
                        print("   -> ❌ 校验失败：可能阅读时长不够或平台风控。")
                except Exception as e:
                    print(f"   -> ⚠️ 校验状态异常: {e}")
                        
            browser.close()
            
    except Exception as e:
        print(f"❌ 账号 {account_idx} 运行异常: {e}")

if __name__ == "__main__":
    cookie_env = os.environ.get('DXY_COOKIE', '')
    cookies = [c.strip() for c in cookie_env.split('\n') if c.strip()]
    
    if not cookies:
        print("❌ 未找到 DXY_COOKIE，请检查 Secrets 配置。")
    else:
        for idx, c in enumerate(cookies, 1):
            run_account(c, idx)
            time.sleep(3)
