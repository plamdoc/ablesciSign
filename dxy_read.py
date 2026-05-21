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
# 基础与接口配置
# =========================
TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"

# 你抓到的核心 API 接口
API_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"

# 单次运行最大阅读数量
MAX_CLICKS = 5

# 阅读页停留时间 (秒)
READ_WAIT_MIN = 20
READ_WAIT_MAX = 35


def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": domain,
            "path": "/",
            "secure": True,
            "sameSite": "Lax"
        })
    return cookies


def fetch_task_list(page):
    """
    【核心黑科技】直接在页面上下文中发起 fetch 请求，获取后端最真实的 JSON 数据
    """
    try:
        return page.evaluate(f"""
            async () => {{
                const res = await fetch("{API_URL}", {{
                    method: "GET",
                    credentials: "include",
                    headers: {{
                        "accept": "application/json, text/plain, */*"
                    }}
                }});
                return await res.json();
            }}
        """)
    except Exception as e:
        print(f"❌ 接口请求失败: {str(e)}")
        return None


def simulate_reading(read_page):
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"   📖 正在认真阅读 {wait_time} 秒...")
    start = time.time()
    while time.time() - start < wait_time:
        try:
            # 模拟往下翻阅文章
            read_page.mouse.wheel(0, random.randint(300, 900))
        except Exception:
            pass
        time.sleep(random.uniform(2.0, 4.0))


def run_one_account(browser, cookie_str: str, account_index: int):
    print("=" * 45)
    print(f"🚀 开始登录账号 [{account_index}]")
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900}
    )
    context.add_cookies(parse_cookies(cookie_str))
    page = context.new_page()

    try:
        print(f"🌐 正在访问主页注入 Cookie...")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)

        # 1. 调用 API 获取任务全景图
        print("📡 正在向服务器请求最真实的底层任务数据...")
        data = fetch_task_list(page)
        
        if not data or 'results' not in data:
            print("❌ 未能获取到有效的接口数据，Cookie 可能过期。")
            return

        items = data['results'].get('items', [])
        if not items:
            print("📋 当前没有可用的阅读任务。")
            return

        # 2. 根据 userStatus 完美分类任务
        completed_tasks = [item for item in items if item.get('userStatus') == 2]
        unread_tasks = [item for item in items if item.get('userStatus') == 1]

        print(f"📊 接口解析成功！今日总任务: {len(items)} 个")
        print(f"✅ 已完成: {len(completed_tasks)} 个 | ⏳ 待阅读: {len(unread_tasks)} 个")

        if not unread_tasks:
            print("🎉 恭喜！今天的所有阅读任务都已经做完了！")
            return

        # 3. 开始执行未完成任务（限制单次最大数量）
        tasks_to_do = unread_tasks[:MAX_CLICKS]
        print(f"🎯 准备执行其中 {len(tasks_to_do)} 个任务 (单次上限 {MAX_CLICKS} 个)...")

        for i, task in enumerate(tasks_to_do, 1):
            title = task.get('title', '未知标题')
            url = task.get('contentUrl', '')

            print("-" * 35)
            print(f"📍 任务 {i}/{len(tasks_to_do)}: 【{title}】")

            if not url:
                print("   ⚠️ 该任务没有提供文章链接，跳过。")
                continue

            try:
                new_page = context.new_page()
                print("   ➡️ 获取到直达链接，正在闪现至文章页面...")
                
                # 伪造 referer 骗过服务器，让它以为我们是从任务列表点进来的
                new_page.goto(url, referer=TASK_URL, wait_until="domcontentloaded", timeout=45000)
                
                # 模拟阅读
                simulate_reading(new_page)
                
                new_page.close()
                print("   ✅ 本篇文章阅读完毕，标签页已关闭。")
                
            except Exception as e:
                print(f"   ❌ 阅读过程出错: {str(e)}")

            if i < len(tasks_to_do):
                delay = random.randint(3, 7)
                print(f"   💤 休息 {delay} 秒防风控...")
                time.sleep(delay)

        # 4. 再次调用 API 核对最终成果
        print("-" * 35)
        print("🔎 正在通过底层接口复查丁当到账情况...")
        time.sleep(4)  # 给服务器 4 秒钟的时间把数据入库
        final_data = fetch_task_list(page)
        
        if final_data and 'results' in final_data:
            final_items = final_data['results'].get('items', [])
            final_completed = len([t for t in final_items if t.get('userStatus') == 2])
            newly_completed = final_completed - len(completed_tasks)
            print(f"💰 成果核对：本轮实际新增完成 {newly_completed} 个任务！今日已累计完成 {final_completed}/{len(items)} 个。")

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
    print("=" * 45)
    print(f"🎉 识别到 {len(account_cookies)} 个账号配置，即将发车...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        for index, cookie_str in enumerate(account_cookies, start=1):
            run_one_account(browser, cookie_str, index)
            if index < len(account_cookies):
                time.sleep(random.randint(5, 10))

        browser.close()
    print("🎉 所有账号今天这波阅读任务已搞定！")


if __name__ == "__main__":
    time.sleep(random.randint(1, 15))
    main()
