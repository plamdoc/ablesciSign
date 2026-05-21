#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("【错误】缺少 playwright 库。")
    exit(1)

def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    cookies = []
    for item in cookie_str.split(';'):
        if '=' in item:
            name, value = item.strip().split('=', 1)
            cookies.append({
                'name': name,
                'value': value,
                'domain': domain,
                'path': '/'
            })
    return cookies

def main():
    cookie_env = os.environ.get('DXY_COOKIE', '')
    if not cookie_env:
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE！\033[0m")
        return

    account_cookies = [c.strip() for c in cookie_env.split('\n') if c.strip()]
    print("=" * 40)
    print(f"🎉 成功解析到 {len(account_cookies)} 个账号配置，准备开始执行...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        for index, current_cookie in enumerate(account_cookies, start=1):
            print("-" * 40)
            print(f"🚀 开始执行 [账号 {index}] ...")
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
            context.add_cookies(parse_cookies(current_cookie))
            page = context.new_page()
            url = "https://hao.dxy.cn/plus/activity?source=livesquare"
            
            try:
                print(f"🌐 正在打开页面: {url}")
                page.goto(url, wait_until="networkidle", timeout=45000)
                
                print("⏳ 等待页面和动态任务列表完全渲染 (6秒)...")
                time.sleep(6) 

                # ==========================================
                # 全新逻辑：使用 Playwright 原生定位器和物理点击
                # ==========================================
                
                # 1. 精准抓取页面上所有文本就是“去阅读”的元素
                buttons = page.get_by_text("去阅读", exact=True).all()
                
                if not buttons:
                    print("📋 页面未找到任何“去阅读”按钮。")
                    continue

                clicked_count = 0
                skip_count = 0
                MAX_CLICKS = 5

                for btn in buttons:
                    if clicked_count >= MAX_CLICKS:
                        break
                        
                    # 确保按钮是实际可见的
                    if not btn.is_visible():
                        continue

                    # 2. 判断所属任务卡片是否已完成 (向上查找 8 层父节点提取文本)
                    is_completed = btn.evaluate("""(node) => {
                        let parent = node.parentElement;
                        for(let i=0; i<8; i++) {
                            if(!parent) break;
                            const text = parent.innerText || "";
                            if(text.includes('已完成') || text.includes('finish')) {
                                return true;
                            }
                            parent = parent.parentElement;
                        }
                        return false;
                    }""")

                    # 3. 物理点击
                    if not is_completed:
                        try:
                            print(f"  👉 发现未完成任务，正在执行真实的鼠标点击...")
                            # force=True 确保无视可能存在的透明遮罩层强行点击
                            btn.click(force=True)
                            clicked_count += 1
                            
                            # 【关键】真实点击通常会打开新标签页，这里必须停顿等待新页面加载并记录数据
                            time.sleep(4) 
                        except Exception as e:
                            print(f"  ❌ 点击失败: {str(e)}")
                    else:
                        skip_count += 1

                print(f"✅ [账号 {index}] 本轮成功物理点击了 {clicked_count} 个任务 (上限5个)。跳过了 {skip_count} 个已完成。")
                
                if clicked_count > 0:
                    print("⏳ 额外保持浏览器存活 10 秒，确保底层阅读接口调用完成...")
                    time.sleep(10)
                
            except Exception as e:
                print(f"❌ [账号 {index}] 运行发生异常: {str(e)}")
            finally:
                context.close()
                if index < len(account_cookies):
                    delay = random.randint(3, 8)
                    print(f"💤 账号切换中，休息 {delay} 秒...")
                    time.sleep(delay)

        browser.close()
        print("=" * 40)
        print("🎉 所有账号任务已全部执行完毕！")

if __name__ == "__main__":
    time.sleep(random.randint(1, 15))
    main()
