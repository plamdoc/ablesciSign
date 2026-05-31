import requests
import os
import time

def run_account_tasks(cookie, account_index):
    """处理单个账号的阅读任务"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookie,
        'Accept': 'application/json, text/plain, */*'
    }

    list_url = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"
    
    print(f"\n================ 开始执行 [账号 {account_index}] ================")
    try:
        response = requests.get(list_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        items = data.get('results', {}).get('items', [])
        if not items:
            print("⚠️ 未找到任务列表，可能是 Cookie 已过期或今日无任务。")
            return
        
        print(f"✅ 成功获取列表，共发现 {len(items)} 个阅读任务。")
        
        MAX_CLICKS = 5  # 限制每次运行最多只点击 5 个任务
        success_count = 0
        
        for index, item in enumerate(items):
            if success_count >= MAX_CLICKS:
                print(f"🛑 [账号 {account_index}] 已达到本次最大点击限制（{MAX_CLICKS}个），剩下的留到下小时。")
                break

            task_id = item.get('id')
            title = item.get('title', '未知标题')
            user_status = item.get('userStatus')
            
            if not task_id:
                continue
                
            if user_status == 2:
                print(f"[{index + 1}/{len(items)}] ⏭️ 跳过已完成: {title}")
                continue

            print(f"[{index + 1}/{len(items)}] 📖 正在阅读: {title} (ID: {task_id})")
            
            task_url = f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}"
            task_res = requests.get(task_url, headers=headers)
            
            if task_res.status_code == 200:
                print(f"   -> 🎉 点击成功！")
                success_count += 1
            else:
                print(f"   -> ❌ 请求失败，状态码: {task_res.status_code}")
            
            # 账号内的任务延时
            time.sleep(3)
                
        print(f"🎉 [账号 {account_index}] 本轮执行完毕！共成功点击 {success_count} 个新任务。")

    except Exception as e:
        print(f"❌ [账号 {account_index}] 运行发生错误: {e}")


def main():
    # 1. 获取包含多个 Cookie 的环境变量
    cookie_env = os.environ.get('DXY_COOKIE')
    if not cookie_env:
        print("❌ 未找到 DXY_COOKIE 环境变量，请检查 GitHub Secrets 配置。")
        return
    
    # 2. 按换行符分割出多个账号的 Cookie，并去除空行
    cookies = [c.strip() for c in cookie_env.split('\n') if c.strip()]
    
    if not cookies:
        print("❌ 环境变量中没有提取到有效的 Cookie。")
        return
        
    print(f"🚀 检测到 {len(cookies)} 个账号配置，准备开始批量执行...")
    
    # 3. 遍历每个 Cookie 执行任务
    for idx, cookie in enumerate(cookies, start=1):
        run_account_tasks(cookie, idx)
        
        # 多个账号之间增加一点缓冲时间，防止被平台风控关联
        if idx < len(cookies):
            print(f"\n⏳ 等待 5 秒后切换至下一个账号...")
            time.sleep(5)
            
    print("\n✅ 所有账号的任务均已处理完毕！")

if __name__ == "__main__":
    main()
