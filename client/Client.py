import cv2
import yt_dlp
import time
import os
import signal
import sqlite3
import requests
from datetime import datetime

# ============ CẤU HÌNH ============
YOUTUBE_URL    = 'https://www.youtube.com/watch?v=oC8ttZHG50I'
SERVER_BASE    = 'http://127.0.0.1:5000'
UPLOAD_URL     = f'{SERVER_BASE}/api/images'
CONFIG_URL     = f'{SERVER_BASE}/api/config'

SAVE_FOLDER    = 'timestamp'
DB_NAME        = 'camera_metadata.db'

DEFAULT_CONFIG = {
    'capture_interval': 5,
    'jpeg_quality': 80,
    'resize_width': 854,
}
CONFIG_POLL_INTERVAL = 10
#SHOW_PREVIEW     = False
SHOW_PREVIEW = True  
PREVIEW_FPS      = 5        # Preview chỉ vẽ 5 fps (không phải 30)
UPLOAD_ENABLED   = True     # Bật upload lên server

# ============ BIẾN TOÀN CỤC ============
RUNNING = True   # Điều khiển vòng lặp, set False khi Ctrl+C

def _handle_sigint(sig, frame):
    global RUNNING
    print("\n[EXIT] Nhan Ctrl+C. Dang thoat...")
    RUNNING = False

signal.signal(signal.SIGINT, _handle_sigint)

# ============ KHỞI TẠO ============
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)
    print(f"Da tao thu muc: {SAVE_FOLDER}/")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS CameraLogs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name     TEXT,
            file_path     TEXT,
            capture_time  DATETIME,
            file_size_kb  REAL,
            uploaded      INTEGER DEFAULT 0,
            server_id     INTEGER
        )
    ''')
    conn.commit()
    conn.close()
    print("Database cuc bo san sang.")


def save_metadata(file_name, file_path, capture_time, size_kb, uploaded, server_id=None):
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''
        INSERT INTO CameraLogs (file_name, file_path, capture_time, file_size_kb, uploaded, server_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (file_name, file_path, capture_time, size_kb, int(uploaded), server_id))
    conn.commit()
    conn.close()


def fetch_config():
    try:
        r = requests.get(CONFIG_URL, timeout=3)
        r.raise_for_status()
        c = r.json()
        return {
            'capture_interval': int(c.get('capture_interval', DEFAULT_CONFIG['capture_interval'])),
            'jpeg_quality':     int(c.get('jpeg_quality',     DEFAULT_CONFIG['jpeg_quality'])),
            'resize_width':     int(c.get('resize_width',     DEFAULT_CONFIG['resize_width'])),
        }
    except Exception as e:
        print(f"[WARN] Khong lay duoc config ({e}). Dung config hien tai.")
        return None


def get_live_stream_url(youtube_url):
    ydl_opts = {
        'format': 'best[height<=480]/best',   # Giảm xuống 480p cho nhẹ
        'noplaylist': True,
        'quiet': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info['url'] if 'url' in info else info.get('formats', [info])[-1]['url']


def process_frame(frame, resize_width, jpeg_quality):
    h, w = frame.shape[:2]
    if resize_width and resize_width != w:
        new_h = int(h * resize_width / w)
        frame = cv2.resize(frame, (resize_width, new_h), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
    if not ok:
        raise RuntimeError('JPEG encode that bai')
    return frame, buf.tobytes()


def upload_image(jpg_bytes, file_name, capture_time, width, height):
    try:
        files = {'file': (file_name, jpg_bytes, 'image/jpeg')}
        data = {
            'capture_time': capture_time,
            'width':  str(width),
            'height': str(height),
        }
        r = requests.post(UPLOAD_URL, files=files, data=data, timeout=10)
        if r.status_code == 201:
            return r.json().get('id')
        print(f"[ERR] Server tra {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[ERR] Upload loi: {e}")
    return None


def open_capture(stream_url):
    """Mở stream với các tham số tối ưu cho HLS."""
    cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
    # Các tham số này giúp giảm buffer, giảm latency
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    # Timeout đọc (ms) — tránh blocking vô hạn
    os.environ['OPENCV_FFMPEG_READ_ATTEMPTS'] = '3'
    return cap


# ============ MAIN ============
def main():
    global RUNNING
    init_db()

    config = dict(DEFAULT_CONFIG)
    last_config_poll = 0
    last_preview_time = 0

    print("Dang boc tach luong YouTube...")
    try:
        stream_url = get_live_stream_url(YOUTUBE_URL)
        print("Co luong. Khoi dong OpenCV...")
    except Exception as e:
        print(f"[ERR] Loi lay luong: {e}")
        return

    while RUNNING:
        cap = open_capture(stream_url)
        if not cap.isOpened():
            print("Khong mo duoc luong. Thu lai sau 2s...")
            time.sleep(2)
            continue

        print(f"Bat dau. Config: {config}")
        last_capture = time.time()

        while RUNNING:
            # ---- 1. Đọc frame KHÔNG blocking quá lâu ----
            # grab() chỉ lấy frame khỏi buffer (nhanh)
            grabbed = cap.grab()

            if not grabbed:
                print("Mat luong. Ket noi lai...")
                try:
                    stream_url = get_live_stream_url(YOUTUBE_URL)
                except Exception as e:
                    print(f"   -> loi: {e}")
                break

            now = time.time()

            # ---- 2. Polling config ----
            if now - last_config_poll >= CONFIG_POLL_INTERVAL:
                new_cfg = fetch_config()
                if new_cfg and new_cfg != config:
                    print(f"[POLL] Cap nhat config: {config} -> {new_cfg}")
                    config = new_cfg
                last_config_poll = now

            # ---- 3. Đến chu kỳ chụp → retrieve frame + lưu + upload ----
            if now - last_capture >= config['capture_interval']:
                ret, frame = cap.retrieve()
                if not ret:
                    last_capture = now
                    continue

                dt = datetime.now()
                ts_file = dt.strftime('%Y%m%d_%H%M%S')
                ts_db   = dt.strftime('%Y-%m-%d %H:%M:%S')

                file_name = f"cam_{ts_file}.jpg"
                file_path = os.path.join(SAVE_FOLDER, file_name)

                frame_out, jpg_bytes = process_frame(
                    frame, config['resize_width'], config['jpeg_quality']
                )
                h_out, w_out = frame_out.shape[:2]

                with open(file_path, 'wb') as f:
                    f.write(jpg_bytes)
                size_kb = round(len(jpg_bytes) / 1024, 2)

                server_id = None
                if UPLOAD_ENABLED:
                    server_id = upload_image(jpg_bytes, file_name, ts_db, w_out, h_out)

                save_metadata(file_name, file_path, ts_db, size_kb,
                              uploaded=(server_id is not None),
                              server_id=server_id)

                tag = f"OK server_id={server_id}" if server_id else "chua upload"
                print(f"[SAVE] {file_name} | {size_kb} KB | {w_out}x{h_out} | {tag}")

                last_capture = now

            # ---- 4. Preview giới hạn fps (nếu bật) ----
            if SHOW_PREVIEW and (now - last_preview_time) >= (1.0 / PREVIEW_FPS):
                ret, frame = cap.retrieve()
                if ret:
                    disp = cv2.resize(frame, (640, 360))  # nhỏ hơn cho nhẹ
                    cv2.imshow("Client - Camera Da Nang", disp)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("Nhan q. Thoat...")
                        RUNNING = False

                # Kiểm tra user bấm X đóng cửa sổ chưa
                try:
                    if cv2.getWindowProperty("Client - Camera Da Nang",
                                             cv2.WND_PROP_VISIBLE) < 1:
                        print("Cua so da dong. Thoat...")
                        RUNNING = False
                except cv2.error:
                    pass

                last_preview_time = now

        cap.release()

    # Cleanup
    cv2.destroyAllWindows()
    print("[EXIT] Da giai phong tai nguyen.")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[EXIT] KeyboardInterrupt")
    finally:
        cv2.destroyAllWindows()