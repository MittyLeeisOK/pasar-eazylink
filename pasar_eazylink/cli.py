import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import load_config, save_config
from .mapping import add_token, delete_user, show_mapping
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


def legacy_mapping_enabled(cfg: dict) -> bool:
    return config_bool(cfg.get("EAZYLINK_WRITE_LEGACY_MAPPING", "false"))


def maybe_write_legacy_mapping(cfg: dict, token: str, username: str) -> bool:
    if not legacy_mapping_enabled(cfg):
        print("Legacy Mapping 写入已关闭，跳过 /etc/sub-map.tsv。")
        return False
    add_token(cfg, token, username)
    return True


def run_command(cmd: list[str]):
    print()
    print("$ " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError as exc:
        print(f"命令不可用：{exc}")
    except Exception as exc:
        print(f"命令执行失败：{exc}")


def run_upgrade():
    print()
    confirm = input("确认升级？输入 yes 继续: ").strip().lower()
    if confirm != "yes":
        print("已取消。")
        return

    script_candidates = [
        Path("/opt/pasar-eazylink/install.sh"),
        Path(__file__).resolve().parent.parent / "install.sh",
    ]
    script = next((p for p in script_candidates if p.exists()), None)
    if not script:
        print("未找到 install.sh，无法自动升级。")
        print("请手动执行安装脚本完成升级。")
        return

    print(f"开始执行升级脚本：{script}")
    try:
        result = subprocess.run(["bash", str(script)], check=False)
    except Exception as exc:
        print(f"升级执行失败：{exc}")
        return

    if result.returncode == 0:
        print("升级完成。")
    else:
        print(f"升级失败，退出码：{result.returncode}")
        print("请确认当前用户权限后重试。")


def remove_path(path: Path, label: str):
    if not path.exists() and not path.is_symlink():
        print(f"{label} 不存在，跳过。")
        return
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        print(f"{label} 已删除：{path}")
    except Exception as exc:
        print(f"{label} 删除失败：{exc}")


def run_uninstall(cfg: dict):
    print()
    print("卸载将删除程序文件。")
    confirm = input("输入 uninstall 确认卸载: ").strip().lower()
    if confirm != "uninstall":
        print("已取消。")
        return

    remove_path(Path("/usr/local/bin/pasar"), "命令入口")
    remove_path(Path("/usr/local/bin/sub-notify"), "提醒命令入口")
    remove_path(Path("/etc/systemd/system/sub-notify.service"), "提醒服务文件")
    remove_path(Path("/etc/systemd/system/sub-notify-db.service"), "DB 提醒服务文件")
    remove_path(Path("/opt/pasar-eazylink"), "安装目录")
    os.system("systemctl daemon-reload >/dev/null 2>&1")

    while True:
        extra = input("是否同时删除配置与映射文件？输入 yes 继续，输入 no 跳过: ").strip().lower()
        if extra == "yes":
            remove_path(Path("/etc/pasar-easylink.env"), "主配置文件")
            remove_path(Path("/etc/sub-notify.env"), "通知配置文件")
            map_path = Path(cfg.get("SUB_MAP_FILE", ""))
            if str(map_path).strip():
                remove_path(map_path, "映射文件")
            break
        if extra == "no":
            print("已跳过删除配置与映射文件。")
            break
        print("输入无效，请输入 yes 或 no。")

    print("卸载流程已结束。")


def create_eazy_link(cfg: dict):
    print()
    print("=== 新增 Eazy Link ===")

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

    maybe_write_legacy_mapping(cfg, token, username)

    if not shlink_upsert(cfg, slug, long_url):
        return

    print()
    print("=== 新增完成 ===")
    print(f"用户：{username}")
    print(f"短链接：{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}")
    print(f"长链接：{long_url}")
    print(f"token：{short_token(token)}")

    if legacy_mapping_enabled(cfg):
        show_mapping(cfg, username)


def update_eazy_link(cfg: dict):
    print()
    print("=== 更新 Eazy Link ===")

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
    maybe_write_legacy_mapping(cfg, token, username)

    print()
    print("选择要覆盖的短链接。")
    matches = show_shortlinks(cfg, username)

    selected = None
    if matches:
        value = input("选择序号覆盖；输入 0 或回车新建短链接: ").strip()
        if value and value.isdigit() and 1 <= int(value) <= len(matches):
            selected = matches[int(value) - 1]

    if selected:
        code = item_code(selected)
        status, data, raw = shlink_patch(cfg, code, long_url)

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

    print()
    print("=== 更新完成 ===")
    print(f"用户：{username}")
    print(f"短链接：{short_url}")
    print(f"长链接：{long_url}")
    print(f"token：{short_token(token)}")

    if legacy_mapping_enabled(cfg):
        show_mapping(cfg, username)


def delete_eazy_link(cfg: dict):
    print()
    print("=== 删除 Eazy Link ===")

    username = input_nonempty("用户名: ")
    if not validate_username(username):
        print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
        return

    show_mapping(cfg, username)
    matches = show_shortlinks(cfg, username)

    confirm = input("确认删除该用户的所有 mapping？输入 yes 继续: ").strip().lower()
    if confirm != "yes":
        print("已取消。")
        return

    delete_user(cfg, username)

    if matches:
        confirm2 = input("是否同时删除上面匹配到的所有短链接？输入 yes 继续: ").strip().lower()
        if confirm2 == "yes":
            for item in matches:
                status, data, raw = shlink_delete(cfg, item_code(item))
                if status in (200, 202, 204, 404):
                    print(f"已删除/跳过：{item_short_url(item, cfg)}")
                else:
                    print(f"删除失败：{item_short_url(item, cfg)} HTTP {status}")
                    if raw:
                        print(raw)

    print("删除完成。说明：这里不删除 PasarGuard 面板中的真实用户。")


def view_shortlinks(cfg: dict):
    query = input("关键词过滤，留空查看全部: ").strip()
    show_shortlinks(cfg, query)


def legacy_mapping_menu(cfg: dict):
    items = [
        ("1", "查看 user mapping"),
        ("2", "按用户删除 mapping"),
        ("3", "手动新增 token -> 用户 mapping"),
        ("0", "返回"),
    ]
    while True:
        menu_block("Legacy Mapping 工具", items)
        opt = prompt_menu()

        if opt == "1":
            query = input("关键词过滤，留空查看全部: ").strip()
            show_mapping(cfg, query)
        elif opt == "2":
            username = input_nonempty("用户名: ")
            if not validate_username(username):
                print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
                continue
            delete_user(cfg, username)
        elif opt == "3":
            token = input_nonempty("token: ")
            username = input_nonempty("用户名: ")
            if not validate_username(username):
                print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
                continue
            add_token(cfg, token, username)
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def manage_shortlink_modify(cfg: dict):
    item = select_shortlink(cfg)
    if not item:
        return

    old_code = item_code(item)
    old_long = item_long_url(item)

    print()
    print(f"当前 shortCode：{old_code}")
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
        print("将创建新短链并删除旧短链。")

        if not shlink_upsert(cfg, new_slug, new_long):
            return

        status, data, raw = shlink_delete(cfg, old_code)
        if status not in (200, 202, 204, 404):
            print(f"旧短链删除失败，HTTP {status}")
            print(raw)
            return

        final_short = f"{cfg['SHORT_DOMAIN'].rstrip('/')}/{new_slug}"
    else:
        status, data, raw = shlink_patch(cfg, old_code, new_long)

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

    print()
    print("=== 修改完成 ===")
    print(f"短链接：{final_short}")
    print(f"目标：{new_long}")


def manage_shortlink_delete(cfg: dict):
    item = select_shortlink(cfg)
    if not item:
        return

    code = item_code(item)
    short_url = item_short_url(item, cfg)
    long_url = item_long_url(item)

    print()
    print(f"准备删除：{short_url}")
    print(f"目标：{long_url}")

    confirm = input("确认删除这个短链接？输入 yes 继续: ").strip().lower()
    if confirm != "yes":
        print("已取消。")
        return

    status, data, raw = shlink_delete(cfg, code)
    if status in (200, 202, 204, 404):
        print("短链接已删除。")
    else:
        print(f"删除失败，HTTP {status}")
        print(raw)


def shortlink_manage_menu(cfg: dict):
    items = [
        ("1", "修改某个短链接"),
        ("2", "删除某个短链接"),
        ("3", "查看短链接列表"),
        ("0", "返回"),
    ]
    while True:
        menu_block("短链接管理", items)
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


def subnotify_menu():
    items = [
        ("1", "测试最近一条订阅记录，不发送 TG"),
        ("2", "发送最近一条订阅记录作为测试"),
        ("3", "查看 sub-notify-db.service 状态"),
        ("4", "启动 sub-notify-db.service"),
        ("5", "停止 sub-notify-db.service"),
        ("6", "查看最近日志"),
        ("0", "返回"),
    ]
    while True:
        menu_block("DB 订阅提醒", items)
        opt = prompt_menu()

        if opt == "1":
            run_command(["pasar", "subnotify-db", "--test"])
        elif opt == "2":
            run_command(["pasar", "subnotify-db", "--send-test"])
        elif opt == "3":
            run_command(["systemctl", "status", "sub-notify-db.service", "--no-pager", "-l"])
        elif opt == "4":
            run_command(["systemctl", "enable", "--now", "sub-notify-db.service"])
        elif opt == "5":
            run_command(["systemctl", "disable", "--now", "sub-notify-db.service"])
        elif opt == "6":
            run_command(["journalctl", "-u", "sub-notify-db.service", "-n", "80", "--no-pager"])
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def settings_menu(cfg: dict):
    items = [
        ("1", "Pasar Panel 地址"),
        ("2", "Pasar Panel 端口"),
        ("3", "Pasar 登录/更新 Access Token"),
        ("4", "Shlink API Key"),
        ("5", "短链域名"),
        ("6", "订阅基础地址"),
        ("7", "Mapping 表路径"),
        ("8", "TG Bot Token"),
        ("9", "TG Chat ID"),
        ("10", "TG Thread ID"),
        ("11", "查看当前配置"),
        ("12", "测试 Pasar API"),
        ("13", "测试 Shlink API"),
        ("14", "测试 TG 通知"),
        ("15", "升级程序"),
        ("16", "卸载程序"),
        ("17", "PasarGuard SQLite 路径"),
        ("18", "提醒轮询间隔秒数"),
        ("19", "提醒状态文件路径"),
        ("20", "提醒用户状态过滤"),
        ("21", "Legacy Mapping 自动写入"),
        ("0", "返回"),
    ]
    while True:
        cfg = load_config()

        menu_block("Eazy Link 设置", items)
        opt = prompt_menu()

        if opt == "1":
            value = input(f"Pasar Panel 地址 [当前: {cfg['PASAR_PANEL_HOST']}]: ").strip()
            if value:
                cfg["PASAR_PANEL_HOST"] = value.rstrip("/")
                save_config(cfg)
        elif opt == "2":
            value = input(f"Pasar Panel 端口 [当前: {cfg['PASAR_PANEL_PORT']}]: ").strip()
            if value:
                cfg["PASAR_PANEL_PORT"] = value
                save_config(cfg)
        elif opt == "3":
            pasar_login(cfg)
        elif opt == "4":
            value = input("Shlink API Key: ").strip()
            if value:
                cfg["SHLINK_API_KEY"] = value
                save_config(cfg)
        elif opt == "5":
            value = input(f"短链域名 [当前: {cfg['SHORT_DOMAIN']}]: ").strip()
            if value:
                cfg["SHORT_DOMAIN"] = value.rstrip("/")
                cfg["SHLINK_API_BASE"] = f"{value.rstrip('/')}/rest/v3"
                save_config(cfg)
        elif opt == "6":
            value = input(f"订阅基础地址 [当前: {cfg['SUB_BASE_URL']}]: ").strip()
            if value:
                cfg["SUB_BASE_URL"] = value.rstrip("/")
                save_config(cfg)
        elif opt == "7":
            value = input(f"Mapping 表路径 [当前: {cfg['SUB_MAP_FILE']}]: ").strip()
            if value:
                cfg["SUB_MAP_FILE"] = value
                save_config(cfg)
        elif opt == "8":
            value = input("TG Bot Token: ").strip()
            if value:
                cfg["TG_BOT_TOKEN"] = value
                save_config(cfg)
                sync_tg_env(cfg)
        elif opt == "9":
            value = input("TG Chat ID: ").strip()
            if value:
                cfg["TG_CHAT_ID"] = value
                save_config(cfg)
                sync_tg_env(cfg)
        elif opt == "10":
            value = input("TG Thread ID，可留空: ").strip()
            cfg["TG_THREAD_ID"] = value
            save_config(cfg)
            sync_tg_env(cfg)
        elif opt == "11":
            print()
            print("=== 当前配置 ===")
            print(f"Pasar Panel 地址：{cfg['PASAR_PANEL_HOST']}")
            print(f"Pasar Panel 端口：{cfg['PASAR_PANEL_PORT']}")
            print(f"Shlink API Base：{cfg['SHLINK_API_BASE']}")
            print(f"短链域名：{cfg['SHORT_DOMAIN']}")
            print(f"订阅基础地址：{cfg['SUB_BASE_URL']}")
            print(f"Mapping 表：{cfg['SUB_MAP_FILE']}")
            print(f"TG Bot Token：{mask(cfg['TG_BOT_TOKEN'])}")
            print(f"TG Chat ID：{mask(cfg['TG_CHAT_ID'])}")
            print(f"TG Thread ID：{mask(cfg['TG_THREAD_ID'])}")
            print(f"PasarGuard SQLite：{cfg['PASARGUARD_DB_PATH']}")
            print(f"提醒轮询间隔：{cfg['SUB_NOTIFY_POLL_SECONDS']}")
            print(f"提醒状态文件：{cfg['SUB_NOTIFY_STATE_FILE']}")
            print(f"提醒状态过滤：{cfg['SUB_NOTIFY_USER_STATUS'] or '<empty>'}")
            print(f"Legacy Mapping 自动写入：{cfg['EAZYLINK_WRITE_LEGACY_MAPPING']}")
        elif opt == "12":
            test_pasar(cfg)
        elif opt == "13":
            test_shlink(cfg)
        elif opt == "14":
            test_tg(cfg)
        elif opt == "15":
            run_upgrade()
        elif opt == "16":
            run_uninstall(cfg)
        elif opt == "17":
            value = input(f"PasarGuard SQLite 路径 [当前: {cfg['PASARGUARD_DB_PATH']}]: ").strip()
            if value:
                cfg["PASARGUARD_DB_PATH"] = value
                save_config(cfg)
        elif opt == "18":
            value = input(f"提醒轮询间隔秒数 [当前: {cfg['SUB_NOTIFY_POLL_SECONDS']}]: ").strip()
            if value:
                cfg["SUB_NOTIFY_POLL_SECONDS"] = value
                save_config(cfg)
        elif opt == "19":
            value = input(f"提醒状态文件路径 [当前: {cfg['SUB_NOTIFY_STATE_FILE']}]: ").strip()
            if value:
                cfg["SUB_NOTIFY_STATE_FILE"] = value
                save_config(cfg)
        elif opt == "20":
            value = input(
                f"提醒用户状态过滤（逗号分隔，可留空） [当前: {cfg['SUB_NOTIFY_USER_STATUS'] or '<empty>'}]: "
            ).strip()
            cfg["SUB_NOTIFY_USER_STATUS"] = value
            save_config(cfg)
        elif opt == "21":
            value = input(
                f"Legacy Mapping 自动写入（true/false） [当前: {cfg['EAZYLINK_WRITE_LEGACY_MAPPING']}]: "
            ).strip().lower()
            if value in {"true", "false"}:
                cfg["EAZYLINK_WRITE_LEGACY_MAPPING"] = value
                save_config(cfg)
            elif value:
                print("请输入 true 或 false。")
        elif opt == "0":
            return
        else:
            print("无效选项，请重试。")


def main_menu():
    items = [
        ("1", "新增 Eazy Link"),
        ("2", "更新 Eazy Link"),
        ("3", "删除 Eazy Link"),
        ("4", "查看短链接"),
        ("5", "单独短链接管理"),
        ("6", "DB 订阅提醒"),
        ("7", "设置"),
        ("8", "Legacy Mapping 工具"),
        ("0", "退出"),
    ]
    while True:
        cfg = load_config()

        menu_block(f"Pasar Eazy Link v{__version__}", items)
        opt = prompt_menu()

        if opt == "1":
            create_eazy_link(cfg)
        elif opt == "2":
            update_eazy_link(cfg)
        elif opt == "3":
            delete_eazy_link(cfg)
        elif opt == "4":
            view_shortlinks(cfg)
        elif opt == "5":
            shortlink_manage_menu(cfg)
        elif opt == "6":
            subnotify_menu()
        elif opt == "7":
            settings_menu(cfg)
        elif opt == "8":
            legacy_mapping_menu(cfg)
        elif opt == "0":
            return
        else:
            print("输入无效，已退出。")
            return


def main(argv: list[str] | None = None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] == "easylink":
        main_menu()
    else:
        print("Usage: pasar easylink")
        sys.exit(1)
