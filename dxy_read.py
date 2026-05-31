import os
import re
import json
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# 1. 基础配置
# ============================================================

LIST_URL = (
    "https://hao.dxy.cn/api/client/proxy/api/stats/client/session/task/activity/list"
    "?taskType=2&pageNo=1&pageSize=15&reset=true"
)

BASE_REFERER = "https://hao.dxy.cn/plus/activity?source=livesquare"
BASE_ORIGIN = "https://hao.dxy.cn"

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 可通过环境变量修改
TIMEOUT = int(os.environ.get("DXY_TIMEOUT", "20"))
MAX_CLICKS = int(os.environ.get("DXY_MAX_CLICKS", "5"))
READ_WAIT_SECONDS = int(os.environ.get("DXY_READ_WAIT_SECONDS", "6"))

# 1 = 打印详细调试日志；0 = 简洁日志
DEBUG = os.environ.get("DXY_DEBUG", "1").strip() == "1"

# 1 = 访问任务链接和文章链接；0 = 只检测 Cookie 和任务列表
ENABLE_VISIT = os.environ.get("DXY_ENABLE_VISIT", "1").strip() == "1"

# GitHub Actions 环境判断
GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"


# ============================================================
# 2. 日志工具
# ============================================================

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_info(msg: str):
    print(f"[{now_str()}] ℹ️ {msg}")


def log_ok(msg: str):
    print(f"[{now_str()}] ✅ {msg}")


def log_warn(msg: str):
    print(f"[{now_str()}] ⚠️ {msg}")


def log_error(msg: str):
    print(f"[{now_str()}] ❌ {msg}")


def gh_group_start(title: str):
    if GITHUB_ACTIONS:
        print(f"::group::{title}")


def gh_group_end():
    if GITHUB_ACTIONS:
        print("::endgroup::")


def safe_filename(text: str, max_len: int = 80) -> str:
    text = str(text)
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text)
    text = text.strip("_")
    return text[:max_len] if text else "unknown"


def mask_cookie(cookie: str) -> str:
    """
    避免日志泄露完整 Cookie。
    """
    if not cookie:
        return ""

    parts = []
    for item in cookie.split(";"):
        item = item.strip()
        if not item:
            continue

        if "=" not in item:
            parts.append("***")
            continue

        key, value = item.split("=", 1)
        value = value.strip()

        if len(value) <= 8:
            masked_value = "***"
        else:
            masked_value = value[:4] + "***" + value[-4:]

        parts.append(f"{key}={masked_value}")

    return "; ".join(parts)


def response_text_preview(response: requests.Response, max_chars: int = 1000) -> str:
    try:
        text = response.text or ""
    except Exception:
        return "<无法读取 response.text>"

    text = text.replace("\r", " ").replace("\n", " ").strip()

    if len(text) > max_chars:
        text = text[:max_chars] + " ...[已截断]"

    return text


def save_failure_log(
    account_index: int,
    name: str,
    response: Optional[requests.Response] = None,
    error: Optional[Exception] = None,
    extra: Optional[Dict[str, Any]] = None
):
    """
    保存失败日志到 logs 文件夹。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = LOG_DIR / f"account_{account_index}_{timestamp}_{safe_filename(name)}.log"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"时间: {now_str()}\n")
        f.write(f"账号: {account_index}\n")
        f.write(f"名称: {name}\n\n")

        if extra:
            f.write("额外信息:\n")
            f.write(json.dumps(extra, ensure_ascii=False, indent=2))
            f.write("\n\n")

        if response is not None:
            f.write("响应信息:\n")
            f.write(f"请求 URL: {response.request.url if response.request else ''}\n")
            f.write(f"最终 URL: {response.url}\n")
            f.write(f"状态码: {response.status_code}\n")
            f.write(f"Content-Type: {response.headers.get('Content-Type', '')}\n")
            f.write("\n响应头:\n")
            f.write(json.dumps(dict(response.headers), ensure_ascii=False, indent=2))
            f.write("\n\n")

            if response.history:
                f.write("跳转历史:\n")
                for i, h in enumerate(response.history, start=1):
                    f.write(f"[{i}] {h.status_code} -> {h.headers.get('Location', '')}\n")
                f.write("\n")

            f.write("响应正文前 5000 字:\n")
            try:
                f.write(response.text[:5000])
            except Exception:
                f.write("<无法读取响应正文>")
            f.write("\n\n")

        if error is not None:
            f.write("异常信息:\n")
            f.write(repr(error))
            f.write("\n\nTraceback:\n")
            f.write(traceback.format_exc())

    log_warn(f"失败日志已保存: {filename}")


# ============================================================
# 3. requests 会话
# ============================================================

def create_session() -> requests.Session:
    """
    创建带重试机制的 Session。
    """
    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def build_headers(cookie: str) -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": BASE_REFERER,
        "Origin": BASE_ORIGIN,
        "Connection": "keep-alive",
    }


def print_redirect_history(account_index: int, response: requests.Response, request_name: str):
    """
    打印跳转历史，排查 linkTask 是否跳到了文章页。
    """
    if not response.history:
        log_info(f"[账号 {account_index}] {request_name} 无跳转历史。")
        return

    log_info(f"[账号 {account_index}] {request_name} 跳转历史：")

    for i, h in enumerate(response.history, start=1):
        location = h.headers.get("Location", "")
        print(f"  [{i}] {h.status_code} -> {location}")

    log_info(f"[账号 {account_index}] {request_name} 最终 URL: {response.url}")


def safe_get(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    account_index: int,
    request_name: str,
    allow_redirects: bool = True
) -> Tuple[Optional[requests.Response], Optional[Exception]]:
    """
    GET 请求统一封装：
    - 打印 URL
    - 打印状态码
    - 打印跳转历史
    - 打印响应摘要
    - 失败保存日志
    """
    try:
        if DEBUG:
            log_info(f"[账号 {account_index}] 请求名称: {request_name}")
            log_info(f"[账号 {account_index}] 请求 URL: {url}")

        response = session.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=allow_redirects
        )

        log_info(
            f"[账号 {account_index}] {request_name} 状态码: "
            f"{response.status_code} | 最终 URL: {response.url}"
        )

        if response.history:
            print_redirect_history(account_index, response, request_name)

        if DEBUG:
            content_type = response.headers.get("Content-Type", "")
            log_info(f"[账号 {account_index}] {request_name} Content-Type: {content_type}")
            log_info(f"[账号 {account_index}] {request_name} 响应摘要: {response_text_preview(response)}")

        if response.status_code >= 400:
            save_failure_log(
                account_index=account_index,
                name=f"{request_name}_status_{response.status_code}",
                response=response,
                extra={"url": url}
            )

        return response, None

    except Exception as e:
        log_error(f"[账号 {account_index}] {request_name} 请求异常: {e}")

        save_failure_log(
            account_index=account_index,
            name=f"{request_name}_exception",
            error=e,
            extra={"url": url}
        )

        return None, e


# ============================================================
# 4. JSON 解析与任务状态
# ============================================================

def parse_json_response(
    response: requests.Response,
    account_index: int,
    request_name: str
) -> Optional[Dict[str, Any]]:
    try:
        return response.json()
    except Exception as e:
        log_error(f"[账号 {account_index}] {request_name} JSON 解析失败: {e}")
        save_failure_log(
            account_index=account_index,
            name=f"{request_name}_json_parse_failed",
            response=response,
            error=e
        )
        return None


def task_status_text(user_status: Any) -> str:
    if user_status == 2:
        return "已完成"
    if user_status == 1:
        return "进行中/已领取"
    if user_status == 0:
        return "未完成"
    if user_status is None:
        return "未知"
    return f"未知状态({user_status})"


def get_task_list(
    session: requests.Session,
    headers: Dict[str, str],
    account_index: int
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    获取任务列表。
    """
    response, error = safe_get(
        session=session,
        url=LIST_URL,
        headers=headers,
        account_index=account_index,
        request_name="获取任务列表",
        allow_redirects=True
    )

    if error or response is None:
        return [], None

    data = parse_json_response(response, account_index, "获取任务列表")
    if not data:
        return [], None

    results = data.get("results")

    if not isinstance(results, dict):
        log_error(f"[账号 {account_index}] 返回 JSON 中没有有效 results 字段。")
        save_failure_log(
            account_index=account_index,
            name="task_list_no_results",
            response=response,
            extra={"json": data}
        )
        return [], data

    items = results.get("items", [])

    if not isinstance(items, list):
        log_error(f"[账号 {account_index}] results.items 不是列表，接口结构可能变化。")
        save_failure_log(
            account_index=account_index,
            name="task_list_items_not_list",
            response=response,
            extra={"json": data}
        )
        return [], data

    return items, data


def validate_cookie(
    session: requests.Session,
    headers: Dict[str, str],
    account_index: int
) -> bool:
    """
    检测 Cookie 是否有效。
    """
    log_info(f"[账号 {account_index}] 开始检测 Cookie 有效性。")
    log_info(f"[账号 {account_index}] Cookie 摘要: {mask_cookie(headers.get('Cookie', ''))}")

    items, raw_data = get_task_list(session, headers, account_index)

    if raw_data is None:
        log_error(f"[账号 {account_index}] Cookie 检测失败：接口没有返回有效 JSON。")
        return False

    if "results" not in raw_data:
        log_error(f"[账号 {account_index}] Cookie 检测失败：返回中没有 results，可能 Cookie 过期。")
        return False

    results = raw_data.get("results")
    if not isinstance(results, dict):
        log_error(f"[账号 {account_index}] Cookie 检测失败：results 结构异常。")
        return False

    if "items" not in results:
        log_error(f"[账号 {account_index}] Cookie 检测失败：results 中没有 items。")
        return False

    log_ok(f"[账号 {account_index}] Cookie 检测通过，读取到任务数量: {len(items)}")
    return True


def print_task_overview(account_index: int, items: List[Dict[str, Any]]):
    """
    打印任务概览。
    """
    if not items:
        log_warn(f"[账号 {account_index}] 没有读取到任务。")
        return

    log_info(f"[账号 {account_index}] 任务概览：")

    for i, item in enumerate(items, start=1):
        task_id = item.get("id", "")
        title = item.get("title", "未知标题")
        user_status = item.get("userStatus")
        content_url = item.get("contentUrl", "")

        print(
            f"  [{i}] "
            f"ID={task_id} | "
            f"状态={task_status_text(user_status)} | "
            f"标题={title} | "
            f"contentUrl={'有' if content_url else '无'}"
        )


def check_task_success(
    session: requests.Session,
    headers: Dict[str, str],
    account_index: int,
    target_task_id: Any
) -> bool:
    """
    重新获取任务列表，检查指定任务是否完成。
    """
    items, _ = get_task_list(session, headers, account_index)

    for item in items:
        if item.get("id") == target_task_id:
            current_status = item.get("userStatus")
            log_info(
                f"[账号 {account_index}] 任务 {target_task_id} 当前状态: "
                f"{task_status_text(current_status)}"
            )
            return current_status == 2

    log_warn(f"[账号 {account_index}] 重新获取列表后没有找到任务 ID={target_task_id}")
    return False


# ============================================================
# 5. 文章 ID 提取，仅用于调试显示
# ============================================================

def extract_article_id_from_url(url: str) -> Optional[str]:
    """
    从 URL 中尽量提取文章 ID，仅用于调试显示。
    不用于伪造任何完成接口。
    """
    if not url:
        return None

    patterns = [
        r"id=(\d{10,})",
        r"articleId=(\d{10,})",
        r"/article/(\d{10,})",
        r"content/article/(\d{10,})",
        r"article%2F(\d{10,})",
    ]

    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)

    return None


def debug_article_info(account_index: int, task_id: Any, title: str, url: str):
    """
    只打印文章 ID 调试信息，不额外调用隐藏接口。
    """
    article_id = extract_article_id_from_url(url)

    if article_id:
        log_info(
            f"[账号 {account_index}] 文章 ID 提取成功："
            f"task_id={task_id} | article_id={article_id} | 标题={title}"
        )
    else:
        log_warn(
            f"[账号 {account_index}] 未能从 URL 中提取文章 ID。"
            f"task_id={task_id} | 标题={title}"
        )


# ============================================================
# 6. 执行任务访问与校验
# ============================================================

def visit_task(
    session: requests.Session,
    headers: Dict[str, str],
    account_index: int,
    task_id: Any,
    title: str,
    content_url: Optional[str]
) -> bool:
    """
    访问任务跳转链接和文章链接，然后重新检查任务状态。
    """
    task_url = f"https://hao.dxy.cn/plus/activity/linkTask/{task_id}"

    log_info(f"[账号 {account_index}] 准备访问任务：{title}")
    log_info(f"[账号 {account_index}] 任务跳转链接: {task_url}")

    # 第一步：访问任务跳转链接
    link_response, link_error = safe_get(
        session=session,
        url=task_url,
        headers=headers,
        account_index=account_index,
        request_name=f"访问任务跳转链接_{task_id}",
        allow_redirects=True
    )

    if link_error or link_response is None:
        log_error(f"[账号 {account_index}] 访问任务跳转链接失败：{title}")
        return False

    # 打印 linkTask 最终 URL 中可能包含的文章 ID
    debug_article_info(
        account_index=account_index,
        task_id=task_id,
        title=title,
        url=link_response.url
    )

    # 第二步：访问 contentUrl
    if content_url:
        log_info(f"[账号 {account_index}] 任务 contentUrl: {content_url}")

        article_headers = headers.copy()
        article_headers["Referer"] = task_url
        article_headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        )

        article_response, article_error = safe_get(
            session=session,
            url=content_url,
            headers=article_headers,
            account_index=account_index,
            request_name=f"访问文章内容_{task_id}",
            allow_redirects=True
        )

        if article_error or article_response is None:
            log_warn(f"[账号 {account_index}] 文章 contentUrl 访问失败，但继续校验任务状态。")
        else:
            debug_article_info(
                account_index=account_index,
                task_id=task_id,
                title=title,
                url=article_response.url
            )
    else:
        log_warn(f"[账号 {account_index}] 当前任务没有 contentUrl：{title}")

    # 第三步：等待后重新拉取任务列表校验
    log_info(f"[账号 {account_index}] 等待 {READ_WAIT_SECONDS} 秒后重新校验任务状态。")
    time.sleep(READ_WAIT_SECONDS)

    return check_task_success(
        session=session,
        headers=headers,
        account_index=account_index,
        target_task_id=task_id
    )


def run_account_tasks(cookie: str, account_index: int):
    """
    执行单个账号。
    """
    gh_group_start(f"账号 {account_index}")

    print()
    print(f"================ 开始执行 [账号 {account_index}] ================")

    session = create_session()
    headers = build_headers(cookie)

    try:
        # Cookie 检测
        if not validate_cookie(session, headers, account_index):
            log_error(f"[账号 {account_index}] Cookie 无效，跳过该账号。")
            return

        # 获取任务列表
        items, _ = get_task_list(session, headers, account_index)

        if not items:
            log_warn(f"[账号 {account_index}] 未找到任务，可能今日无任务或 Cookie 权限异常。")
            return

        log_ok(f"[账号 {account_index}] 成功获取任务列表，共 {len(items)} 个任务。")
        print_task_overview(account_index, items)

        if not ENABLE_VISIT:
            log_warn(
                f"[账号 {account_index}] 当前 DXY_ENABLE_VISIT=0，"
                f"只检测 Cookie 和任务列表，不访问任务链接。"
            )
            return

        success_count = 0
        attempt_count = 0

        for index, item in enumerate(items, start=1):
            if success_count >= MAX_CLICKS:
                log_warn(
                    f"[账号 {account_index}] 已达到最大成功限制 MAX_CLICKS={MAX_CLICKS}，停止。"
                )
                break

            task_id = item.get("id")
            title = item.get("title", "未知标题")
            user_status = item.get("userStatus")
            content_url = item.get("contentUrl")

            if not task_id:
                log_warn(f"[账号 {account_index}] 第 {index} 个任务缺少 id，跳过。")
                continue

            if user_status == 2:
                log_info(f"[{index}/{len(items)}] 跳过已完成任务：{title}")
                continue

            attempt_count += 1

            print()
            log_info(f"[{index}/{len(items)}] 开始尝试任务：{title}")
            log_info(
                f"[账号 {account_index}] "
                f"task_id={task_id} | userStatus={user_status} | "
                f"contentUrl={'有' if content_url else '无'}"
            )

            try:
                is_success = visit_task(
                    session=session,
                    headers=headers,
                    account_index=account_index,
                    task_id=task_id,
                    title=title,
                    content_url=content_url
                )

                if is_success:
                    log_ok(f"[账号 {account_index}] 校验成功，任务已完成：{title}")
                    success_count += 1
                else:
                    log_warn(f"[账号 {account_index}] 校验失败，任务状态未变为已完成：{title}")
                    save_failure_log(
                        account_index=account_index,
                        name=f"task_not_completed_{task_id}",
                        extra={
                            "task_id": task_id,
                            "title": title,
                            "userStatus_before": user_status,
                            "contentUrl": content_url,
                            "note": (
                                "任务链接和文章链接已访问，但重新获取任务列表后，"
                                "userStatus 未变为 2。"
                            )
                        }
                    )

            except Exception as e:
                log_error(f"[账号 {account_index}] 执行任务异常：{title} | {e}")
                save_failure_log(
                    account_index=account_index,
                    name=f"task_exception_{task_id}",
                    error=e,
                    extra={
                        "task_id": task_id,
                        "title": title,
                        "userStatus": user_status,
                        "contentUrl": content_url
                    }
                )

            # 任务之间间隔，避免连续请求太快
            time.sleep(2)

        print()
        log_ok(
            f"[账号 {account_index}] 执行结束。"
            f"尝试任务数：{attempt_count}，真实完成数：{success_count}。"
        )

    except Exception as e:
        log_error(f"[账号 {account_index}] 账号执行发生严重错误：{e}")
        save_failure_log(
            account_index=account_index,
            name="account_fatal_error",
            error=e
        )

    finally:
        try:
            session.close()
        except Exception:
            pass

        gh_group_end()


# ============================================================
# 7. 主程序
# ============================================================

def load_cookies_from_env() -> List[str]:
    """
    从环境变量 DXY_COOKIE 中读取 Cookie。
    多账号用换行分隔。
    """
    cookie_env = os.environ.get("DXY_COOKIE", "")

    if not cookie_env.strip():
        return []

    cookies = []

    for line in cookie_env.splitlines():
        line = line.strip()
        if line:
            cookies.append(line)

    return cookies


def print_runtime_info():
    print("========== 运行参数 ==========")
    print(f"当前时间: {now_str()}")
    print(f"TIMEOUT: {TIMEOUT}")
    print(f"MAX_CLICKS: {MAX_CLICKS}")
    print(f"READ_WAIT_SECONDS: {READ_WAIT_SECONDS}")
    print(f"DEBUG: {DEBUG}")
    print(f"ENABLE_VISIT: {ENABLE_VISIT}")
    print(f"GITHUB_ACTIONS: {GITHUB_ACTIONS}")
    print(f"LOG_DIR: {LOG_DIR.resolve()}")
    print("==============================")
    print()


def main():
    print_runtime_info()

    cookies = load_cookies_from_env()

    if not cookies:
        log_error("未找到 DXY_COOKIE 环境变量。")
        log_info("本地运行示例：")
        log_info("Windows CMD:")
        print('set DXY_COOKIE=你的Cookie')
        print('python dxy_task_debug_full.py')
        print()
        log_info("PowerShell:")
        print('$env:DXY_COOKIE="你的Cookie"')
        print('python dxy_task_debug_full.py')
        return

    log_ok(f"共读取到 {len(cookies)} 个账号 Cookie。")

    for idx, cookie in enumerate(cookies, start=1):
        run_account_tasks(cookie, idx)

        if idx < len(cookies):
            log_info("账号之间间隔 5 秒。")
            time.sleep(5)

    log_ok("全部账号执行结束。")


if __name__ == "__main__":
    try:
        main()
    finally:
        # 本地双击运行时防止窗口闪退；GitHub Actions 中不暂停
        if not GITHUB_ACTIONS:
            input("按回车键退出...")
