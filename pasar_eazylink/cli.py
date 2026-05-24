import os
import subprocess
import sys

from . import __version__
from .colors import colors
from .config import load_config, save_config
from .pasar_api import create_user_from_template, list_templates
from .shlink_api import (
    show_list,
    item_code,
    item_long_url,
    create as shlink_create,
    patch as shlink_patch,
    delete as shlink_delete,
    upsert as shlink_upsert,
)
from .utils import validate_username, validate_slug, extract_token, make_long_url, prompt_slug


def is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def clear_screen():
    if os.environ.get("NO_CLEAR"):
        return
    if not is_tty():
        return
    os.system("clear")


def pause(text: str = "按回车继续..."):
    input(colors.menu(text))


def menu(title, items, main: bool = False, clear: bool = True):
    if clear:
        clear_screen()

    if main:
        # Match requested visual style.
        # Top/bottom frame width intentionally follows the user's example.
        line = "━" * 34
        print(colors.menu(f"┏{line}┓"))
        print(colors.menu(f"┃      {title}      "))
        print(colors.menu(f"┗{line}┛"))

        for k, v in items:
            print(f"  {k}  {v}")

        print(colors.menu("─" * 36))
        return

    print(colors.menu(title))
    print(colors.menu("─" * 28))

    for k, v in items:
        print(f" {str(k).rjust(2)}  {v}")

    print(colors.menu("─" * 28))


def ask():
    # Empty input equals return/back.
    return (input(colors.menu("请输入选项: ")).strip().lower() or "0")


def yesno(prompt):
    # Empty input equals no.
    return (input(prompt).strip().lower() or "no") == "yes"


def prompt_value(label: str, current: str | None = None):
    suffix = f" [当前: {current}]" if current else ""
    value = input(f"输入{label}{suffix}(回车取消): ").strip()
    return value or None


def create_link(cfg):
    clear_screen()

    list_templates(cfg)

    u = input("用户名(回车取消): ").strip()
    if not u or u == "0":
        print("已取消")
        return

    if not validate_username(u):
        print(colors.err("用户名格式无效"))
        return

    tid = input("模板ID(回车取消): ").strip()
    if not tid or tid == "0":
        print("已取消")
        return

    if not tid.isdigit():
        print(colors.err("模板ID必须是数字"))
        return

    remark = input("备注(回车留空): ").strip()
    long_url = create_user_from_template(cfg, u, int(tid), remark)

    if not long_url:
        return

    slug = prompt_slug(u)

    if shlink_upsert(cfg, slug, long_url):
        print(
            colors.ok(
                f"[OK] 创建完成\n"
                f"用户：{u}\n"
                f"长链：{long_url}\n"
                f"短链：{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}"
            )
        )


def manage_short(cfg):
    while True:
        clear_screen()
        items = show_list(cfg, "")

        print()
        print(colors.menu("管理短链"))
        print(colors.menu("─" * 28))
        print("  1  修改")
        print("  2  删除")
        print("  0  返回")
        print(colors.menu("─" * 28))

        o = ask()
        if o in {"", "0"}:
            return

        if o not in {"1", "2"}:
            continue

        if not items:
            print("无可操作短链接")
            pause()
            continue

        value = input("输入序号(回车取消): ").strip()
        if value in {"", "0"}:
            print("已取消")
            pause()
            continue

        if not value.isdigit() or not (1 <= int(value) <= len(items)):
            print(colors.err("序号无效。"))
            pause()
            continue

        it = items[int(value) - 1]
        current_code = item_code(it)
        current_long = item_long_url(it)

        if o == "1":
            while True:
                slug_input = input(
                    f"输入新的短链接 slug [当前: {current_code}]（留空则不修改）: "
                ).strip()

                if not slug_input or validate_slug(slug_input):
                    break

                print("slug 只能包含字母、数字、点、下划线、短横线，长度 3-128。")

            target_input = input(
                f"输入新的目标长链接或 token [当前: {current_long}]（留空则不修改）: "
            ).strip()

            final_code = slug_input or current_code

            if target_input:
                token = extract_token(target_input)
                final_long = make_long_url(token, cfg) if token else target_input
            else:
                final_long = current_long

            if final_code == current_code and final_long == current_long:
                print("未修改，已取消")
                pause()
                continue

            print()
            print("确认修改成如下吗")
            print(f"{cfg['SHORT_DOMAIN'].rstrip('/')}/{final_code} -> {final_long}")

            if input("输入yes确认，留空则取消: ").strip().lower() != "yes":
                print("已取消")
                pause()
                continue

            if final_code != current_code:
                st, _, raw = shlink_create(cfg, final_code, final_long)
                if st >= 300:
                    print(raw)
                    pause()
                    continue

                st2, _, raw2 = shlink_delete(cfg, current_code)
                if st2 >= 300:
                    print(raw2)
                    pause()
                    continue
            else:
                st, _, raw = shlink_patch(cfg, current_code, final_long)
                if st >= 300:
                    print(raw)
                    pause()
                    continue

            print(colors.ok("[OK] 修改完成"))
            pause()
            continue

        if o == "2":
            if yesno("确认删除？输入yes继续(回车取消): "):
                st, _, raw = shlink_delete(cfg, current_code)

                if st >= 300:
                    print(raw)
                    pause()
                    continue

                print(colors.ok("[OK] 删除完成"))
                pause()
                continue

            print("已取消")
            pause()
            continue


def db_menu():
    while True:
        menu(
            "订阅监控",
            [
                ("1", "监控拉取测试"),
                ("2", "TG通知测试"),
                ("3", "启动监控和TG通知"),
                ("4", "停止监控和TG通知"),
                ("5", "重启监控和TG通知"),
                ("6", "服务状态"),
                ("7", "服务日志"),
                ("0", "返回"),
            ],
        )

        o = ask()
        if o in {"", "0"}:
            return

        commands = {
            "1": ["pasar", "monitor-db", "--test"],
            "2": ["pasar", "monitor-db", "--send-test"],
            "3": ["systemctl", "enable", "--now", "sub-notify-db.service"],
            "4": ["systemctl", "disable", "--now", "sub-notify-db.service"],
            "5": ["systemctl", "restart", "sub-notify-db.service"],
            "6": ["systemctl", "status", "sub-notify-db.service", "--no-pager", "-l"],
            "7": ["journalctl", "-u", "sub-notify-db.service", "-n", "80", "--no-pager"],
        }

        if o in commands:
            clear_screen()
            print(colors.menu("$ " + " ".join(commands[o])))
            subprocess.run(commands[o], check=False)
            print()
            pause()


def settings(cfg):
    groups = {
        "1": ["PASAR_PANEL_HOST", "PASAR_PANEL_PORT", "PASAR_API_KEY", "SUB_BASE_URL"],
        "2": ["SHLINK_API_BASE", "SHLINK_API_KEY", "SHORT_DOMAIN"],
        "3": ["TG_BOT_TOKEN", "TG_CHAT_ID", "TG_THREAD_ID"],
        "5": [
            "DB_MONITOR_STATE_FILE",
            "DB_MONITOR_NGINX_LOOKBACK_SECONDS",
            "DB_MONITOR_NGINX_STATUS",
        ],
    }

    group_titles = {
        "1": "Pasar设置",
        "2": "Shlink设置",
        "3": "Telegram设置",
        "5": "安装维护设置",
    }

    def edit_group(title, keys):
        while True:
            items = [(str(i + 1), k) for i, k in enumerate(keys)] + [("0", "返回")]
            menu(title, items)

            x = ask()
            if x in {"", "0"}:
                return

            if x.isdigit() and 1 <= int(x) <= len(keys):
                key = keys[int(x) - 1]
                v = prompt_value(key, cfg.get(key))

                if v:
                    cfg[key] = v
                    save_config(cfg)
                    print(colors.ok("[OK] 配置已保存"))
                    pause()

    while True:
        menu(
            "设置",
            [
                ("1", "Pasar"),
                ("2", "Shlink"),
                ("3", "Telegram"),
                ("4", "订阅监控"),
                ("5", "安装维护"),
                ("6", "查看配置"),
                ("0", "返回"),
            ],
        )

        o = ask()
        if o in {"", "0"}:
            return

        if o == "6":
            clear_screen()
            print("当前配置：")
            print("─" * 28)
            for k in sorted(cfg.keys()):
                value = cfg[k]
                if "TOKEN" in k or "KEY" in k:
                    value = "<hidden>" if value else ""
                print(f"{k}={value}")
            print()
            pause()

        elif o == "4":
            monitor_settings(cfg)

        elif o in groups:
            edit_group(group_titles[o], groups[o])


def monitor_settings(cfg):
    keys = {
        "1": "PASARGUARD_DB_PATH",
        "2": "NGINX_ACCESS_LOG",
        "3": "DB_MONITOR_POLL_SECONDS",
        "4": "DISPLAY_TIMEZONE",
    }

    while True:
        menu(
            "订阅监控设置",
            [
                ("1", "DB路径"),
                ("2", "Nginx日志路径"),
                ("3", "轮询间隔"),
                ("4", "显示时区"),
                ("0", "返回"),
            ],
        )

        x = ask()
        if x in {"", "0"}:
            return

        if x in keys:
            key = keys[x]
            v = prompt_value(key, cfg.get(key))

            if v:
                cfg[key] = v
                save_config(cfg)
                print(colors.ok("[OK] 配置已保存"))
                pause()


def main_menu():
    while True:
        cfg = load_config()

        menu(
            f"🚀 订阅与短链管理 v{__version__}",
            [
                ("1", "⚡ 快速新增用户+短链"),
                ("2", "🔗 管理短链"),
                ("3", "📡 订阅监控"),
                ("4", "⚙️  设置"),
                ("0", "退出"),
            ],
            main=True,
        )

        o = ask()
        if o in {"", "0"}:
            clear_screen()
            return

        if o == "1":
            create_link(cfg)
            pause()

        elif o == "2":
            manage_short(cfg)

        elif o == "3":
            db_menu()

        elif o == "4":
            settings(cfg)


def main(argv=None):
    main_menu()
