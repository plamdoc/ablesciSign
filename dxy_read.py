import requests
import os
import time

def run_dxy_tasks():
    # 从 GitHub Secrets 中读取配置好的 Cookie
    cookie = os.environ.get('DXY_COOKIE')
    if not cookie:
        print("❌ 未找到 DXY_COOKIE 环境变量，请检查 GitHub Secrets 配置。")
        return

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookie,
        'Accept': 'application/json, text/plain, */*'
    }

    # 获取任务列表的接口
    list_url = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"
    
    print("⏳ 开始获取丁香园阅读任务列表...")
    try:
        response = requests.get(list_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # 解析 JSON 获取任务列表
        items = data.get('results', {}).get('items', [])
        if not items:
            print("⚠️ 未找到任务列表，可能是 Cookie 已过期或今日无任务。")
            return
        
        print(f"✅ 成功获取，共发现 {len(items)} 个阅读任务。")
        
        MAX_CLICKS = 5  # 💡 核心限制：每次运行最多只点击 5 个任务
        success_count = 0
        
        # 遍历执行阅读任务
        for index, item in enumerate(items):
            # 检查是否已经点击够了 5 个
            if success_count >= MAX_CLICKS:
                print(f"\n🛑 已达到本次运行的最大点击限制（{MAX_CLICKS}个），脚本自动安全退出。剩下的任务留到下小时运行。")
                break

            task_id = item.get('id')
            title = item.get('title', '未知标题')
            user_status = item.get('userStatus')
            
            if not task_id:
                continue
                
            # userStatus == 2 通常表示该任务之前已经完成，直接跳过，不计入5次限制
            if user_status == 2:
                print(f"[{index + 1}/{len(items)}] ⏭️ 跳过已完成: {title}")
                continue

            print(f"[{index + 1}/{len(items)}] 📖 正在阅读: {title} (ID: {task_id})")
            
            # 拼接阅读跳转链接
            task_url = f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}"
            
            # 发送请求模拟点击阅读
            task_res = requests.get(task_url, headers=headers)
            
            if task_res.status_code == 200:
                print(f"   -> 🎉 任务点击成功！")
                success_count += 1
            else:
                print(f"   -> ❌ 请求失败，状态码: {task_res.status_code}")
            
            # 防风控延时 (随机等待 2-4 秒)
            time.sleep(3)
                
        print(f"\n🎉 本轮任务执行完毕！本次共成功点击了 {success_count} 个新任务。")

    except Exception as e:
        print(f"❌ 运行过程中发生错误: {e}")

if __name__ == "__main__":
    run_dxy_tasks()
