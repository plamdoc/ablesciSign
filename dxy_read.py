import requests
import os
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 列表接口
LIST_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"

def parse_cookie_string(cookie_str):
    """将普通的 Cookie 字符串解析为 Playwright 需要的字典列表格式"""
    cookies = []
    for item in cookie_str.split(';'):
        if '=' in item:
            name, value = item.strip().split('=', 1)
            cookies.append({
                'name': name,
                'value': value,
                'domain': '.dxy.cn',  # 覆盖所有丁香园子域名
                'path': '/'
            })
    return cookies

def get_task_list(headers):
    response = requests.get(LIST_URL, headers=headers)
    response.raise_for_status()
    return response.json().get('results', {}).get('items', [])

def check_task_success(headers, target_task_id):
    items = get_task_list(headers)
    for item in items:
        if item.get('id') == target_task_id:
            return item.get('userStatus') == 2
    return False

def run_account_tasks(cookie, account_index):
    # Requests 用的 headers
    req_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': cookie,
        'Accept': 'application/json, text/plain, */*'
    }
    
    print(f"\n================ 开始执行 [账号 {account_index}] ================")
    try:
        items = get_task_list(req_headers)
        if not items:
            print("⚠️ 未找到任务，可能是 Cookie 已过期。")
            return
            
        print(f"✅ 成功获取列表，共发现 {len(items)} 个阅读任务。")
        
        # 筛选出未完成的任务
        todo_tasks = [item for item in items if item.get('userStatus') != 2]
        print(f"🔍 其中已完成 {len(items) - len(todo_tasks)} 个，未完成 {len(todo_tasks)} 个。")
        
        if not todo_tasks:
            print("🎉 本账号所有任务均已完成，跳过浏览器环节。")
            return

        MAX_CLICKS = 5
        success_count = 0
        
        # --- 🚀 启动真正的无头浏览器 ---
        print("🌐 正在启动 Playwright 无头浏览器...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            # 注入账号 Cookie
            context.add_cookies(parse_cookie_string(cookie))
            page = context.new_page()

            for index, item in enumerate(todo_tasks):
                if success_count >= MAX_CLICKS:
                    print(f"🛑 [账号 {account_index}] 已达到本次最大点击限制（{MAX_CLICKS}个）。")
                    break

                task_id = item.get('id')
                title = item.get('title', '未知标题')
                
                print(f"[{index + 1}/{len(todo_tasks)}] 📖 浏览器正在阅读: {title}")
                
                task_url = f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}"
                
                try:
                    # 让浏览器打开跳转链接，等待重定向完成
                    page.goto(task_url, timeout=30000)
                    
                    # 模拟真实人类行为：稍微往下滚一点点，更容易触发埋点 JS
                    page.evaluate("window.scrollBy(0, 500)")
                    
                    # 核心：挂机等待 6 秒，给 JS 充足的时间去发送 _da_event 打卡请求
                    page.wait_for_timeout(6000) 
                    
                except PlaywrightTimeoutError:
                    print("   -> ⚠️ 页面加载超时，但可能 JS 已触发，继续尝试校验...")
                except Exception as e:
                    print(f"   -> ❌ 浏览器发生异常: {e}")
                
                # 重新用 requests 去列表里核对，是否真的变成了 2 (已完成)
                is_really_success = check_task_success(req_headers, task_id)
                
                if is_really_success:
                    print(f"   -> 🎉 校验成功！积分已到账。")
                    success_count += 1
                else:
                    print(f"   -> ❌ 校验失败：可能阅读时长不够或被拦截。")

            browser.close()
                
        print(f"🎉 [账号 {account_index}] 运行完毕！共真实完成 {success_count} 个任务。")

    except Exception as e:
        print(f"❌ [账号 {account_index}] 运行发生错误: {e}")

def main():
    cookie_env = os.environ.get('DXY_COOKIE')
    if not cookie_env:
        print("❌ 未找到 DXY_COOKIE 环境变量。")
        return
    
    cookies = [c.strip() for c in cookie_env.split('\n') if c.strip()]
    
    for idx, cookie in enumerate(cookies, start=1):
        run_account_tasks(cookie, idx)
        if idx < len(cookies):
            time.sleep(3)

if __name__ == "__main__":
    main()
