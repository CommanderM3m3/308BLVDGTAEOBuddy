import sys
import subprocess
import importlib
from datetime import datetime

required_libraries = {
    'cv2': 'opencv-python',
    'numpy': 'numpy',
    'flask': 'flask',
    'mss': 'mss',
    'zeroconf': 'zeroconf',
    'qrcode': 'qrcode[pil]',
    'psutil': 'psutil'
}

for module_name, package_name in required_libraries.items():
    try:
        import importlib.util
        if module_name == 'qrcode':
            importlib.import_module('qrcode')
        else:
            importlib.import_module(module_name)
    except ImportError:
        print(f"Library '{module_name}' not found. Installing '{package_name}'...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])

import os
import threading
import time
import socket
import json
import urllib.request
import io
import base64
import webbrowser
import psutil
import cv2
import numpy as np
from flask import Flask, Response, render_template_string, jsonify
from mss import MSS
from zeroconf import ServiceInfo, Zeroconf
import qrcode

app = Flask(__name__)
current_process = psutil.Process(os.getpid())
current_process.cpu_percent(interval=None)

CURRENT_VERSION = "v1.0.0"
GITHUB_REPO = "CommanderM3m3/308BLVDGTAEOBuddy"

def check_for_updates():
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(
            api_url, 
            headers={'User-Agent': 'GTA-Vault-Hack-Buddy-Updater'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            latest_version = data.get("tag_name")
            release_url = data.get("html_url")
            
            if latest_version and latest_version != CURRENT_VERSION:
                print(f"\n[!] Update available! ({CURRENT_VERSION} -> {latest_version})")
                print(f"[!] Download the latest version here: {release_url}\n")
            else:
                print(f"[*] Running latest version ({CURRENT_VERSION}).")
    except Exception as e:
        print("[*] Could not check for updates (offline or network error).")

latest_frame = None
frame_lock = threading.Lock()

log_messages = []
log_lock = threading.Lock()

def add_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    with log_lock:
        log_messages.append(formatted_msg)
        if len(log_messages) > 100:
            log_messages.pop(0)

add_log("Initializing script and loading assets...")

script_dir = os.path.dirname(os.path.abspath(__file__))
ref_dir = os.path.join(script_dir, 'Reference Images')
os.makedirs(ref_dir, exist_ok=True)

header_path = os.path.join(ref_dir, 'FingerprintScannerHackFinder.png')
header_template = cv2.imread(header_path, cv2.IMREAD_GRAYSCALE)
if header_template is None:
    add_log(f"CRITICAL ERROR: Could not load header template from {header_path}")
    raise ValueError(f"Could not load header template from: {header_path}")
t_h, t_w = header_template.shape[:2]
add_log("Fingerprint header template loaded successfully.")

fingerprints = {}
for i in range(1, 5):
    main_path = os.path.join(ref_dir, f'Fingerprint{i}.png')
    main_img = cv2.imread(main_path, cv2.IMREAD_GRAYSCALE)
    
    parts = []
    for j in range(1, 5):
        part_path = os.path.join(ref_dir, f'Fingerprint{i}_{j}.png')
        part_img = cv2.imread(part_path, cv2.IMREAD_GRAYSCALE)
        if part_img is not None:
            parts.append(part_img)
            
    if main_img is not None and len(parts) == 4:
        fingerprints[i] = {
            'main': main_img,
            'parts': parts
        }
        add_log(f"Loaded Fingerprint {i} with 4 quadrant components.")
    else:
        add_log(f"Warning: Fingerprint {i} files incomplete or missing.")

keypad_header_path = os.path.join(ref_dir, 'KeypadCrackerFinder.png')
keypad_header_template = cv2.imread(keypad_header_path, cv2.IMREAD_GRAYSCALE)
if keypad_header_template is None:
    add_log(f"WARNING: Could not load KeypadCrackerFinder from {keypad_header_path}")
else:
    add_log("KeypadCrackerFinder template loaded successfully.")

dot_path = os.path.join(ref_dir, 'KeypadCrackerDot.png')
dot_template = cv2.imread(dot_path, cv2.IMREAD_GRAYSCALE)
if dot_template is None:
    add_log(f"WARNING: Could not load KeypadCrackerDot from {dot_path}")
else:
    add_log("KeypadCrackerDot template loaded successfully.")

def capture_loop():
    global latest_frame
    with MSS() as sct:
        monitor = sct.monitors[1]
        monitor_region = {
            "top": monitor["top"],
            "left": monitor["left"],
            "width": monitor["width"],
            "height": monitor["height"]
        }

        scaled_header = cv2.resize(header_template, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        sh_h, sh_w = scaled_header.shape[:2]

        scaled_kp_header = cv2.resize(keypad_header_template, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) if keypad_header_template is not None else None
        kph_h, kph_w = scaled_kp_header.shape[:2] if scaled_kp_header is not None else (0, 0)

        scaled_dot = cv2.resize(dot_template, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) if dot_template is not None else None
        dh, dw = scaled_dot.shape[:2] if scaled_dot is not None else (0, 0)
        
        scaled_fingerprints = {}
        for fp_id, data in fingerprints.items():
            scaled_fingerprints[fp_id] = {
                'main': cv2.resize(data['main'], (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
                'parts': [cv2.resize(p, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) for p in data['parts']]
            }

        target_fps = 15
        frame_duration = 1.0 / target_fps
        last_logged_state = None

        persistent_dots = []
        last_detected_mode = None

        add_log("Capture loop started. Monitoring screen for minigames...")

        while True:
            t_start = time.time()
            screenshot = sct.grab(monitor_region)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            detected_mode = None

            res_fp = cv2.matchTemplate(gray_frame, scaled_header, cv2.TM_CCOEFF_NORMED)
            _, max_val_fp, _, max_loc_fp = cv2.minMaxLoc(res_fp)

            max_val_kp = 0
            max_loc_kp = (0, 0)
            if scaled_kp_header is not None:
                res_kp = cv2.matchTemplate(gray_frame, scaled_kp_header, cv2.TM_CCOEFF_NORMED)
                _, max_val_kp, _, max_loc_kp = cv2.minMaxLoc(res_kp)

            if max_val_fp > 0.8:
                detected_mode = "fingerprint"
                header_loc = max_loc_fp
                header_dims = (sh_w, sh_h)
            elif max_val_kp > 0.8:
                detected_mode = "keypad"
                header_loc = max_loc_kp
                header_dims = (kph_w, kph_h)

            if detected_mode != last_detected_mode:
                if detected_mode == "keypad":
                    persistent_dots = []
                elif detected_mode != "keypad":
                    persistent_dots = []
                last_detected_mode = detected_mode

            if detected_mode == "fingerprint":
                if last_logged_state != "fp_header":
                    add_log("Fingerprint Scanner minigame detected on screen.")
                    last_logged_state = "fp_header"

                top_left = header_loc
                bottom_right = (top_left[0] + header_dims[0], top_left[1] + header_dims[1])
                cv2.rectangle(frame, top_left, bottom_right, (0, 215, 255), 3)
                
                detected_fp = None
                highest_val = 0
                for fp_id, data in scaled_fingerprints.items():
                    m_res = cv2.matchTemplate(gray_frame, data['main'], cv2.TM_CCOEFF_NORMED)
                    _, m_val, _, _ = cv2.minMaxLoc(m_res)
                    if m_val > highest_val and m_val > 0.75:
                        highest_val = m_val
                        detected_fp = fp_id

                if detected_fp:
                    fp_state_key = f"fp_{detected_fp}"
                    if last_logged_state != fp_state_key:
                        add_log(f"Match found! Target is Fingerprint {detected_fp}")
                        last_logged_state = fp_state_key

                    cv2.putText(frame, f"TARGET: FP {detected_fp}", (30, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    target_parts = scaled_fingerprints[detected_fp]['parts']
                    for idx, scaled_part in enumerate(target_parts):
                        p_res = cv2.matchTemplate(gray_frame, scaled_part, cv2.TM_CCOEFF_NORMED)
                        _, p_val, _, p_loc = cv2.minMaxLoc(p_res)
                        if p_val > 0.75:
                            ph, pw = scaled_part.shape[:2]
                            pt1 = p_loc
                            pt2 = (p_loc[0] + pw, p_loc[1] + ph)
                            
                            overlay = frame.copy()
                            cv2.rectangle(overlay, pt1, pt2, (0, 255, 0), -1)
                            cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
                            cv2.rectangle(frame, pt1, pt2, (0, 255, 0), 2)
                            cv2.putText(frame, f"Touch {idx+1}", (pt1[0], pt1[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
                else:
                    if last_logged_state != "fp_searching":
                        add_log("Fingerprint header present, scanning for match...")
                        last_logged_state = "fp_searching"
                    cv2.putText(frame, "SEARCHING TARGET...", (30, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 2)

            elif detected_mode == "keypad":
                if last_logged_state != "kp_header":
                    add_log("Keypad Cracker minigame detected on screen.")
                    last_logged_state = "kp_header"

                top_left = header_loc
                bottom_right = (top_left[0] + header_dims[0], top_left[1] + header_dims[1])
                cv2.rectangle(frame, top_left, bottom_right, (255, 0, 0), 3)
                cv2.putText(frame, "MODE: KEYPAD CRACKER", (30, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 0), 2)

                if scaled_dot is not None:
                    k_res = cv2.matchTemplate(gray_frame, scaled_dot, cv2.TM_CCOEFF_NORMED)
                    threshold = 0.78
                    loc = np.where(k_res >= threshold)
                    
                    current_frame_dots = []
                    for pt in zip(*loc[::-1]):
                        too_close = False
                        for p_pt in current_frame_dots:
                            if abs(pt[0] - p_pt[0]) < 10 and abs(pt[1] - p_pt[1]) < 10:
                                too_close = True
                                break
                        if not too_close:
                            current_frame_dots.append(pt)

                    if len(current_frame_dots) > 0:
                        is_new_cycle = False
                        if len(persistent_dots) > 0:
                            matches_old = 0
                            for pt in current_frame_dots:
                                for saved_pt in persistent_dots:
                                    if abs(pt[0] - saved_pt[0]) < 15 and abs(pt[1] - saved_pt[1]) < 15:
                                        matches_old += 1
                            if matches_old < len(current_frame_dots) / 2:
                                is_new_cycle = True

                        if is_new_cycle or len(persistent_dots) == 0:
                            persistent_dots = []
                            add_log("New flash sequence detected, clearing old dots.")

                        for pt in current_frame_dots:
                            exists = False
                            for saved_pt in persistent_dots:
                                if abs(pt[0] - saved_pt[0]) < 15 and abs(pt[1] - saved_pt[1]) < 15:
                                    exists = True
                                    break
                            if not exists:
                                persistent_dots.append(pt)
                                add_log(f"Keypad flash tracked at coordinates: {pt}")

                for pt in persistent_dots:
                    pt1 = pt
                    pt2 = (pt[0] + dw, pt[1] + dh)
                    overlay = frame.copy()
                    cv2.rectangle(overlay, pt1, pt2, (0, 255, 0), -1)
                    cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
                    cv2.rectangle(frame, pt1, pt2, (0, 255, 0), 2)
                    cv2.putText(frame, "CODE", (pt1[0], pt1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 2)

            else:
                if last_logged_state != "waiting":
                    add_log("Waiting for minigame...")
                    last_logged_state = "waiting"

            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            frame_bytes = buffer.tobytes()

            with frame_lock:
                latest_frame = frame_bytes

            elapsed = time.time() - t_start
            if elapsed < frame_duration:
                time.sleep(frame_duration - elapsed)

def generate_frames():
    global latest_frame
    target_fps = 15
    frame_duration = 1.0 / target_fps
    while True:
        t_start = time.time()
        with frame_lock:
            if latest_frame is None:
                time.sleep(0.05)
                continue
            current_frame = latest_frame

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n')
        
        elapsed = time.time() - t_start
        if elapsed < frame_duration:
            time.sleep(frame_duration - elapsed)

@app.route('/logs')
def logs():
    with log_lock:
        return jsonify({"logs": log_messages})

@app.route('/stats')
def stats():
    try:
        cpu = current_process.cpu_percent(interval=0.0) / psutil.cpu_count()
        mem = current_process.memory_info().rss / (1024 * 1024)
        return jsonify({"cpu": round(cpu, 1), "mem": round(mem, 1)})
    except Exception:
        return jsonify({"cpu": 0.0, "mem": 0.0})

@app.route('/')
def index():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()

    url = f"http://{local_ip}:5000"
    qr_base64 = ""
    try:
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img_qr.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception:
        pass

    return render_template_string('''
        <html>
            <head>
                <title>GTA V Vault Hack Buddy</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        background-color: #5b0069;
                        display: flex;
                        flex-direction: column;
                        justify-content: flex-start;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        padding: 10px;
                        box-sizing: border-box;
                        color: white;
                        font-family: sans-serif;
                    }
                    .top-bar {
                        width: 98%;
                        max-width: 1200px;
                        display: flex;
                        justify-content: flex-end;
                        margin-bottom: 10px;
                        flex-shrink: 0;
                    }
                    .qr-btn {
                        background: #00ff88;
                        color: #000;
                        border: none;
                        padding: 10px 20px;
                        font-size: 16px;
                        font-weight: bold;
                        border-radius: 6px;
                        cursor: pointer;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                        transition: background 0.2s;
                    }
                    .qr-btn:hover {
                        background: #00cc6a;
                    }
                    #console-log {
                        background: #000;
                        color: #00ff88;
                        font-family: monospace;
                        padding: 18px;
                        margin-bottom: 20px;
                        border-radius: 8px;
                        font-size: 22px;
                        width: 98%;
                        max-width: 1200px;
                        height: 40vh;
                        overflow-y: scroll;
                        text-align: left;
                        border: 3px solid #333;
                        box-sizing: border-box;
                        line-height: 1.6;
                        -webkit-overflow-scrolling: touch;
                        flex-shrink: 0;
                    }
                    img.feed {
                        width: 98%;
                        max-width: 1200px;
                        height: auto;
                        max-height: 40vh;
                        border: 3px solid #222;
                        border-radius: 8px;
                        box-shadow: 0 0 25px rgba(0,0,0,0.6);
                        flex-shrink: 0;
                    }
                    .footer-container {
                        width: 98%;
                        max-width: 1200px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-top: 10px;
                        flex-shrink: 0;
                    }
                    .watermark {
                        font-size: 14px;
                        color: rgba(255, 255, 255, 0.6);
                        font-family: sans-serif;
                        letter-spacing: 1px;
                    }
                    .perf-stats {
                        font-size: 12px;
                        font-family: monospace;
                        color: rgba(0, 255, 136, 0.8);
                        background: rgba(0, 0, 0, 0.3);
                        padding: 4px 8px;
                        border-radius: 4px;
                    }
                    .modal-overlay {
                        display: none;
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0,0,0,0.7);
                        justify-content: center;
                        align-items: center;
                        z-index: 1000;
                    }
                    .modal-content {
                        background: #22002b;
                        padding: 30px;
                        border-radius: 12px;
                        border: 3px solid #00ff88;
                        text-align: center;
                        box-shadow: 0 0 30px rgba(0,255,136,0.4);
                        max-width: 90%;
                    }
                    .modal-content h3 {
                        margin-top: 0;
                        color: #00ff88;
                        font-size: 22px;
                    }
                    .modal-content img {
                        border-radius: 6px;
                        margin: 15px 0;
                        border: 2px solid #fff;
                    }
                    .close-btn {
                        background: #ff4444;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        font-size: 14px;
                        font-weight: bold;
                        border-radius: 4px;
                        cursor: pointer;
                        margin-top: 10px;
                    }
                    .close-btn:hover {
                        background: #cc0000;
                    }
                </style>
            </head>
            <body>
                <div class="top-bar">
                    <button class="qr-btn" onclick="openModal()">📱 Show Phone QR</button>
                </div>

                <div id="console-log">Initializing console logs...</div>
                <img class="feed" src="/video_feed">
                
                <div class="footer-container">
                    <div class="watermark">.308 Boulevard</div>
                    <div class="perf-stats">CPU: <span id="cpu-val">0.0</span>% | RAM: <span id="mem-val">0.0</span> MB</div>
                </div>

                <div id="qr-modal" class="modal-overlay" onclick="outsideClose(event)">
                    <div class="modal-content">
                        <h3>Scan to Open on Phone</h3>
                        <p style="font-size: 14px; color: #ddd;">Point your phone camera at the code below:</p>
                        <img src="data:image/png;base64,{{ qr_data }}" alt="QR Code" width="200" height="200">
                        <br>
                        <button class="close-btn" onclick="closeModal()">Close</button>
                    </div>
                </div>
                
                <video id="keep-awake-video" loop muted playsinline style="width: 1px; height: 1px; position: absolute; opacity: 0.01; pointer-events: none;">
                    <source src="data:video/mp4;base64,AAAAHGZ0eXBpc29tAAACAGlzb21pc29tYXZjMQAAAAhmcmVlAAAAG21kYXQAAABmAFUAAAAAZGF0YQAAAAE=" type="video/mp4">
                </video>

                <script>
                    let audioCtx = null;

                    function openModal() {
                        document.getElementById('qr-modal').style.display = 'flex';
                    }

                    function closeModal() {
                        document.getElementById('qr-modal').style.display = 'none';
                    }

                    function outsideClose(e) {
                        if (e.target.id === 'qr-modal') {
                            closeModal();
                        }
                    }

                    function triggerKeepAwake() {
                        const vid = document.getElementById('keep-awake-video');
                        if (vid && vid.paused) {
                            vid.play().catch(e => {});
                        }

                        if (!audioCtx) {
                            const AudioContext = window.AudioContext || window.webkitAudioContext;
                            if (AudioContext) {
                                audioCtx = new AudioContext();
                            }
                        }
                        if (audioCtx && audioCtx.state === 'suspended') {
                            audioCtx.resume();
                        }
                        if (audioCtx) {
                            try {
                                const buffer = audioCtx.createBuffer(1, 1, 22050);
                                const source = audioCtx.createBufferSource();
                                source.buffer = buffer;
                                source.connect(audioCtx.destination);
                                source.start(0);
                            } catch (e) {}
                        }
                    }

                    ['click', 'touchstart', 'mousemove', 'keydown'].forEach(evt => {
                        document.addEventListener(evt, triggerKeepAwake, {passive: true, once: true});
                    });

                    setInterval(triggerKeepAwake, 3000);

                    setInterval(async () => {
                        try {
                            let res = await fetch('/logs');
                            let data = await res.json();
                            let consoleBox = document.getElementById('console-log');
                            consoleBox.innerText = data.logs.join('\\n');
                            consoleBox.scrollTop = consoleBox.scrollHeight;
                        } catch (err) {}
                    }, 800);

                    setInterval(async () => {
                        try {
                            let res = await fetch('/stats');
                            let data = await res.json();
                            document.getElementById('cpu-val').innerText = data.cpu;
                            document.getElementById('mem-val').innerText = data.mem;
                        } catch (err) {}
                    }, 1500);
                </script>
            </body>
        </html>
    ''', qr_data=qr_base64)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    check_for_updates()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()

    url = f"http://{local_ip}:5000"

    desc = {'path': '/'}
    info = ServiceInfo(
        "_http._tcp.local.",
        "308BLVDGTAEOBuddy._http._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=5000,
        weight=0,
        priority=0,
        properties=desc,
        server="308BLVDGTAEOBuddy.local.",
    )
    
    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    
    print("\n" + "="*50)
    print(f"[*] Server Running Locally at: http://127.0.0.1:5000")
    print(f"[*] Network Access IP: {url}")
    print("="*50 + "\n")

    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:5000")).start()

    t = threading.Thread(target=capture_loop, daemon=True)
    t.start()
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    finally:
        zeroconf.unregister_service(info)
        zeroconf.close()