import psutil
import platform
import time
from datetime import datetime
from flask import Flask, jsonify, render_template

app = Flask(__name__)

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
    return jsonify(get_stats())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)