import requests
import os
import time

# 列表接口 URL
LIST_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"

def get_task_list(headers):
    """获取任务列表并返回 items"""
    response = requests.get(LIST_URL, headers=headers)
    response.raise_for_status()
    return response.json().get('results', {}).get('items', [])

def check_task_success(headers, target_task_id):
    """重新获取列表，检查指定 task_id 的状态是否变为已完成 (userStatus == 2)"""
    items = get_task_list(headers)
    for item in items:
        if item.get('id') == target_task_id:
            return item.get('userStatus') == 2
    return False

def run_account_tasks(cookie, account_index):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookie,
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://hao.dxy.cn/plus/activity?source=livesquare', 
        'Origin': 'https://hao.dxy.cn',
        'Connection': 'keep-alive'
    }
    
    print(f"\n================ 开始执行 [账号 {account_index}] ================")
    try:
        items = get_task_list(headers)
        if not items:
            print("⚠️ 未找到任务列表，可能是 Cookie 已过期。")
            return
        
        print(f"✅ 成功获取列表，共发现 {len(items)} 个阅读任务。")
        
        MAX_CLICKS = 5
        success_count = 0
        
        for index, item in enumerate(items):
            if success_count >= MAX_CLICKS:
                print(f"🛑 [账号 {account_index}] 已达到本次最大尝试限制（{MAX_CLICKS}个）。")
                break

            task_id = item.get('id')
            title = item.get('title', '未知标题')
            user_status = item.get('userStatus')
            # 提取真实文章的 URL
            content_url = item.get('contentUrl') 
            
            if not task_id:
                continue
                
            if user_status == 2:
                print(f"[{index + 1}/{len(items)}] ⏭️ 跳过已完成: {title}")
                continue

            print(f"[{index + 1}/{len(items)}] 📖 尝试阅读: {title}")
            
            # 步骤 1：请求点击追踪链接
            task_url = f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}"
            requests.get(task_url, headers=headers)
            
            # 步骤 2：追加请求真实的 contentUrl (模拟浏览器跳转)
            if content_url:
                # 伪装是从 linkTask 跳转过来的
                article_headers = headers.copy()
                article_headers['Referer'] = task_url 
                requests.get(content_url, headers=article_headers)
            
            # 步骤 3：模拟停留阅读 4 秒钟，等待服务器结算
            time.sleep(4)
            
            # 步骤 4：严格校验！重新拉取列表判断是否真的成功了
            is_really_success = check_task_success(headers, task_id)
            
            if is_really_success:
                print(f"   -> 🎉 校验成功！积分已到账。")
                success_count += 1
            else:
                print(f"   -> ❌ 校验失败：请求已发送，但服务器未判定完成。可能存在隐藏的 POST 打卡接口。")
                
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
            time.sleep(5)

if __name__ == "__main__":
    main()
