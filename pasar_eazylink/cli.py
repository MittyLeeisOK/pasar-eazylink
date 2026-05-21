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

    add_token(cfg, token, username)

    if not shlink_upsert(cfg, slug, long_url):
        return

    print()
    print("=== 新增完成 ===")
    print(f"用户：{username}")
    print(f"短链接：{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}")
    print(f"长链接：{long_url}")
    print(f"token：{short_token(token)}")

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
    add_token(cfg, token, username)

    print()
    print("选择要覆盖的短链接。")
    matches = show_shortlinks(cfg, username)

    selected = None
    if matches:
        value = input("选择序号覆盖；输入 0 或回车新建短链接: ").strip()
        if value == "":
            selected = None
        elif value.isdigit() and 1 <= int(value) <= len(matches):
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


def view_menu(cfg: dict):
    while True:
        print()
        print("=== 数据查看 ===")
        print("1 查看 Mapping")
        print("2 查看短链接列表")
        print("3 同时查看 Mapping 和短链接")
        print("0 返回")

        opt = input("请选择（0/b/back 返回）: ").strip().lower()
        if opt in {"b", "back"}:
            opt = "0"

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
            print("无效选项。")


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
    while True:
        print()
        print("=== 短链接管理 ===")
        print("1 修改某个短链接")
        print("2 删除某个短链接")
        print("3 查看短链接列表")
        print("0 返回")

        opt = input("请选择（0/b/back 返回）: ").strip().lower()
        if opt in {"b", "back"}:
            opt = "0"

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
            print("无效选项。")


def settings_menu(cfg: dict):
    while True:
        cfg = load_config()

        print()
        print("=== Eazy Link 设置 ===")
        print("1 Pasar Panel 地址")
        print("2 Pasar Panel 端口")
        print("3 Pasar 登录/更新 Access Token")
        print("4 日本 Shlink API Key")
        print("5 短链域名")
        print("6 订阅基础地址")
        print("7 Mapping 表路径")
        print("8 TG Bot Token")
        print("9 TG Chat ID")
        print("10 TG Thread ID")
        print("11 查看当前配置")
        print("12 测试 Pasar API")
        print("13 测试 Shlink API")
        print("14 测试 TG 通知")
        print("0 返回")

        opt = input("请选择（0/b/back 返回）: ").strip().lower()
        if opt in {"b", "back"}:
            opt = "0"

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
            value = input("日本 Shlink API Key: ").strip()
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
            print(f"Pasar Access Token：{mask(cfg['PASAR_API_KEY'])}")
            print(f"Shlink API Base：{cfg['SHLINK_API_BASE']}")
            print(f"Shlink API Key：{mask(cfg['SHLINK_API_KEY'])}")
            print(f"短链域名：{cfg['SHORT_DOMAIN']}")
            print(f"订阅基础地址：{cfg['SUB_BASE_URL']}")
            print(f"Mapping 表：{cfg['SUB_MAP_FILE']}")
            print(f"TG Bot Token：{mask(cfg['TG_BOT_TOKEN'])}")
            print(f"TG Chat ID：{mask(cfg['TG_CHAT_ID'])}")
            print(f"TG Thread ID：{mask(cfg['TG_THREAD_ID'])}")
        elif opt == "12":
            test_pasar(cfg)
        elif opt == "13":
            test_shlink(cfg)
        elif opt == "14":
            test_tg(cfg)
        elif opt == "0":
            return
        else:
            print("无效选项。")


def main_menu():
    while True:
        cfg = load_config()

        print()
        print(f"=== Pasar Eazy Link v{__version__} ===")
        print("1 新增 Eazy Link")
        print("2 更新 Eazy Link")
        print("3 删除 Eazy Link")
        print("4 查看 Mapping / 短链接")
        print("5 短链接管理")
        print("6 设置")
        print("0 退出")

        opt = input("请选择（0/q 退出）: ").strip().lower()
        if opt in {"q", "quit", "exit"}:
            opt = "0"

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
            return
        else:
            print("无效选项。")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "easylink":
        main_menu()
    else:
        print("Usage: pasar easylink")
        sys.exit(1)
