#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("【错误】缺少 playwright 库，请先安装。")
    exit(1)

# =========================
# 基础配置
# =========================
TASK_URL = "https://hao.dxy.cn/plus/activity?source=livesquare"
API_URL = "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list?taskType=2&pageNo=1&pageSize=15&reset=true"

MAX_CLICKS = 5
READ_WAIT_MIN = 35  
READ_WAIT_MAX = 42


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
    try:
        return page.evaluate(f"""
            async () => {{
                const res = await fetch("{API_URL}", {{
                    method: "GET",
                    credentials: "include",
                    headers: {{ "accept": "application/json, text/plain, */*" }}
                }});
                return await res.json();
            }}
        """)
    except Exception:
        return None


def get_card_title(btn) -> str:
    """利用 task_item 容器精准提取标题"""
    try:
        return btn.evaluate("""node => {
            const card = node.closest('.task_item');
            if (card && card.innerText) {
                // 通常标题在文本的第一行或第二行
                const lines = card.innerText.split('\\n').filter(line => line.trim().length > 0);
                return lines[0]; 
            }
            return "未知文章";
        }""")
    except:
        return "未知文章"


def simulate_reading(read_page):
    wait_time = random.randint(READ_WAIT_MIN, READ_WAIT_MAX)
    print(f"   📖 正在深度模拟阅读 {wait_time} 秒...")
    
    read_page.bring_to_front()
    
    start = time.time()
    while time.time() - start < wait_time:
        try:
            scroll_y = random.randint(300, 700)
            read_page.evaluate(f"window.scrollBy(0, {scroll_y})")
        except Exception:
            pass
        time.sleep(random.uniform(2.5, 4.5))


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
        print(f"🌐 正在访问主页注入并渲染 DOM...")
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)

        # 1. API 探路
        data = fetch_task_list(page)
        if not data or 'results' not in data:
            print("❌ 接口数据获取失败，可能 Cookie 已过期。")
            return
            
        items = data['results'].get('items', [])
        initial_completed = len([t for t in items if t.get('userStatus') == 2])
        print(f"📊 接口摸底：今日总任务 {len(items)} 个 | 已完成 {initial_completed} 个")

        if initial_completed >= len(items):
            print("🎉 恭喜！今天的所有阅读任务都已经做完了！")
            return

        print("-" * 35)
        print("🎯 开始执行物理点击策略...")

        print("   ⬇️ 正在向下滚动页面以加载所有懒加载任务...")
        for _ in range(3):
            page.mouse.wheel(0, 1000)
            time.sleep(1.5)
        
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1.5)

        # ==========================================
        # 【核心杀招】使用你扒出来的 class 精准定位！
        # ==========================================
        # 寻找 class 包含 operate-btn 且内部包含“去阅读”文本的 div
        buttons = page.locator("div.operate-btn:has-text('去阅读')").all()
        print(f"   👁️ DOM 扫描完毕：页面上共锁定 {len(buttons)} 个“去阅读”目标 div")

        clicked_count = 0

        for i in range(len(buttons)):
            if clicked_count >= MAX_CLICKS:
                break
                
            # 动态重新抓取，防止因为弹窗等原因导致 DOM 节点刷新失效
            current_btns = page.locator("div.operate-btn:has-text('去阅读')").all()
            if i >= len(current_btns):
                break
            btn = current_btns[i]

            if not btn.is_visible():
                continue

            # UI 过滤：精准查找父级 task_item 里是否有已完成水印
            is_completed = btn.evaluate("""node => {
                const card = node.closest('.task_item');
                if (!card) return false;
                return !!card.querySelector('img[alt="已完成水印"], img.watermark');
            }""")

            title = get_card_title(btn)

            if is_completed:
                print(f"   ⏭️ 识别到水印，跳过已完成: 【{title[:20]}...】")
                continue

            print(f"\n📍 锁定未完成任务: 【{title}】")
            
            try:
                # 把按钮滚动到视口中
                btn.scroll_into_view_if_needed()
                time.sleep(1.5)

                with context.expect_page(timeout=8000) as popup_info:
                    print("   🖱️ 触发原生地图级物理点击...")
                    box = btn.bounding_box()
                    if box:
                        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        time.sleep(0.3)
                        page.mouse.down()
                        time.sleep(0.1)
                        page.mouse.up()
                    else:
                        btn.click(force=True)

                new_page = popup_info.value
                print("   ➡️ 成功捕获新文章标签页。")
                
                simulate_reading(new_page)
                
                new_page.close()
                print("   ✅ 标签页已关闭，本篇流程结束。")
                clicked_count += 1
                
                time.sleep(random.randint(4, 7))

            except PlaywrightTimeoutError:
                print("   ⚠️ 未捕获到新弹窗，检查原网页是否跳转...")
                if page.url != TASK_URL:
                    simulate_reading(page)
                    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=45000)
                    time.sleep(5)
                    clicked_count += 1
                else:
                    print("   ⚠️ 页面未跳转且无弹窗，跳过此异常任务。")

        print("\n" + "-" * 35)
        print("🔎 正在等待数据入库并复查入账情况...")
        time.sleep(6) 
        
        final_data = fetch_task_list(page)
        if final_data and 'results' in final_data:
            final_items = final_data['results'].get('items', [])
            final_completed = len([t for t in final_items if t.get('userStatus') == 2])
            newly_completed = final_completed - initial_completed
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
    print("🎉 所有账号今日任务流程执行完毕！")


if __name__ == "__main__":
    time.sleep(random.randint(1, 15))
    main()
