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
            # 增加参数，试图绕过基础的反爬检测
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled'] 
            )
            context = browser.new_context(
                user_agent=req_headers['User-Agent'],
                viewport={'width': 1280, 'height': 800}
            )
            
            # 注入 Cookie
            context.add_cookies(parse_cookie_string(cookie_str))
            
            # 创建新页面并注入反检测 JS 脚本 (关键：抹除 webdriver 特征)
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            for i, task in enumerate(todo_tasks):
                if success_count >= MAX_CLICKS:
                    print(f"🛑 达到每次运行最大限制 {MAX_CLICKS} 个，退出。")
                    break
                    
                task_id = task.get('id')
                content_url = task.get('contentUrl', '')
                print(f"[{i+1}/{len(todo_tasks)}] 📖 浏览器正在阅读: {task.get('title')}")
                
                try:
                    # 先访问中转链接打卡
                    page.goto(f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}", timeout=20000, wait_until="commit")
                    page.wait_for_timeout(2000)
                    
                    # 如果有真实文章内容地址，主动跳转过去，确保触发打卡 JS
                    if content_url and "hao.dxy.cn" in content_url:
                        page.goto(content_url, timeout=20000, wait_until="domcontentloaded")
                    
                    # 打印当前页面标题，用于排查是否被拦截在登录页或验证码页
                    print(f"   -> 当前页面定位: {page.title()}")
                    
                    # 深度阅读模拟：分 4 次滑动，每次间隔 3 秒，总共停留 12 秒
                    for _ in range(4):
                        page.evaluate("window.scrollBy(0, 400)")
                        page.wait_for_timeout(3000) 
                    
                    # 重新拉取接口核对
                    verify_res = requests.get(LIST_URL, headers=req_headers).json()
                    new_status = next((t.get('userStatus') for t in verify_res.get('results', {}).get('items', []) if t.get('id') == task_id), 0)
                    
                    if new_status == 2:
                        print("   -> 🎉 校验成功！积分已到账。")
                        success_count += 1
                    else:
                        print("   -> ❌ 校验失败：请结合上面的'当前页面定位'排查原因。")
                        
                except Exception as e:
                    print(f"   -> ⚠️ 浏览器访问超时或报错，继续下一个: {e}")
                    
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
            time.sleep(3) # 账号间缓冲
