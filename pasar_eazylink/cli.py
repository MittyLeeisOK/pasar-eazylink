import json
import sys

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

# ANSI color codes for better CLI aesthetics
COLORS = {
    'RESET': '\033[0m',
    'BOLD': '\033[1m',
    'CYAN': '\033[96m',
    'GREEN': '\033[92m',
    'YELLOW': '\033[93m',
    'BLUE': '\033[94m',
    'MAGENTA': '\033[95m',
    'RED': '\033[91m',
}

def colored(text, color):
    """Return colored text using ANSI codes"""
    return f"{COLORS.get(color, '')}{text}{COLORS['RESET']}"

def print_header(title):
    """Print a formatted header"""
    print()
    border = "═" * (len(title) + 4)
    print(colored(border, 'CYAN'))
    print(colored(f"  {title}  ", 'CYAN'))
    print(colored(border, 'CYAN'))

def print_section(title):
    """Print a formatted section title"""
    print()
    print(colored(f"╭─ {title}", 'BLUE'))

def print_option(num, title, description=""):
    """Print a formatted menu option"""
    if description:
        print(f"  {colored(num, 'YELLOW')} {title}")
        print(f"     {description}")
    else:
        print(f"  {colored(num, 'YELLOW')} {title}")


def create_eazy_link(cfg: dict):
    print_header("快速新增用户并生成短链接")
    print("此功能将快速为您创建一个新用户、生成订阅链接并自动创建短链接")
    print()

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

    add_token(cfg, token, username)

    if not shlink_upsert(cfg, slug, long_url):
        return

    print()
    print_header("创建完成")
    print(f"{colored('用户：', 'GREEN')}{username}")
    print(f"{colored('短链接：', 'GREEN')}{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}")
    print(f"{colored('长链接：', 'GREEN')}{long_url}")
    print(f"{colored('Token：', 'GREEN')}{short_token(token)}")

    show_mapping(cfg, username)


def update_eazy_link(cfg: dict):
    print_header("更新订阅链接")
    print("此功能将更新用户的订阅链接，保留原有的短链接映射")
    print()

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
    add_token(cfg, token, username)

    print()
    print("选择要覆盖的短链接。")
    matches = show_shortlinks(cfg, username)

    selected = None
    if matches:
        value = input("选择序号覆盖；输入 0 新建一个短链接: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(matches):
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
    print_header("更新完成")
    print(f"{colored('用户：', 'GREEN')}{username}")
    print(f"{colored('短链接：', 'GREEN')}{short_url}")
    print(f"{colored('长链接：', 'GREEN')}{long_url}")
    print(f"{colored('Token：', 'GREEN')}{short_token(token)}")

    show_mapping(cfg, username)


def delete_eazy_link(cfg: dict):
    print_header("删除用户及其短链接")
    print("此功能将删除用户的映射关系和对应的短链接")
    print()

    username = input_nonempty("用户名: ")
    if not validate_username(username):
        print("用户名只能包含字母、数字、点、下划线、短横线，长度 3-64。")
        return

    show_mapping(cfg, username)
    matches = show_shortlinks(cfg, username)

    confirm = input("确认删除该用户的所有 mapping？输入 yes 继续: ").strip()
    if confirm != "yes":
        print("已取消。")
        return

    delete_user(cfg, username)

    if matches:
        confirm2 = input("是否同时删除上面匹配到的所有短链接？输入 yes 继续: ").strip()
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


def view_menu(cfg: dict):
    while True:
        print_header("查看用户映射和短链接")

        print_option("1", "查看用户映射", "查看所有用户及其订阅链接的映射关系")
        print_option("2", "查看短链接列表", "查看所有已创建的短链接列表")
        print_option("3", "同时查看映射和短链接", "一次性查看所有用户映射和短链接信息")
        print_option("0", "返回主菜单")

        opt = input("\n请选择: ").strip()

        if opt == "1":
            query = input("关键词过滤，留空查看全部: ").strip()
            show_mapping(cfg, query)
        elif opt == "2":
            query = input("关键词过滤，留空查看全部: ").strip()
            show_shortlinks(cfg, query)
        elif opt == "3":
            query = input("关键词过滤，留空查看全部: ").strip()
            show_mapping(cfg, query)
            show_shortlinks(cfg, query)
        elif opt == "0":
            return
        else:
            print(colored("无效选项。", 'RED'))


def manage_shortlink_modify(cfg: dict):
    item = select_shortlink(cfg)
    if not item:
        return

    old_code = item_code(item)
    old_long = item_long_url(item)

    print()
    print_header("修改短链接")
    print(f"{colored('当前 shortCode：', 'CYAN')}{old_code}")
    print(f"{colored('当前短链接：', 'CYAN')}{item_short_url(item, cfg)}")
    print(f"{colored('当前目标：', 'CYAN')}{old_long}")

    new_slug = input("\n新的 shortCode/slug，留空不修改: ").strip()
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
    print_header("修改完成")
    print(f"{colored('短链接：', 'GREEN')}{final_short}")
    print(f"{colored('目标：', 'GREEN')}{new_long}")


def manage_shortlink_delete(cfg: dict):
    item = select_shortlink(cfg)
    if not item:
        return

    code = item_code(item)
    short_url = item_short_url(item, cfg)
    long_url = item_long_url(item)

    print()
    print_header("删除短链接")
    print(f"{colored('准备删除：', 'YELLOW')}{short_url}")
    print(f"{colored('目标：', 'YELLOW')}{long_url}")

    confirm = input("\n确认删除这个短链接？输入 yes 继续: ").strip()
    if confirm != "yes":
        print("已取消。")
        return

    status, data, raw = shlink_delete(cfg, code)
    if status in (200, 202, 204, 404):
        print(colored("✓ 短链接已删除。", 'GREEN'))
    else:
        print(f"删除失败，HTTP {status}")
        print(raw)


def shortlink_manage_menu(cfg: dict):
    while True:
        print_header("短链接管理")

        print_option("1", "修改短链接", "修改已创建的短链接的目标或代码")
        print_option("2", "删除短链接", "删除某个短链接")
        print_option("3", "查看短链接列表", "查看所有短链接")
        print_option("0", "返回主菜单")

        opt = input("\n请选择: ").strip()

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
            print(colored("无效选项。", 'RED'))


def settings_menu(cfg: dict):
    while True:
        cfg = load_config()

        print_header("系统设置")

        print_section("API 配置")
        print_option("1", "Pasar Panel 地址", "配置 PasarGuard 面板地址")
        print_option("2", "Pasar Panel 端口", "配置 PasarGuard 面板端口")
        print_option("3", "Pasar Access Token", "登录或更新 PasarGuard 访问令牌")

        print_section("短链接服务配置")
        print_option("4", "Shlink API Key", "配置 Shlink API 密钥")
        print_option("5", "短链域名", "配置短链接使用的域名")

        print_section("订阅服务配置")
        print_option("6", "订阅基础地址", "配置订阅地址基础URL")
        print_option("7", "用户映射表路径", "配置用户映射表文件位置")

        print_section("通知服务配置")
        print_option("8", "Telegram Bot Token", "配置 Telegram 机器人令牌")
        print_option("9", "Telegram Chat ID", "配置 Telegram 聊天ID")
        print_option("10", "Telegram Thread ID", "配置 Telegram 话题ID（可选）")

        print_section("工具和信息")
        print_option("11", "查看当前配置", "显示所有已配置的参数")
        print_option("12", "测试 Pasar API", "测试与 PasarGuard 的连接")
        print_option("13", "测试 Shlink API", "测试与 Shlink 的连接")
        print_option("14", "测试 Telegram 通知", "测试 Telegram 通知功能")
        print_option("0", "返回主菜单")

        opt = input("\n请选择: ").strip()

        if opt == "1":
            value = input(f"Pasar Panel 地址 [当前: {cfg['PASAR_PANEL_HOST']}]: ").strip()
            if value:
                cfg["PASAR_PANEL_HOST"] = value.rstrip("/")
                save_config(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "2":
            value = input(f"Pasar Panel 端口 [当前: {cfg['PASAR_PANEL_PORT']}]: ").strip()
            if value:
                cfg["PASAR_PANEL_PORT"] = value
                save_config(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "3":
            pasar_login(cfg)
        elif opt == "4":
            value = input("Shlink API Key: ").strip()
            if value:
                cfg["SHLINK_API_KEY"] = value
                save_config(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "5":
            value = input(f"短链域名 [当前: {cfg['SHORT_DOMAIN']}]: ").strip()
            if value:
                cfg["SHORT_DOMAIN"] = value.rstrip("/")
                cfg["SHLINK_API_BASE"] = f"{value.rstrip('/')}/rest/v3"
                save_config(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "6":
            value = input(f"订阅基础地址 [当前: {cfg['SUB_BASE_URL']}]: ").strip()
            if value:
                cfg["SUB_BASE_URL"] = value.rstrip("/")
                save_config(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "7":
            value = input(f"用户映射表路径 [当前: {cfg['SUB_MAP_FILE']}]: ").strip()
            if value:
                cfg["SUB_MAP_FILE"] = value
                save_config(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "8":
            value = input("Telegram Bot Token: ").strip()
            if value:
                cfg["TG_BOT_TOKEN"] = value
                save_config(cfg)
                sync_tg_env(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "9":
            value = input("Telegram Chat ID: ").strip()
            if value:
                cfg["TG_CHAT_ID"] = value
                save_config(cfg)
                sync_tg_env(cfg)
                print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "10":
            value = input("Telegram Thread ID，可留空: ").strip()
            cfg["TG_THREAD_ID"] = value
            save_config(cfg)
            sync_tg_env(cfg)
            print(colored("✓ 配置已保存", 'GREEN'))
        elif opt == "11":
            print_header("当前配置详情")
            print(f"{colored('Pasar Panel 地址：', 'CYAN')}{cfg['PASAR_PANEL_HOST']}")
            print(f"{colored('Pasar Panel 端口：', 'CYAN')}{cfg['PASAR_PANEL_PORT']}")
            # Sensitive tokens are masked using mask() function - shows only first 6 and last 4 chars
            print(f"{colored('Pasar Access Token：', 'CYAN')}{mask(cfg['PASAR_API_KEY'])}")
            print(f"{colored('Shlink API Base：', 'CYAN')}{cfg['SHLINK_API_BASE']}")
            # Sensitive API key is masked for security
            print(f"{colored('Shlink API Key：', 'CYAN')}{mask(cfg['SHLINK_API_KEY'])}")
            print(f"{colored('短链域名：', 'CYAN')}{cfg['SHORT_DOMAIN']}")
            print(f"{colored('订阅基础地址：', 'CYAN')}{cfg['SUB_BASE_URL']}")
            print(f"{colored('用户映射表：', 'CYAN')}{cfg['SUB_MAP_FILE']}")
            # Sensitive tokens are masked for security
            print(f"{colored('Telegram Bot Token：', 'CYAN')}{mask(cfg['TG_BOT_TOKEN'])}")
            print(f"{colored('Telegram Chat ID：', 'CYAN')}{mask(cfg['TG_CHAT_ID'])}")
            print(f"{colored('Telegram Thread ID：', 'CYAN')}{mask(cfg['TG_THREAD_ID'])}")
        elif opt == "12":
            test_pasar(cfg)
        elif opt == "13":
            test_shlink(cfg)
        elif opt == "14":
            test_tg(cfg)
        elif opt == "0":
            return
        else:
            print(colored("无效选项。", 'RED'))


def main_menu():
    while True:
        cfg = load_config()

        print_header(f"Pasar Eazy Link v{__version__}")

        print_section("用户和链接管理")
        print_option("1", "快速新增用户并生成短链接", "创建新用户、生成订阅链接和短链接")
        print_option("2", "更新订阅链接", "为已有用户更新订阅链接")
        print_option("3", "删除用户及其短链接", "删除用户映射和对应的短链接")

        print_section("查看和管理")
        print_option("4", "查看用户映射和短链接", "查看用户映射关系和已创建的短链接")
        print_option("5", "短链接管理", "修改或删除单个短链接")
        print_option("6", "系统设置", "配置API、域名、通知等参数")
        print_option("0", "退出程序")

        opt = input("\n请选择: ").strip()

        if opt == "1":
            create_eazy_link(cfg)
        elif opt == "2":
            update_eazy_link(cfg)
        elif opt == "3":
            delete_eazy_link(cfg)
        elif opt == "4":
            view_menu(cfg)
        elif opt == "5":
            shortlink_manage_menu(cfg)
        elif opt == "6":
            settings_menu(cfg)
        elif opt == "0":
            print()
            print(colored("感谢使用 Pasar Eazy Link，再见！", 'GREEN'))
            return
        else:
            print(colored("无效选项。", 'RED'))


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "easylink":
        main_menu()
    else:
        print("Usage: pasar easylink")
        sys.exit(1)
