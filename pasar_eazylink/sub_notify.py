import argparse, html, json, os, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .config import load_config
from .device import parse_user_agent
from .nginx_log import find_matching_request
from .http_client import http_json

def fmt_time(raw,tz_name):
    try:
        dt=datetime.strptime((raw or '').split('.')[0],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        tz=datetime.now().astimezone().tzinfo if (not tz_name or tz_name=='local') else ZoneInfo(tz_name)
        l=dt.astimezone(tz)
        return l.strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        return raw or '<unknown>'

def mask_path(p):
    if not p.startswith('/sub/'): return p
    t=p[5:]; return '/sub/'+(t[:8]+'...'+t[-6:] if len(t)>14 else t)

def send_tg(cfg,text):
    form={'chat_id':cfg['TG_CHAT_ID'],'parse_mode':'HTML','text':text}
    if cfg.get('TG_THREAD_ID'): form['message_thread_id']=cfg['TG_THREAD_ID']
    code,data,raw=http_json('POST',f"https://api.telegram.org/bot{cfg['TG_BOT_TOKEN']}/sendMessage",form=form)
    return 200<=code<300 and data.get('ok',True)

def build_message(row,cfg,ng=None):
    d=parse_user_agent(str(row['user_agent'] or ''))
    sip=f"<code>{html.escape(str(ng['remote_addr']))}</code>" if ng else '未匹配到 Nginx 真实IP'
    nlines='' if not ng else f"\nNginx路径：<code>{html.escape(mask_path(ng['path']))}</code>\nNginx状态：{html.escape(str(ng['status']))}\n响应大小：{ng['body_bytes']} B"
    return f"#订阅拉取提醒\n\n用户：<b>{html.escape(str(row['username'] or f'id={row['user_id']}'))}</b>\n用户ID：{row['user_id']}\n状态：{html.escape(str(row['status'] or ''))}\n\n来源IP：{sip}\nDB记录IP：<code>{html.escape(str(row['ip'] or ''))}</code>\n设备：{html.escape(d['client'])} / {html.escape(d['device_type'])}\n系统：{html.escape(d['os'])}\n型号：{html.escape(d['model'])}\nUA摘要：{html.escape(d['summary'])}{nlines}\n\n时间：{html.escape(fmt_time(str(row['created_at'] or ''),cfg.get('DISPLAY_TIMEZONE','local')))}\n记录ID：{row['id']}"

def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--test',action='store_true'); p.add_argument('--send-test',action='store_true');a=p.parse_args(argv)
 cfg=load_config(); conn=sqlite3.connect(cfg['PASARGUARD_DB_PATH']); conn.row_factory=sqlite3.Row
 row=conn.execute("SELECT s.id,s.user_id,s.created_at,s.user_agent,s.ip,u.username,u.status FROM user_subscription_updates s left join users u on u.id=s.user_id ORDER BY s.id DESC LIMIT 1").fetchone()
 if not row: print('no subscription updates found'); return 0
 ng=None
 if str(cfg.get('DB_MONITOR_LOOKUP_NGINX_IP','true')).lower()=='true':
    try:
      dt=datetime.strptime(str(row['created_at']).split('.')[0],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
      ng=find_matching_request(cfg.get('NGINX_ACCESS_LOG','/var/log/nginx/access.log'),dt,str(row['user_agent'] or ''),int(cfg.get('DB_MONITOR_NGINX_LOOKBACK_SECONDS','600')),set([x.strip() for x in cfg.get('DB_MONITOR_NGINX_STATUS','200,304').split(',') if x.strip()]))
    except Exception: ng=None
 text=build_message(row,cfg,ng); print(text)
 if a.send_test: return 0 if send_tg(cfg,text) else 1
 return 0
