import subprocess
from . import __version__
from .colors import colors
from .config import load_config, save_config
from .pasar_api import create_user_from_template, list_templates
from .shlink_api import show_shortlinks, select_shortlink, item_code, item_long_url, item_short_url, patch as shlink_patch, delete as shlink_delete, upsert as shlink_upsert
from .utils import input_nonempty, validate_username, extract_token, make_long_url, prompt_slug

def menu(title,items):
 print('\n'+'='*20);print(colors.title(title));print('='*20)
 for k,v in items: print(f"{k}  {v}")
 print('='*20)

def ask():
 return (input('请输入选项: ').strip() or '0').lower()

def yesno(prompt): return (input(prompt).strip().lower()=='yes')

def create_link(cfg):
    list_templates(cfg); u=input('用户名(0返回): ').strip();
    if not u or u=='0': return
    if not validate_username(u): print(colors.err('用户名格式无效')); return
    tid=input('模板ID(0返回): ').strip();
    if not tid or tid=='0': return
    long_url=create_user_from_template(cfg,u,int(tid),input('备注: ').strip())
    if not long_url:return
    slug=prompt_slug(u)
    if shlink_upsert(cfg,slug,long_url):
        print(colors.ok(f"用户：{u}\n长链：{long_url}\n短链：{cfg['SHORT_DOMAIN'].rstrip('/')}/{slug}"))

def manage_short(cfg):
  while True:
    menu('=== 管理短链 ===',[('1','查看短链'),('2','修改短链'),('3','删除短链'),('4','更新用户订阅目标'),('0','返回')])
    o=ask()
    if o=='0': return
    if o=='1': show_shortlinks(cfg,input('关键词(回车全部): ').strip())
    elif o=='2' or o=='4':
      it=select_shortlink(cfg)
      if not it: continue
      t=input('新的目标长链接或token(回车保持): ').strip()
      if not t: continue
      long=make_long_url(extract_token(t),cfg) if extract_token(t) else t
      st,_,raw=shlink_patch(cfg,item_code(it),long); print(raw if st>=300 else colors.ok('已更新'))
    elif o=='3':
      it=select_shortlink(cfg)
      if it and yesno('确认删除？输入yes继续: '):
        st,_,raw=shlink_delete(cfg,item_code(it)); print(raw if st>=300 else colors.ok('已删除'))

def db_menu():
 while True:
  menu('=== 订阅监控 ===',[('1','测试'),('2','发送测试'),('3','启动'),('4','停止'),('5','重启'),('6','状态'),('7','日志'),('0','返回')])
  o=ask();
  if o=='0': return
  m={'1':['pasar','monitor-db','--test'],'2':['pasar','monitor-db','--send-test'],'3':['systemctl','enable','--now','sub-notify-db.service'],'4':['systemctl','disable','--now','sub-notify-db.service'],'5':['systemctl','restart','sub-notify-db.service'],'6':['systemctl','status','sub-notify-db.service','--no-pager','-l'],'7':['journalctl','-u','sub-notify-db.service','-n','80','--no-pager']}
  if o in m: subprocess.run(m[o],check=False)

def settings(cfg):
 while True:
  menu('=== 设置 ===',[('1','Pasar'),('2','Shlink'),('3','Telegram'),('4','订阅监控'),('5','安装维护'),('6','查看配置'),('0','返回')])
  o=ask()
  if o=='0':return
  if o=='6': print(cfg)
  if o=='4':
    menu('=== 订阅监控设置 ===',[('1','DB路径'),('2','Nginx日志路径'),('3','轮询间隔'),('4','去重时间'),('5','是否补全真实IP'),('6','显示时区'),('0','返回')]);x=ask()
    keys={'1':'PASARGUARD_DB_PATH','2':'NGINX_ACCESS_LOG','3':'DB_MONITOR_POLL_SECONDS','4':'DB_MONITOR_DEDUP_SECONDS','5':'DB_MONITOR_LOOKUP_NGINX_IP','6':'DISPLAY_TIMEZONE'}
    if x in keys:
      v=input(f"输入{keys[x]}(回车保持): ").strip();
      if v: cfg[keys[x]]=v; save_config(cfg)

def main_menu():
 while True:
  cfg=load_config()
  menu(f'=== 订阅与短链管理 v{__version__} ===',[('1','快速新增用户+短链'),('2','管理短链'),('3','订阅监控'),('4','设置'),('0','退出')])
  o=ask()
  if o=='0': return
  if o=='1': create_link(cfg)
  elif o=='2': manage_short(cfg)
  elif o=='3': db_menu()
  elif o=='4': settings(cfg)

def main(argv=None): main_menu()
