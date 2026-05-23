import subprocess
from . import __version__
from .colors import colors
from .config import load_config, save_config
from .pasar_api import create_user_from_template, list_templates
from .shlink_api import show_list, select, item_code, patch as shlink_patch, delete as shlink_delete, upsert as shlink_upsert
from .utils import validate_username, extract_token, make_long_url, prompt_slug


def menu(title, items):
    print('\n' + '=' * 20)
    print(colors.title(title))
    print('=' * 20)
    for k, v in items:
        print(f"{k}  {v}")
    print('=' * 20)


def ask():
    return (input('请输入选项: ').strip().lower() or '0')


def yesno(prompt):
    return (input(prompt).strip().lower() or 'no') == 'yes'


def prompt_value(label: str, current: str | None = None):
    suffix = f" [当前: {current}]" if current else ""
    value = input(f"输入{label}{suffix}(回车取消): ").strip()
    return value or None


def create_link(cfg):
    list_templates(cfg)
    u = input('用户名(回车取消): ').strip()
    if not u or u == '0':
        print('已取消')
        return
    if not validate_username(u):
        print(colors.err('用户名格式无效'))
        return
    tid = input('模板ID(回车取消): ').strip()
    if not tid or tid == '0':
        print('已取消')
        return
    long_url = create_user_from_template(cfg, u, int(tid), input('备注(回车留空): ').strip())
    if not long_url:
        return
    slug = prompt_slug(u)
    if shlink_upsert(cfg, slug, long_url):
        print(colors.ok(f"用户：{u}\n长链：{long_url}\n短链：{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}"))


def manage_short(cfg):
    while True:
        menu('=== 管理短链 ===', [('1', '查看短链'), ('2', '修改短链'), ('3', '删除短链'), ('4', '更新用户订阅目标'), ('0', '返回')])
        o = ask()
        if o in {'', '0'}:
            return
        if o == '1':
            show_list(cfg, input('关键词(回车全部): ').strip())
        elif o in {'2', '4'}:
            it = select(cfg)
            if not it:
                continue
            t = input('新的目标长链接或token(回车取消): ').strip()
            if not t:
                print('已取消')
                continue
            token = extract_token(t)
            long = make_long_url(token, cfg) if token else t
            st, _, raw = shlink_patch(cfg, item_code(it), long)
            print(raw if st >= 300 else colors.ok('已更新'))
        elif o == '3':
            it = select(cfg)
            if it and yesno('确认删除？输入yes继续(回车取消): '):
                st, _, raw = shlink_delete(cfg, item_code(it))
                print(raw if st >= 300 else colors.ok('已删除'))


def db_menu():
    while True:
        menu('=== 订阅监控 ===', [('1', '测试'), ('2', '发送测试'), ('3', '启动'), ('4', '停止'), ('5', '重启'), ('6', '状态'), ('7', '日志'), ('0', '返回')])
        o = ask()
        if o in {'', '0'}:
            return
        m = {
            '1': ['pasar', 'monitor-db', '--test'],
            '2': ['pasar', 'monitor-db', '--send-test'],
            '3': ['systemctl', 'enable', '--now', 'sub-notify-db.service'],
            '4': ['systemctl', 'disable', '--now', 'sub-notify-db.service'],
            '5': ['systemctl', 'restart', 'sub-notify-db.service'],
            '6': ['systemctl', 'status', 'sub-notify-db.service', '--no-pager', '-l'],
            '7': ['journalctl', '-u', 'sub-notify-db.service', '-n', '80', '--no-pager'],
        }
        if o in m:
            subprocess.run(m[o], check=False)


def settings(cfg):
    groups = {
        '1': ['PASAR_PANEL_HOST', 'PASAR_PANEL_PORT', 'PASAR_API_KEY', 'SUB_BASE_URL'],
        '2': ['SHLINK_API_BASE', 'SHLINK_API_KEY', 'SHORT_DOMAIN'],
        '3': ['TG_BOT_TOKEN', 'TG_CHAT_ID', 'TG_THREAD_ID'],
        '5': ['DB_MONITOR_STATE_FILE', 'DB_MONITOR_NGINX_LOOKBACK_SECONDS', 'DB_MONITOR_NGINX_STATUS'],
    }

    def edit_group(title, keys):
        while True:
            items = [(str(i + 1), k) for i, k in enumerate(keys)] + [('0', '返回')]
            menu(title, items)
            x = ask()
            if x == '0':
                return
            if x.isdigit() and 1 <= int(x) <= len(keys):
                key = keys[int(x) - 1]
                v = prompt_value(key, cfg.get(key))
                if v:
                    cfg[key] = v
                    save_config(cfg)

    while True:
        menu('=== 设置 ===', [('1', 'Pasar'), ('2', 'Shlink'), ('3', 'Telegram'), ('4', '订阅监控'), ('5', '安装维护'), ('6', '查看配置'), ('0', '返回')])
        o = ask()
        if o == '0':
            return
        if o == '6':
            print(cfg)
        elif o == '4':
            while True:
                menu('=== 订阅监控设置 ===', [('1', 'DB路径'), ('2', 'Nginx日志路径'), ('3', '轮询间隔'), ('4', '是否补全真实IP'), ('5', '显示时区'), ('6', '监控服务开关'), ('0', '返回')])
                x = ask()
                if x in {'', '0'}:
                    break
                keys = {'1': 'PASARGUARD_DB_PATH', '2': 'NGINX_ACCESS_LOG', '3': 'DB_MONITOR_POLL_SECONDS', '4': 'DB_MONITOR_LOOKUP_NGINX_IP', '5': 'DISPLAY_TIMEZONE'}
                if x in keys:
                    v = prompt_value(keys[x], cfg.get(keys[x]))
                    if v:
                        cfg[keys[x]] = v
                        save_config(cfg)
                elif x == '6':
                    if yesno('启用监控服务？输入yes启用(否则禁用): '):
                        subprocess.run(['systemctl', 'enable', '--now', 'sub-notify-db.service'], check=False)
                    else:
                        subprocess.run(['systemctl', 'disable', '--now', 'sub-notify-db.service'], check=False)
        elif o in groups:
            edit_group(f"=== {dict([('1','Pasar设置'),('2','Shlink设置'),('3','Telegram设置'),('5','安装维护设置')])[o]} ===", groups[o])


def main_menu():
    while True:
        cfg = load_config()
        menu(f'=== 订阅与短链管理 v{__version__} ===', [('1', '快速新增用户+短链'), ('2', '管理短链'), ('3', '订阅监控'), ('4', '设置'), ('0', '退出')])
        o = ask()
        if o in {'', '0'}:
            return
        if o == '1':
            create_link(cfg)
        elif o == '2':
            manage_short(cfg)
        elif o == '3':
            db_menu()
        elif o == '4':
            settings(cfg)


def main(argv=None):
    main_menu()
