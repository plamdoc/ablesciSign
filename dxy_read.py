#!/usr/bin/env python3
# coding=utf-8

import os
import time
import random

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("【错误】缺少 playwright 库。请先在终端运行: ")
    print("1. pip install playwright")
    print("2. playwright install chromium")
    exit(1)


def parse_cookies(cookie_str: str, domain: str = ".dxy.cn") -> list:
    """将原生字符串形式的 Cookie 转换为 Playwright 需要的字典列表格式"""
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
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE，请检查 GitHub Secrets 配置！\033[0m")
        return

    # 按换行符分割，支持多个账号
    account_cookies = [c.strip() for c in cookie_env.split('\n') if c.strip()]
    print("=" * 40)
    print(f"🎉 成功解析到 {len(account_cookies)} 个账号配置，准备开始执行...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # 循环执行每个账号
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
                print(f"🌐 [账号 {index}] 正在打开页面: {url}")
                page.goto(url, wait_until="networkidle", timeout=45000)
                
                print(f"⏳ [账号 {index}] 等待动态任务列表渲染 (5秒)...")
                time.sleep(5) 

                # 核心 JS 扫描和点击逻辑 (已添加最多点击 5 次的限制)
                js_logic = """
                () => {
                    const allBtnNodes = [];
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.nodeValue.trim() === '去阅读') {
                            allBtnNodes.push(node.parentElement);
                        }
                    }

                    if (allBtnNodes.length === 0) return { clicked: 0, skipped: 0, msg: "页面未找到任何“去阅读”按钮" };

                    let clickedCount = 0;
                    let skipCount = 0;
                    const MAX_CLICKS = 5; // 【新增】设置单次最大点击数量

                    // 使用 for...of 循环代替 forEach，以便可以使用 break 中断循环
                    for (let btnEl of allBtnNodes) {
                        let taskCard = btnEl;
                        let parent = btnEl.parentElement;

                        while(parent) {
                            let containsCount = 0;
                            for(let b of allBtnNodes) {
                                if (parent.contains(b)) containsCount++;
                            }
                            if (containsCount > 1) break;
                            taskCard = parent;
                            parent = parent.parentElement;
                            if (taskCard.tagName === 'BODY' || taskCard.tagName === 'HTML') break;
                        }

                        const htmlStr = taskCard.innerHTML.toLowerCase();
                        const textStr = taskCard.textContent || '';
                        const isCompleted = textStr.includes('已完成') || htmlStr.includes('已完成') || htmlStr.includes('finish');

                        if (!isCompleted) {
                            // 【新增】如果已经点击了 5 个，直接跳出循环，不再点剩下的
                            if (clickedCount >= MAX_CLICKS) {
                                break; 
                            }
                            btnEl.click();
                            clickedCount++;
                        } else {
                            skipCount++;
                        }
                    }

                    return { clicked: clickedCount, skipped: skipCount, msg: "扫描完成" };
                }
                """
                
                result = page.evaluate(js_logic)
                print(f"📋 [账号 {index}] 扫描结果: {result['msg']}")
                print(f"✅ [账号 {index}] 成功点击了 {result['clicked']} 个未完成任务 (单次上限5个)，智能跳过了 {result['skipped']} 个已完成任务。")
                
                if result['clicked'] > 0:
                    print(f"⏳ [账号 {index}] 正在保持浏览器存活 15 秒，确保阅读数据正常上报...")
                    time.sleep(15)
                
            except Exception as e:
                print(f"❌ [账号 {index}] 运行中发生异常错误: {str(e)}")
            finally:
                context.close()
                if index < len(account_cookies):
                    delay = random.randint(3, 8)
                    print(f"💤 账号切换中，防风控休息 {delay} 秒...")
                    time.sleep(delay)

        browser.close()
        print("=" * 40)
        print("🎉 所有账号任务已全部执行完毕！")

if __name__ == "__main__":
    time.sleep(random.randint(1, 15))
    main()
