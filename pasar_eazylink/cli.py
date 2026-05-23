import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import CONFIG_FILE, TG_ENV, load_config, save_config
from .mapping import add_token, delete_token, delete_user, map_path, show_mapping
from .pasar_api import create_user_from_template, list_templates, login as pasar_login, test_api as test_pasar
from .shlink_api import (
    delete as shlink_delete,
    item_code,
    item_long_url,
    item_short_url,
    patch as shlink_patch,
    select as select_shortlink,
    show_list as show_shortlinks,
    test_api as test_shlink,
    upsert as shlink_upsert,
)
from .telegram import sync_env as sync_tg_env, test as test_tg
from .utils import (
    extract_token,
    input_nonempty,
    make_long_url,
    mask,
    prompt_slug,
    short_token,
    validate_slug,
    validate_username,
)

GREEN = "\033[92m"
RESET = "\033[0m"


def color_enabled() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    term = os.getenv("TERM", "").strip().lower()
    if term in {"", "dumb"}:
        return False
    return True


def green(text: str) -> str:
    if color_enabled():
        return f"{GREEN}{text}{RESET}"
    return text


def normalize_menu_opt(raw: str) -> str:
    opt = raw.strip().lower()
    if opt in {"b", "back", "返回", "q", "quit", "exit", "退出"}:
        return "0"
    return opt


def menu_block(title: str, items: list[tuple[str, str]]):
    rows = [title, *[f"{k} {v}" for k, v in items]]
    width = max(len(row) for row in rows) + 2
    line = "=" * width
    print()
    print(green(line))
    print(green(title))
    print(green(line))
    for key, label in items:
        print(green(f"{key:<2} {label}"))
    print(green(line))


def prompt_menu() -> str:
    return normalize_menu_opt(input(green("请输入选项: ")))


def config_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def run_command(cmd: list[str]):
    print()
    print("$ " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError as exc:
        print(f"命令不可用：{exc}")
    except Exception as exc:
        print(f"命令执行失败：{exc}")


def save_bool(cfg: dict, key: str, current: str, label: str):
    value = input(f"{label}（true/false） [当前: {current}]: ").strip().lower()
    if value in {"true", "false"}:
        cfg[key] = value
        save_config(cfg)
    elif value:
        print("请输入 true 或 false。")


def create_link(cfg: dict):
    print("\n=== 新增链接 ===")
    templates = list_templates(cfg)
    if templates is None:
        return

    username = input_nonempty("用户名: ")
    if not validate_username(username):
        print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
        return

    template_id = input_nonempty("模板 ID: ")
    if not template_id.isdigit():
        print("模板 ID 必须是数字。")
        return

    note = input("备注，可留空: ").strip()
    slug = prompt_slug(username)

    long_url = create_user_from_template(cfg, username, int(template_id), note)
    if not long_url:
        return

    token = extract_token(long_url)
    if not token:
        print(f"无法从订阅链接提取 token：{long_url}")
        return

    if config_bool(cfg.get("EAZYLINK_WRITE_LEGACY_MAPPING", "false")):
        add_token(cfg, token, username)
    else:
        print("Legacy Mapping 写入已关闭。")

    if not shlink_upsert(cfg, slug, long_url):
        return

    print("\n=== 新增完成 ===")
    print(f"用户：{username}")
    print(f"短链接：{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}")
    print(f"长链接：{long_url}")
    print(f"token：{short_token(token)}")


def update_link(cfg: dict):
    print("\n=== 更新链接 ===")

    username = input_nonempty("用户名: ")
    if not validate_username(username):
        print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
        return

    input_url = input_nonempty("新的订阅长链接或 token: ")
    token = extract_token(input_url)
    if not token:
        print("没有识别到 token。")
        return

    long_url = make_long_url(token, cfg)

    append_mapping = input("是否追加 token 到 mapping？输入 yes 继续: ").strip().lower()
    if append_mapping == "yes":
        add_token(cfg, token, username)

    print("\n选择要覆盖的短链接。")
    matches = show_shortlinks(cfg, username)

    selected = None
    if matches:
        value = input("选择序号覆盖；输入 0 或回车新建短链接: ").strip()
        if value and value.isdigit() and 1 <= int(value) <= len(matches):
            selected = matches[int(value) - 1]

    if selected:
        code = item_code(selected)
        status, _data, raw = shlink_patch(cfg, code, long_url)

        if 200 <= status < 300:
            short_url = item_short_url(selected, cfg)
            print(f"短链接已覆盖：{short_url}")
        else:
            print(f"短链接覆盖失败，HTTP {status}")
            print(raw)
            return
    else:
        slug = prompt_slug(username)
        if not shlink_upsert(cfg, slug, long_url):
            return
        short_url = f"{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}"

    print("\n=== 更新完成 ===")
    print(f"用户：{username}")
    print(f"短链接：{short_url}")
    print(f"长链接：{long_url}")
    print(f"token：{short_token(token)}")


def delete_link(cfg: dict):
    print("\n=== 删除链接 ===")
    username = input_nonempty("用户名: ")
    if not validate_username(username):
        print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
        return

    show_mapping(cfg, username)
    matches = show_shortlinks(cfg, username)

    if matches:
        confirm_short = input("是否删除匹配的短链接？输入 yes 继续: ").strip().lower()
        if confirm_short == "yes":
            for item in matches:
                status, _data, raw = shlink_delete(cfg, item_code(item))
                if status in (200, 202, 204, 404):
                    print(f"已删除/跳过：{item_short_url(item, cfg)}")
                else:
                    print(f"删除失败：{item_short_url(item, cfg)} HTTP {status}")
                    if raw:
                        print(raw)

    confirm_map = input("是否删除该用户 legacy mapping？输入 yes 继续: ").strip().lower()
    if confirm_map == "yes":
        delete_user(cfg, username)

    print("删除完成。说明：默认不删除 PasarGuard 面板用户。")


def view_links(cfg: dict):
    query = input("关键词过滤，留空查看全部: ").strip()
    show_shortlinks(cfg, query)


def manage_shortlink_modify(cfg: dict):
    item = select_shortlink(cfg)
    if not item:
        return

    old_code = item_code(item)
    old_long = item_long_url(item)

    print(f"\n当前 shortCode：{old_code}")
    print(f"当前短链接：{item_short_url(item, cfg)}")
    print(f"当前目标：{old_long}")

    new_slug = input("新的 shortCode/slug，留空不修改: ").strip()
    if new_slug:
        if not validate_slug(new_slug):
            print("slug 格式无效。")
            return
    else:
        new_slug = old_code

    new_target = input("新的目标长链接或 token，留空不修改: ").strip()
    if new_target:
        token = extract_token(new_target)
        if token:
            new_long = make_long_url(token, cfg)
        else:
            new_long = new_target
            token = ""
    else:
        new_long = old_long
        token = extract_token(old_long)

    if new_slug == old_code and new_long == old_long:
        print("没有修改。")
        return

    if new_slug != old_code:
        if not shlink_upsert(cfg, new_slug, new_long):
            return

        status, _data, raw = shlink_delete(cfg, old_code)
        if status not in (200, 202, 204, 404):
            print(f"旧短链删除失败，HTTP {status}")
            print(raw)
            return
        final_short = f"{cfg['SHORT_DOMAIN'].rstrip('/')}/{new_slug}"
    else:
        status, _data, raw = shlink_patch(cfg, old_code, new_long)
        if not (200 <= status < 300):
            print(f"短链修改失败，HTTP {status}")
            print(raw)
            return
        final_short = item_short_url(item, cfg)

    if token:
        map_user = input("如需把新 token 写入 mapping，请输入用户名；留空跳过: ").strip()
        if map_user:
            if validate_username(map_user):
                add_token(cfg, token, map_user)
            else:
                print("用户名格式无效，已跳过 mapping 写入。")

    print("\n=== 修改完成 ===")
    print(f"短链接：{final_short}")
    print(f"目标：{new_long}")


def manage_shortlink_delete(cfg: dict):
    item = select_shortlink(cfg)
    if not item:
        return

    code = item_code(item)
    short_url = item_short_url(item, cfg)
    long_url = item_long_url(item)

    print(f"\n准备删除：{short_url}")
    print(f"目标：{long_url}")

    confirm = input("确认删除这个短链接？输入 yes 继续: ").strip().lower()
    if confirm != "yes":
        print("已取消。")
        return

    status, _data, raw = shlink_delete(cfg, code)
    if status in (200, 202, 204, 404):
        print("短链接已删除。")
    else:
        print(f"删除失败，HTTP {status}")
        print(raw)


def shortlink_manage_menu(cfg: dict):
    items = [
        ("1", "修改"),
        ("2", "删除"),
        ("3", "列表"),
        ("0", "返回"),
    ]
    while True:
        menu_block("=== 管理短链 ===", items)
        opt = prompt_menu()

        if opt == "1":
            manage_shortlink_modify(cfg)
        elif opt == "2":
            manage_shortlink_delete(cfg)
        elif opt == "3":
            query = input("关键词过滤，留空查看全部: ").strip()
            show_shortlinks(cfg, query)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def mapping_menu(cfg: dict):
    items = [
        ("1", "查看"),
        ("2", "添加"),
        ("3", "删除用户"),
        ("4", "删除Token"),
        ("0", "返回"),
    ]
    while True:
        menu_block("=== Mapping ===", items)
        opt = prompt_menu()

        if opt == "1":
            query = input("关键词过滤，留空查看全部: ").strip()
            show_mapping(cfg, query)
        elif opt == "2":
            token = input_nonempty("token: ")
            username = input_nonempty("用户名: ")
            if not validate_username(username):
                print("用户名格式无效。")
                continue
            add_token(cfg, token, username)
        elif opt == "3":
            username = input_nonempty("用户名: ")
            if not validate_username(username):
                print("用户名格式无效。")
                continue
            delete_user(cfg, username)
        elif opt == "4":
            token = input_nonempty("token: ")
            delete_token(cfg, token)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def db_monitor_menu():
    items = [
        ("1", "测试"),
        ("2", "发送测试"),
        ("3", "启动"),
        ("4", "停止"),
        ("5", "重启"),
        ("6", "状态"),
        ("7", "日志"),
        ("0", "返回"),
    ]
    while True:
        menu_block("=== DB监控 ===", items)
        opt = prompt_menu()

        if opt == "1":
            run_command(["pasar", "monitor-db", "--test"])
        elif opt == "2":
            run_command(["pasar", "monitor-db", "--send-test"])
        elif opt == "3":
            run_command(["systemctl", "enable", "--now", "sub-notify-db.service"])
        elif opt == "4":
            run_command(["systemctl", "disable", "--now", "sub-notify-db.service"])
        elif opt == "5":
            run_command(["systemctl", "restart", "sub-notify-db.service"])
        elif opt == "6":
            run_command(["systemctl", "status", "sub-notify-db.service", "--no-pager", "-l"])
        elif opt == "7":
            run_command(["journalctl", "-u", "sub-notify-db.service", "-n", "80", "--no-pager"])
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def log_monitor_menu(cfg: dict):
    items = [
        ("1", "启动"),
        ("2", "停止"),
        ("3", "重启"),
        ("4", "状态"),
        ("5", "日志"),
        ("6", "Mapping"),
        ("7", "检查配置"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== 日志监控 ===", items)
        opt = prompt_menu()

        if opt == "1":
            run_command(["systemctl", "enable", "--now", "sub-notify.service"])
        elif opt == "2":
            run_command(["systemctl", "disable", "--now", "sub-notify.service"])
        elif opt == "3":
            run_command(["systemctl", "restart", "sub-notify.service"])
        elif opt == "4":
            run_command(["systemctl", "status", "sub-notify.service", "--no-pager", "-l"])
        elif opt == "5":
            run_command(["journalctl", "-u", "sub-notify.service", "-n", "80", "--no-pager"])
        elif opt == "6":
            mapping_menu(cfg)
        elif opt == "7":
            run_command(["/usr/local/bin/sub-notify.sh", "--check-config"])
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def monitor_menu(cfg: dict):
    items = [
        ("1", "DB监控"),
        ("2", "日志监控"),
        ("3", "状态总览"),
        ("4", "停止全部"),
        ("0", "返回"),
    ]
    while True:
        menu_block("=== 订阅监控 ===", items)
        opt = prompt_menu()

        if opt == "1":
            db_monitor_menu()
        elif opt == "2":
            log_monitor_menu(cfg)
        elif opt == "3":
            run_command(["systemctl", "status", "sub-notify-db.service", "sub-notify.service", "--no-pager", "-l"])
        elif opt == "4":
            run_command(["systemctl", "disable", "--now", "sub-notify-db.service", "sub-notify.service"])
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def show_config(cfg: dict):
    print("\n=== 当前配置 ===")
    print(f"Pasar 面板：{cfg['PASAR_PANEL_HOST']}:{cfg['PASAR_PANEL_PORT']}")
    print(f"Shlink API：{cfg['SHLINK_API_BASE']}")
    print(f"短链域名：{cfg['SHORT_DOMAIN']}")
    print(f"订阅地址：{cfg['SUB_BASE_URL']}")
    print(f"DB 路径：{cfg['PASARGUARD_DB_PATH']}")
    print(f"Nginx 日志：{cfg['NGINX_ACCESS_LOG']}")
    print(f"DB轮询：{cfg['DB_MONITOR_POLL_SECONDS']}")
    print(f"去重时间：{cfg['DB_MONITOR_DEDUP_SECONDS']}")
    print(f"补全真实IP：{cfg['DB_MONITOR_LOOKUP_NGINX_IP']}")
    print(f"Legacy Mapping 写入：{cfg['EAZYLINK_WRITE_LEGACY_MAPPING']}")
    print(f"TG Bot Token：{mask(cfg['TG_BOT_TOKEN'])}")
    print(f"TG Chat ID：{mask(cfg['TG_CHAT_ID'])}")
    print(f"TG Thread ID：{mask(cfg['TG_THREAD_ID'])}")


def settings_pasar(cfg: dict):
    items = [
        ("1", "面板地址"),
        ("2", "面板端口"),
        ("3", "登录/更新Token"),
        ("4", "测试API"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== Pasar ===", items)
        opt = prompt_menu()

        if opt == "1":
            value = input(f"面板地址 [当前: {cfg['PASAR_PANEL_HOST']}]: ").strip()
            if value:
                cfg["PASAR_PANEL_HOST"] = value.rstrip("/")
                save_config(cfg)
        elif opt == "2":
            value = input(f"面板端口 [当前: {cfg['PASAR_PANEL_PORT']}]: ").strip()
            if value:
                cfg["PASAR_PANEL_PORT"] = value
                save_config(cfg)
        elif opt == "3":
            pasar_login(cfg)
        elif opt == "4":
            test_pasar(cfg)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def settings_shlink(cfg: dict):
    items = [
        ("1", "API地址"),
        ("2", "API Key"),
        ("3", "短链域名"),
        ("4", "测试API"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== Shlink ===", items)
        opt = prompt_menu()

        if opt == "1":
            value = input(f"API地址 [当前: {cfg['SHLINK_API_BASE']}]: ").strip()
            if value:
                cfg["SHLINK_API_BASE"] = value.rstrip("/")
                save_config(cfg)
        elif opt == "2":
            value = input("API Key: ").strip()
            if value:
                cfg["SHLINK_API_KEY"] = value
                save_config(cfg)
        elif opt == "3":
            value = input(f"短链域名 [当前: {cfg['SHORT_DOMAIN']}]: ").strip()
            if value:
                cfg["SHORT_DOMAIN"] = value.rstrip("/")
                if cfg.get("SHLINK_API_BASE", "").endswith("/rest/v3"):
                    cfg["SHLINK_API_BASE"] = f"{value.rstrip('/')}/rest/v3"
                save_config(cfg)
        elif opt == "4":
            test_shlink(cfg)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def settings_telegram(cfg: dict):
    items = [
        ("1", "Bot Token"),
        ("2", "Chat ID"),
        ("3", "Thread ID"),
        ("4", "发送测试"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== Telegram ===", items)
        opt = prompt_menu()

        if opt == "1":
            value = input("Bot Token: ").strip()
            if value:
                cfg["TG_BOT_TOKEN"] = value
                save_config(cfg)
                sync_tg_env(cfg)
        elif opt == "2":
            value = input("Chat ID: ").strip()
            if value:
                cfg["TG_CHAT_ID"] = value
                save_config(cfg)
                sync_tg_env(cfg)
        elif opt == "3":
            value = input("Thread ID，可留空: ").strip()
            cfg["TG_THREAD_ID"] = value
            save_config(cfg)
            sync_tg_env(cfg)
        elif opt == "4":
            test_tg(cfg)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def settings_monitor(cfg: dict):
    items = [
        ("1", "DB路径"),
        ("2", "Nginx日志路径"),
        ("3", "轮询间隔"),
        ("4", "去重时间"),
        ("5", "是否补全真实IP"),
        ("6", "是否写Legacy Mapping"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== 订阅监控 ===", items)
        opt = prompt_menu()

        if opt == "1":
            value = input(f"DB路径 [当前: {cfg['PASARGUARD_DB_PATH']}]: ").strip()
            if value:
                cfg["PASARGUARD_DB_PATH"] = value
                save_config(cfg)
        elif opt == "2":
            value = input(f"Nginx日志路径 [当前: {cfg['NGINX_ACCESS_LOG']}]: ").strip()
            if value:
                cfg["NGINX_ACCESS_LOG"] = value
                cfg["LOG_MONITOR_ACCESS_LOG"] = value
                save_config(cfg)
        elif opt == "3":
            value = input(f"轮询间隔秒数 [当前: {cfg['DB_MONITOR_POLL_SECONDS']}]: ").strip()
            if value:
                cfg["DB_MONITOR_POLL_SECONDS"] = value
                cfg["SUB_NOTIFY_POLL_SECONDS"] = value
                save_config(cfg)
        elif opt == "4":
            value = input(f"去重时间秒数 [当前: {cfg['DB_MONITOR_DEDUP_SECONDS']}]: ").strip()
            if value:
                cfg["DB_MONITOR_DEDUP_SECONDS"] = value
                save_config(cfg)
        elif opt == "5":
            save_bool(cfg, "DB_MONITOR_LOOKUP_NGINX_IP", cfg["DB_MONITOR_LOOKUP_NGINX_IP"], "是否补全真实IP")
        elif opt == "6":
            save_bool(
                cfg,
                "EAZYLINK_WRITE_LEGACY_MAPPING",
                cfg["EAZYLINK_WRITE_LEGACY_MAPPING"],
                "是否写Legacy Mapping",
            )
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def settings_paths(cfg: dict):
    items = [
        ("1", "配置文件路径"),
        ("2", "Mapping路径"),
        ("3", "状态文件路径"),
        ("4", "查看安装路径"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== 路径 ===", items)
        opt = prompt_menu()

        if opt == "1":
            print(f"主配置: {CONFIG_FILE}")
            print(f"兼容配置: {TG_ENV}")
        elif opt == "2":
            print(f"Mapping: {map_path(cfg)}")
        elif opt == "3":
            print(f"DB状态: {cfg['DB_MONITOR_STATE_FILE']}")
            print("日志状态: /var/lib/pasar-eazylink/log-monitor.state")
        elif opt == "4":
            print("安装路径: /opt/pasar-eazylink")
            print("命令路径: /usr/local/bin/pasar")
            print("日志监控脚本: /usr/local/bin/sub-notify.sh")
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def settings_menu(cfg: dict):
    items = [
        ("1", "Pasar"),
        ("2", "Shlink"),
        ("3", "Telegram"),
        ("4", "订阅监控"),
        ("5", "路径"),
        ("6", "查看配置"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== 设置 ===", items)
        opt = prompt_menu()

        if opt == "1":
            settings_pasar(cfg)
        elif opt == "2":
            settings_shlink(cfg)
        elif opt == "3":
            settings_telegram(cfg)
        elif opt == "4":
            settings_monitor(cfg)
        elif opt == "5":
            settings_paths(cfg)
        elif opt == "6":
            show_config(cfg)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def main_menu():
    items = [
        ("1", "新增链接"),
        ("2", "更新链接"),
        ("3", "删除链接"),
        ("4", "查看链接"),
        ("5", "管理短链"),
        ("6", "订阅监控"),
        ("7", "设置"),
        ("0", "退出"),
    ]
    while True:
        cfg = load_config()
        menu_block("=== 订阅监控与短链接管理 ===", items)
        opt = prompt_menu()

        if opt == "1":
            create_link(cfg)
        elif opt == "2":
            update_link(cfg)
        elif opt == "3":
            delete_link(cfg)
        elif opt == "4":
            view_links(cfg)
        elif opt == "5":
            shortlink_manage_menu(cfg)
        elif opt == "6":
            monitor_menu(cfg)
        elif opt == "7":
            settings_menu(cfg)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def main(argv: list[str] | None = None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] == "easylink":
        main_menu()
    else:
        print("Usage: pasar easylink")
        sys.exit(1)
