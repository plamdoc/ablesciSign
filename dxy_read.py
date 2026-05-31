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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
        
        # 2. 启动真实无头浏览器去阅读
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=req_headers['User-Agent'])
            context.add_cookies(parse_cookie_string(cookie_str))
            page = context.new_page()

            for i, task in enumerate(todo_tasks):
                if success_count >= MAX_CLICKS:
                    print(f"🛑 达到每次运行最大限制 {MAX_CLICKS} 个，退出。")
                    break
                    
                task_id = task.get('id')
                print(f"[{i+1}/{len(todo_tasks)}] 📖 浏览器正在阅读: {task.get('title')}")
                
                try:
                    # 让真实浏览器去访问跳转链接
                    page.goto(f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}", timeout=20000)
                    
                    # 模拟真人滚动并等待 6 秒，确保网页里的 JS 埋点发送成功！
                    page.evaluate("window.scrollBy(0, 800)")
                    page.wait_for_timeout(6000) 
                    
                    # 重新拉取接口核对
                    verify_res = requests.get(LIST_URL, headers=req_headers).json()
                    new_status = next((t.get('userStatus') for t in verify_res.get('results', {}).get('items', []) if t.get('id') == task_id), 0)
                    
                    if new_status == 2:
                        print("   -> 🎉 校验成功！积分已到账。")
                        success_count += 1
                    else:
                        print("   -> ❌ 校验失败：服务器未确认。")
                        
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
