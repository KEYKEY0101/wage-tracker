# -*- coding: utf-8 -*-
# 工資記錄計算程式 啟動器
# 功能：本機伺服器 + 二維碼、UPnP 路由器連接埠轉發（外網）、密碼登入與鎖定、開機自動啟動
# 資料集中存在電腦（wage_data.json），手機/電腦看到同一份記錄

import os
import sys
import json
import time
import hmac
import socket
import struct
import secrets
import threading
import subprocess
import webbrowser
import urllib.request
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import messagebox
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import quote, urlparse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_NAME = '工資記錄計算程式.html'
PORT = 8899
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
DEFAULT_PASSWORD = '123456'  # 首次執行會產生 config.json，請在裡面改成自己的密碼
MAX_FAILS_PER_ROUND = 5
TEMP_LOCK_SECONDS = 5 * 60

DATA_FILE = os.path.join(APP_DIR, 'wage_data.json')
AUTH_FILE = os.path.join(APP_DIR, 'auth_state.json')
STARTUP_DIR = os.path.join(os.environ.get('APPDATA', ''),
                           r'Microsoft\Windows\Start Menu\Programs\Startup')
VBS_PATH = os.path.join(STARTUP_DIR, '工資記錄計算程式啟動器.vbs')

_lock = threading.Lock()
_tokens = {}  # token -> 最後使用時間（存檔於 tokens.json，重開機仍有效）
TOKENS_FILE = os.path.join(APP_DIR, 'tokens.json')
TOKEN_TTL = 30 * 24 * 3600  # 超過 30 天沒使用才需重新輸入密碼（每次使用自動續期）


# ---------- 資料存取 ----------

def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def get_data():
    with _lock:
        return load_json(DATA_FILE, {'settings': None, 'records': {}})


def set_data(obj):
    with _lock:
        save_json(DATA_FILE, {'settings': obj.get('settings'),
                              'records': obj.get('records', {})})


# 啟動時載回已登入裝置的憑證（重開機後不用重新輸入密碼）
_tokens.update({t: c for t, c in load_json(TOKENS_FILE, {}).items()
                if isinstance(c, (int, float))})

# 密碼存在 config.json（不隨程式碼公開）；檔案不存在時自動建立
_cfg = load_json(CONFIG_FILE, {})
if 'password' not in _cfg:
    _cfg['password'] = DEFAULT_PASSWORD
    try:
        save_json(CONFIG_FILE, _cfg)
    except OSError as e:
        print('無法建立 config.json:', e)
PASSWORD = str(_cfg['password'])


# ---------- 登入鎖定 ----------
# 規則：連續錯 5 次 → 暫時鎖 5 分鐘；解鎖後再錯 5 次（累計 10 次）→ 鎖死，需在電腦按「解鎖」

def get_auth_state():
    with _lock:
        return load_json(AUTH_FILE, {'fails': 0, 'locked_until': 0, 'hard_locked': False})


def set_auth_state(st):
    with _lock:
        save_json(AUTH_FILE, st)


def reset_fails():
    set_auth_state({'fails': 0, 'locked_until': 0, 'hard_locked': False})


def reset_auth_state():
    """電腦端「解鎖」用：重設錯誤次數並登出所有裝置"""
    reset_fails()
    with _lock:
        _tokens.clear()
        save_json(TOKENS_FILE, _tokens)


def check_login(password):
    """回傳 (http_status, response_dict)"""
    st = get_auth_state()
    now = time.time()

    if st.get('hard_locked'):
        return 423, {'error': 'hard_locked'}
    if now < st.get('locked_until', 0):
        return 423, {'error': 'locked', 'seconds': int(st['locked_until'] - now)}

    if hmac.compare_digest(str(password), PASSWORD):
        reset_fails()
        token = secrets.token_urlsafe(32)
        with _lock:
            _tokens[token] = now
            save_json(TOKENS_FILE, _tokens)
        return 200, {'ok': True, 'token': token}

    st['fails'] = st.get('fails', 0) + 1
    if st['fails'] >= MAX_FAILS_PER_ROUND * 2:
        st['hard_locked'] = True
        set_auth_state(st)
        return 423, {'error': 'hard_locked'}
    if st['fails'] == MAX_FAILS_PER_ROUND:
        # 第一輪錯滿 5 次 → 暫時鎖 5 分鐘；第二輪錯滿（累計 10 次）→ 上面鎖死
        st['locked_until'] = now + TEMP_LOCK_SECONDS
        set_auth_state(st)
        return 423, {'error': 'locked', 'seconds': TEMP_LOCK_SECONDS}
    set_auth_state(st)
    limit = MAX_FAILS_PER_ROUND if st['fails'] < MAX_FAILS_PER_ROUND else MAX_FAILS_PER_ROUND * 2
    return 401, {'error': 'wrong', 'remaining': limit - st['fails']}


def check_token(token):
    now = time.time()
    with _lock:
        expired = [t for t, c in _tokens.items() if now - c > TOKEN_TTL]
        for t in expired:
            del _tokens[t]
        if token not in _tokens:
            if expired:
                save_json(TOKENS_FILE, _tokens)
            return False
        # 滑動續期：有使用就延長 30 天；時間戳每小時最多寫檔一次
        if now - _tokens[token] > 3600 or expired:
            _tokens[token] = now
            save_json(TOKENS_FILE, _tokens)
        return True


# ---------- HTTP 伺服器 ----------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_DIR, **kwargs)

    def log_message(self, format, *args):
        pass

    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def read_body_json(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length <= 0 or length > 10 * 1024 * 1024:
                return None
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, OSError):
            return None

    def authed(self):
        return check_token(self.headers.get('X-Token', ''))

    def do_GET(self):
        if self.path == '/api/data':
            if not self.authed():
                return self.send_json(401, {'error': 'auth'})
            return self.send_json(200, get_data())
        if self.path == '/api/ping':
            return self.send_json(200, {'ok': self.authed()})
        if self.path in ('/', '/index.html'):
            self.path = '/' + quote(HTML_NAME)
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/login':
            body = self.read_body_json() or {}
            status, resp = check_login(body.get('password', ''))
            return self.send_json(status, resp)
        if self.path == '/api/data':
            if not self.authed():
                return self.send_json(401, {'error': 'auth'})
            body = self.read_body_json()
            if not isinstance(body, dict):
                return self.send_json(400, {'error': 'bad_request'})
            set_data(body)
            return self.send_json(200, {'ok': True})
        return self.send_json(404, {'error': 'not_found'})


def start_server():
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------- 網路位址 ----------

def get_lan_ip():
    # 收集本機所有 IPv4，優先選家用區網 192.168.x.x，避免選到 VPN 位址
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    ips.discard('127.0.0.1')
    for prefix in ('192.168.', '10.', '172.'):
        for ip in sorted(ips):
            if ip.startswith(prefix):
                return ip
    return next(iter(ips), '127.0.0.1')


# ---------- NAT-PMP 連接埠轉發（參考 qr_tool 的做法，此路由器實測支援） ----------

def natpmp_map(lan_ip):
    """用 NAT-PMP 請路由器開埠，成功回傳公網 IP，失敗拋例外"""
    gw = lan_ip.rsplit('.', 1)[0] + '.1'

    def req(payload, sz):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        try:
            s.sendto(payload, (gw, 5351))
            return s.recvfrom(sz + 16)[0]
        finally:
            s.close()

    d = req(struct.pack('!BB', 0, 0), 12)
    if struct.unpack('!BBHI', d[:8])[2] != 0:
        raise RuntimeError('公網 IP 查詢失敗')
    wan = '.'.join(str(b) for b in d[8:12])
    d = req(struct.pack('!BBHHHI', 0, 2, 0, PORT, PORT, 7200), 16)
    result = struct.unpack('!BBHIHHI', d[:16])[2]
    if result != 0:
        raise RuntimeError(f'路由器拒絕開埠 (result={result})')
    return wan


_renew_started = False


def start_natpmp_renew(lan_ip):
    """路由器租約 2 小時到期，每 50 分鐘續約一次"""
    global _renew_started
    if _renew_started:
        return
    _renew_started = True

    def loop():
        while True:
            time.sleep(3000)
            try:
                natpmp_map(lan_ip)
            except Exception as e:
                print('NAT-PMP 續約失敗:', e)

    threading.Thread(target=loop, daemon=True).start()


def setup_external(lan_ip):
    """先試 NAT-PMP，失敗再試 UPnP。回傳 (external_ip 或 None, 訊息)"""
    try:
        wan = natpmp_map(lan_ip)
        start_natpmp_renew(lan_ip)
        if _is_private_ip(wan):
            return wan, (f'路由器對外 IP 是內部位址（{wan}），'
                         'ISP 沒有給公網 IP，外網可能連不上')
        return wan, '外網轉發設定成功'
    except Exception:
        return upnp_setup(lan_ip)


# ---------- UPnP 連接埠轉發（備援） ----------

def upnp_setup(lan_ip):
    """向路由器申請 8899 轉發，回傳 (external_ip 或 None, 訊息)"""
    try:
        location = _ssdp_discover()
        if not location:
            return None, '找不到支援 UPnP 的路由器（路由器可能未開啟 UPnP）'
        control_url, service_type = _find_wan_service(location)
        if not control_url:
            return None, '路由器不支援連接埠轉發服務'
        _soap(control_url, service_type, 'AddPortMapping', {
            'NewRemoteHost': '',
            'NewExternalPort': str(PORT),
            'NewProtocol': 'TCP',
            'NewInternalPort': str(PORT),
            'NewInternalClient': lan_ip,
            'NewEnabled': '1',
            'NewPortMappingDescription': 'WageApp',
            'NewLeaseDuration': '0',
        })
        xml_resp = _soap(control_url, service_type, 'GetExternalIPAddress', {})
        ext_ip = None
        m = ET.fromstring(xml_resp)
        for el in m.iter():
            if el.tag.endswith('NewExternalIPAddress'):
                ext_ip = (el.text or '').strip()
        if not ext_ip:
            return None, '已設定轉發，但無法取得對外 IP'
        if _is_private_ip(ext_ip):
            return ext_ip, ('路由器對外 IP 是內部位址（' + ext_ip +
                            '），代表 ISP 沒有給公網 IP，外網可能連不上')
        return ext_ip, '外網轉發設定成功'
    except Exception as e:
        return None, f'UPnP 設定失敗：{e}'


def _is_private_ip(ip):
    if ip.startswith(('10.', '192.168.', '169.254.')):
        return True
    if ip.startswith('172.'):
        try:
            second = int(ip.split('.')[1])
            return 16 <= second <= 31
        except (ValueError, IndexError):
            return False
    if ip.startswith('100.'):
        try:
            second = int(ip.split('.')[1])
            return 64 <= second <= 127  # CGNAT
        except (ValueError, IndexError):
            return False
    return False


def _ssdp_discover(timeout=3):
    msg = ('M-SEARCH * HTTP/1.1\r\n'
           'HOST: 239.255.255.250:1900\r\n'
           'MAN: "ssdp:discover"\r\n'
           'MX: 2\r\n'
           'ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(msg.encode(), ('239.255.255.250', 1900))
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _ = s.recvfrom(65507)
            except socket.timeout:
                break
            for line in data.decode(errors='ignore').split('\r\n'):
                if line.lower().startswith('location:'):
                    return line.split(':', 1)[1].strip()
    finally:
        s.close()
    return None


def _find_wan_service(location):
    with urllib.request.urlopen(location, timeout=5) as r:
        desc = r.read()
    base = urlparse(location)
    root = ET.fromstring(desc)
    ns = {'d': 'urn:schemas-upnp-org:device-1-0'}
    for service in root.iter('{urn:schemas-upnp-org:device-1-0}service'):
        stype = service.findtext('d:serviceType', '', ns)
        if 'WANIPConnection' in stype or 'WANPPPConnection' in stype:
            curl = service.findtext('d:controlURL', '', ns)
            if curl.startswith('http'):
                return curl, stype
            return f'{base.scheme}://{base.netloc}{curl}', stype
    return None, None


def _soap(control_url, service_type, action, args):
    args_xml = ''.join(f'<{k}>{v}</{k}>' for k, v in args.items())
    body = (f'<?xml version="1.0"?>'
            f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{service_type}">{args_xml}</u:{action}>'
            f'</s:Body></s:Envelope>').encode('utf-8')
    req = urllib.request.Request(control_url, data=body, headers={
        'Content-Type': 'text/xml; charset="utf-8"',
        'SOAPAction': f'"{service_type}#{action}"',
    })
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read()


# ---------- 開機自動啟動 ----------

def is_autostart():
    return os.path.exists(VBS_PATH)


def set_autostart(enabled):
    if enabled:
        pyw = sys.executable
        if pyw.lower().endswith('python.exe'):
            candidate = pyw[:-len('python.exe')] + 'pythonw.exe'
            if os.path.exists(candidate):
                pyw = candidate
        script = os.path.abspath(__file__)
        content = ('Set W = CreateObject("WScript.Shell")\r\n'
                   f'W.Run """{pyw}"" ""{script}""", 0, False\r\n')
        # WSH 支援 UTF-16（含 BOM）的 .vbs，中文路徑不會亂碼
        with open(VBS_PATH, 'w', encoding='utf-16') as f:
            f.write(content)
    else:
        if os.path.exists(VBS_PATH):
            os.remove(VBS_PATH)


# ---------- 二維碼 ----------

def get_qrcode_module():
    try:
        import qrcode
        return qrcode
    except ImportError:
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'qrcode'],
                           creationflags=flags, timeout=120)
            import qrcode
            return qrcode
        except Exception as e:
            print('安裝 qrcode 失敗:', e)
            return None


def draw_qr(canvas, url):
    canvas.delete('all')
    qrcode = get_qrcode_module()
    if qrcode is None:
        canvas.create_text(150, 150, text='無法產生二維碼\n請手動在手機輸入下方網址',
                           fill='#d33', font=('Microsoft JhengHei', 11), justify='center')
        return
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    size = 300
    cell = size / n
    canvas.create_rectangle(0, 0, size, size, fill='white', outline='white')
    for y, row in enumerate(matrix):
        for x, v in enumerate(row):
            if v:
                canvas.create_rectangle(x * cell, y * cell,
                                        (x + 1) * cell, (y + 1) * cell,
                                        fill='black', outline='black')


# ---------- GUI ----------

def run_gui(server, lan_url):
    root = tk.Tk()
    root.title('工資記錄計算程式 啟動器')
    root.resizable(False, False)
    root.configure(bg='white')

    tk.Label(root, text='💰 工資記錄計算程式', bg='white',
             font=('Microsoft JhengHei', 14, 'bold')).pack(pady=(14, 2))

    state = {'ext_url': None, 'current': lan_url}

    mode_frame = tk.Frame(root, bg='white')
    mode_frame.pack()
    mode_var = tk.StringVar(value='lan')

    canvas = tk.Canvas(root, width=300, height=300, bg='white', highlightthickness=0)
    canvas.pack(padx=20, pady=8)
    draw_qr(canvas, lan_url)

    url_box = tk.Entry(root, font=('Consolas', 11), justify='center', width=36,
                       relief='solid', bd=1)

    def show_url(url):
        state['current'] = url
        draw_qr(canvas, url)
        url_box.configure(state='normal')
        url_box.delete(0, 'end')
        url_box.insert(0, url)
        url_box.configure(state='readonly')

    def on_mode():
        if mode_var.get() == 'ext' and state['ext_url']:
            show_url(state['ext_url'])
        else:
            show_url(lan_url)

    tk.Radiobutton(mode_frame, text='內網（同 Wi-Fi）', variable=mode_var, value='lan',
                   command=on_mode, bg='white', font=('Microsoft JhengHei', 10)).pack(side='left')
    ext_radio = tk.Radiobutton(mode_frame, text='外網（任何網路）', variable=mode_var, value='ext',
                               command=on_mode, bg='white', state='disabled',
                               font=('Microsoft JhengHei', 10))
    ext_radio.pack(side='left')

    show_url(lan_url)
    url_box.pack(pady=(0, 4))

    ext_status = tk.Label(root, text='正在向路由器申請外網轉發…', bg='white',
                          fg='#888', font=('Microsoft JhengHei', 9))
    ext_status.pack()

    def upnp_worker():
        ext_ip, msg = setup_external(get_lan_ip())
        def apply():
            if ext_ip and not _is_private_ip(ext_ip):
                state['ext_url'] = f'http://{ext_ip}:{PORT}/'
                ext_radio.configure(state='normal')
                ext_status.configure(text=f'外網：{msg}', fg='#0a7d40')
            else:
                ext_status.configure(text=f'外網：{msg}', fg='#c07000')
        root.after(0, apply)

    threading.Thread(target=upnp_worker, daemon=True).start()

    def open_local():
        webbrowser.open(f'http://localhost:{PORT}/')

    tk.Button(root, text='在電腦瀏覽器開啟', font=('Microsoft JhengHei', 10),
              command=open_local, width=20).pack(pady=(6, 6))

    # 登入鎖定狀態 + 解鎖
    lock_frame = tk.Frame(root, bg='white')
    lock_frame.pack(pady=(0, 4))
    lock_label = tk.Label(lock_frame, text='', bg='white', font=('Microsoft JhengHei', 10))
    lock_label.pack(side='left', padx=(0, 8))

    def do_unlock():
        reset_auth_state()
        refresh_lock()
        messagebox.showinfo('解鎖', '已解除鎖定並重設錯誤次數，所有裝置需重新輸入密碼登入。')

    unlock_btn = tk.Button(lock_frame, text='解鎖', font=('Microsoft JhengHei', 10),
                           command=do_unlock)

    def refresh_lock():
        st = get_auth_state()
        now = time.time()
        if st.get('hard_locked'):
            lock_label.configure(text='登入狀態：已鎖死（密碼錯誤太多次）', fg='#c00')
            unlock_btn.pack(side='left')
        elif now < st.get('locked_until', 0):
            remain = int(st['locked_until'] - now)
            lock_label.configure(text=f'登入狀態：暫時鎖定中（剩 {remain // 60}分{remain % 60:02d}秒）',
                                 fg='#c07000')
            unlock_btn.pack(side='left')
        else:
            fails = st.get('fails', 0)
            extra = f'（已錯 {fails} 次）' if fails else ''
            lock_label.configure(text=f'登入狀態：正常{extra}', fg='#0a7d40')
            unlock_btn.pack_forget()
        root.after(2000, refresh_lock)

    refresh_lock()

    auto_var = tk.BooleanVar(value=is_autostart())

    def toggle_auto():
        try:
            set_autostart(auto_var.get())
        except Exception as e:
            messagebox.showerror('錯誤', f'設定開機自動啟動失敗：{e}')
            auto_var.set(is_autostart())

    tk.Checkbutton(root, text='開機自動啟動（重新開機後自動開啟本程式）',
                   variable=auto_var, command=toggle_auto, bg='white',
                   font=('Microsoft JhengHei', 10)).pack(pady=(0, 4))

    tk.Label(root, text='關閉此視窗後手機將無法連線。\n'
                        '第一次使用如出現 Windows 防火牆詢問，請按「允許存取」。',
             bg='white', fg='#888', font=('Microsoft JhengHei', 9),
             justify='center').pack(pady=(0, 12))

    def on_close():
        server.shutdown()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', on_close)
    root.mainloop()


def main():
    try:
        server = start_server()
    except OSError:
        if '--headless' not in sys.argv:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo('工資記錄計算程式',
                                f'啟動器可能已在執行中（埠 {PORT} 已被使用）。\n'
                                f'請直接開啟 http://localhost:{PORT}/')
            root.destroy()
        else:
            print(f'埠 {PORT} 已被使用')
        return

    lan_url = f'http://{get_lan_ip()}:{PORT}/'

    if '--headless' in sys.argv:
        print('serving at', lan_url)
        ext_ip, msg = setup_external(get_lan_ip())
        print('外網:', msg, ext_ip or '')
        threading.Event().wait()
    else:
        run_gui(server, lan_url)


if __name__ == '__main__':
    main()
