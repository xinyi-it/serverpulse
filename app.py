import psutil
import platform
import time
import threading
import subprocess
from datetime import datetime
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# 访客追踪 - 纯内存，不落盘
visitors = {}  # ip -> {first_seen, last_seen, city, isp}
VISITOR_TIMEOUT = 300  # 5分钟无活动视为离开
geo_cache = {}  # ip -> {city, isp, country}
geo_lock = threading.Lock()

def get_geo_info(ip):
    """查询IP地理位置和运营商（用curl，比urllib更稳定）"""
    if ip in geo_cache:
        return geo_cache[ip]
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '5',
             f'https://ipinfo.io/{ip}/json'],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            info = {
                'country': data.get('country', '未知'),
                'city': data.get('city', '未知'),
                'isp': data.get('org', '未知').replace('AS', '').strip()
            }
            if info['city'] != '未知':
                with geo_lock:
                    geo_cache[ip] = info
            return info
    except Exception as e:
        print(f'[ServerPulse] 地理位置查询失败 {ip}: {e}')
    return {'country': '未知', 'city': '未知', 'isp': '未知'}

def track_visitor(ip):
    """记录访客活动"""
    now = time.time()
    if ip not in visitors:
        geo = get_geo_info(ip)
        visitors[ip] = {
            'first_seen': now,
            'last_seen': now,
            'city': geo['city'],
            'isp': geo['isp'],
            'country': geo['country']
        }
    else:
        visitors[ip]['last_seen'] = now
        # 如果之前查询失败，重试
        if visitors[ip].get('city') == '未知':
            geo = get_geo_info(ip)
            if geo['city'] != '未知':
                visitors[ip]['city'] = geo['city']
                visitors[ip]['isp'] = geo['isp']
                visitors[ip]['country'] = geo['country']

def get_active_visitors():
    """获取当前在线访客列表"""
    now = time.time()
    active = {}
    for ip, info in visitors.items():
        if now - info['last_seen'] <= VISITOR_TIMEOUT:
            active[ip] = {
                'city': info['city'],
                'isp': info['isp'],
                'country': info['country'],
                'first_seen': datetime.fromtimestamp(info['first_seen']).strftime('%H:%M:%S'),
                'last_seen': datetime.fromtimestamp(info['last_seen']).strftime('%H:%M:%S'),
                'duration': int(now - info['first_seen'])
            }
    # 清理超时访客
    expired = [ip for ip, info in visitors.items() if now - info['last_seen'] > VISITOR_TIMEOUT]
    for ip in expired:
        del visitors[ip]
    return active

def get_system_info():
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天 {hours}小时 {minutes}分钟"
    
    return {
        'hostname': platform.node(),
        'os': f"{platform.system()} {platform.release()}",
        'python_version': platform.python_version(),
        'uptime': uptime_str,
        'boot_time': datetime.fromtimestamp(boot_time).strftime('%Y-%m-%d %H:%M:%S')
    }

def get_stats():
    cpu_percent = psutil.cpu_percent(interval=0)
    cpu_per_core = psutil.cpu_percent(interval=0, percpu=True)
    
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    disk = psutil.disk_usage('/')
    
    net_io = psutil.net_io_counters()
    
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username']):
        try:
            pinfo = proc.info
            if pinfo['cpu_percent'] is not None:
                processes.append({
                    'pid': pinfo['pid'],
                    'name': pinfo['name'],
                    'cpu': pinfo['cpu_percent'],
                    'memory': round(pinfo['memory_percent'], 1) if pinfo['memory_percent'] else 0,
                    'user': pinfo['username'] or 'N/A'
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    processes.sort(key=lambda x: x['cpu'], reverse=True)
    top_processes = processes[:10]
    
    return {
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'cpu': {
            'total': cpu_percent,
            'cores': cpu_per_core,
            'count': psutil.cpu_count(),
            'freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        },
        'memory': {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent,
            'swap_total': swap.total,
            'swap_used': swap.used,
            'swap_percent': swap.percent
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent
        },
        'network': {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        },
        'processes': top_processes,
        'system': get_system_info()
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    # 记录访客
    visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if visitor_ip and visitor_ip != '127.0.0.1':
        track_visitor(visitor_ip)
    stats = get_stats()
    return jsonify(stats)

@app.route('/api/visitors')
def api_visitors():
    return jsonify(get_active_visitors())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)