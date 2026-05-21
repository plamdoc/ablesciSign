def main():
    # 从 GitHub Secrets 中读取环境变量
    cookie_env = os.environ.get('DXY_COOKIE', '')
    if not cookie_env:
        print("\033[31m[错误] 未找到环境变量 DXY_COOKIE，请检查 GitHub Secrets 配置！\033[0m")
        return

    # 【核心改动 1】按换行符分割环境变量，提取出多个账号的 Cookie
    account_cookies = [c.strip() for c in cookie_env.split('\n') if c.strip()]
    print("=" * 40)
    print(f"🎉 成功解析到 {len(account_cookies)} 个账号配置，准备开始执行...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # 【核心改动 2】循环遍历每一个账号
        for index, current_cookie in enumerate(account_cookies, start=1):
            print("-" * 40)
            print(f"🚀 开始执行 账号 [{index}] ...")
            
            # 为每个账号创建一个独立的无痕浏览器上下文，防止串号
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
            
            # 注入当前账号的 Cookie
            context.add_cookies(parse_cookies(current_cookie))
            page = context.new_page()
            url = "https://hao.dxy.cn/plus/activity?source=livesquare"
            
            try:
                print(f"🌐 [账号 {index}] 正在打开页面...")
                page.goto(url, wait_until="networkidle", timeout=45000)
                
                print(f"⏳ [账号 {index}] 等待动态任务列表渲染...")
                time.sleep(5) 

                # 核心 JS 点击逻辑保持不变
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

                    allBtnNodes.forEach(btnEl => {
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
                            btnEl.click();
                            clickedCount++;
                        } else {
                            skipCount++;
                        }
                    });

                    return { clicked: clickedCount, skipped: skipCount, msg: "扫描完成" };
                }
                """
                
                result = page.evaluate(js_logic)
                print(f"✅ [账号 {index}] 成功点击 {result['clicked']} 个新任务，跳过 {result['skipped']} 个已完成任务。")
                
                if result['clicked'] > 0:
                    print(f"⏳ [账号 {index}] 保持存活 15 秒，确保积分发放...")
                    time.sleep(15)
                
            except Exception as e:
                print(f"❌ [账号 {index}] 运行中发生异常错误: {str(e)}")
            finally:
                # 执行完毕后，关闭当前账号的上下文，并随机休眠几秒再执行下一个账号
                context.close()
                if index < len(account_cookies):
                    delay = random.randint(3, 8)
                    print(f"💤 账号切换中，随机休息 {delay} 秒...")
                    time.sleep(delay)

        browser.close()
        print("=" * 40)
        print("🎉 所有账号任务已全部执行完毕！")
