# CLAUDE.md

Hướng dẫn cho Claude Code (và các AI agent khác) khi làm việc trong repo này.
**Đọc thêm [PROGRESS.md](PROGRESS.md)** để biết tiến trình hiện tại, việc đang dở và các lỗi còn tồn tại. Cập nhật PROGRESS.md ở cuối mỗi phiên làm việc.

## Dự án

Đồ án PBL4 (Hệ điều hành + Mạng máy tính): truy xuất ảnh từ camera qua mạng.

- **Client** (`client/`): đọc nguồn video (RTSP / HTTP MJPEG / webcam / file / YouTube), chụp ảnh theo chu kỳ, lưu cục bộ (file + SQLite), gửi lên Server qua HTTP. Đa luồng Producer–Consumer.
- **Server** (`server/Server.py`): Flask REST API + MySQL, lưu ảnh vào `server/uploads/`, cấu hình Client từ xa, thống kê độ trễ.
- **Website** (`server/templates/`, `server/static/style.css`): gallery real-time, quản lý ảnh, cấu hình, thống kê.

Người dùng là sinh viên, giao tiếp bằng **tiếng Việt**. Comment, log, thông báo lỗi API và giao diện đều viết tiếng Việt — giữ nguyên như vậy.

## Lệnh thường dùng

```powershell
# Cài đặt
cd server; pip install -r requirements.txt      # Flask, Flask-Cors, PyMySQL, cryptography
cd client; pip install -r requirements.txt      # opencv-python, requests, yt-dlp

# Server (máy này: MySQL80 chạy ở cổng 3307, KHÔNG phải 3306)
cd server
$env:MYSQL_PORT=3307; $env:MYSQL_PASSWORD="<hỏi người dùng>"; python Server.py
# Biến khác: MYSQL_HOST, MYSQL_USER (root), MYSQL_DATABASE (pbl4_camera), PBL4_HOST, PBL4_PORT (5000), PBL4_DEBUG=1

# Chuyển dữ liệu cũ SQLite (server/server.db) → MySQL, chạy lại không bị trùng
python migrate_sqlite_to_mysql.py

# Client
cd client
python Client.py                                         # đọc client_config.json
python Client.py --source-type file --source-url video.mp4 --no-preview
```

Nếu terminal báo `UnicodeEncodeError` khi in tiếng Việt: đặt `$env:PYTHONIOENCODING="utf-8"`.

Chưa có bộ test tự động trong repo. Kiểm thử bằng cách chạy Server (cổng phụ, vd `PBL4_PORT=5055`) rồi gọi các API trong bảng REST API của [README.md](README.md); dọn dữ liệu thử (ảnh, dòng `clients`) sau khi test.

## Kiến trúc chính

### Client (`client/`)
- `Client.py`: 3 luồng + luồng chính
  - `CaptureThread` (producer): đọc frame, lưu file ảnh **atomic** (ghi file tạm → `os.replace`), ghi `LocalStore`, đẩy id vào `queue.Queue` có giới hạn.
  - `UploadThread` (consumer): gửi multipart lên `POST /api/images`, retry; định kỳ quét ảnh `pending` trong DB để **gửi bù** khi mất mạng.
  - `ConfigThread`: mỗi `config_poll_interval` giây gọi `GET /api/config?client_id=...`, cập nhật `SharedConfig` (có `threading.Lock`).
  - Dừng bằng `threading.Event` khi nhận SIGINT/SIGTERM.
  - Thứ tự ưu tiên cấu hình: `DEFAULT_SETTINGS` < `client_config.json` < biến môi trường `CAMERA_URL` < tham số dòng lệnh.
- `video_source.py`: lớp `VideoSource` (OpenCV; YouTube được phân giải URL bằng yt-dlp; RTSP ép TCP).
- `local_store.py`: SQLite WAL `client/data/client.db`, vừa là kho metadata vừa là hàng đợi gửi bù. Mỗi thao tác mở connection riêng (không chia sẻ giữa luồng).

### Server (`server/Server.py`)
- Mỗi request mở **một kết nối MySQL riêng** (`get_db()`, `DictCursor`) → an toàn với `threaded=True`.
- `init_db()` chạy khi import module: tạo database, tạo bảng, **tự thêm cột thiếu / nâng `DATETIME` → `DATETIME(3)`** cho DB cũ (qua `information_schema`). Đổi schema thì sửa cả `init_db()`, `schema.sql` và `migrate_sqlite_to_mysql.py`.
- Bảng: `images`, `config` (đúng 1 dòng id=1), `config_history`, `clients`.
- Chống nhận trùng: cùng `(client_id, client_capture_id, capture_time)` → trả lại bản ghi cũ với `duplicate: true`.
- `cleanup_old_images()` xóa ảnh cũ nhất khi vượt `config.max_images`.
- Giới hạn tham số cấu hình nằm ở `CONFIG_LIMITS`.

## Quy ước quan trọng

- **Thời gian**: lưu MySQL kiểu `DATETIME(3)` (mili giây — cần cho đo độ trễ). Ra JSON/template luôn là chuỗi ISO `YYYY-MM-DDTHH:MM:SS.mmm` qua `to_json()` / `iso()`. Template `detail.html` cắt chuỗi (`capture_time[8:10]`) nên **phải truyền chuỗi, không truyền datetime**. Dữ liệu vào đi qua `normalize_time()`.
- **SQL**: placeholder `%s` (PyMySQL), không dùng `?`; không dùng `conn.execute` (PyMySQL không có) — luôn qua `cursor`. Đọc COUNT bằng alias: `SELECT COUNT(*) AS n` rồi `['n']`.
- **Log** dùng `log = logging.getLogger('server'|'client')` (ghi `logs/*.log` xoay vòng), không dùng `print` trong Server.
- **Bảo mật**: không ghi mật khẩu MySQL / camera vào file trong repo — chỉ qua biến môi trường. Không bật `PBL4_DEBUG` khi mở ra LAN.
- Client và Server ở 2 máy phải đồng bộ đồng hồ (NTP) thì số liệu độ trễ mới đúng.

## Git

- Nhánh chính `main`; nhánh làm việc hiện tại `feature/multithread-client`. Remote: `origin`.
- Commit message viết tiếng Việt, ngắn gọn (xem `git log`).
- Không commit dữ liệu chạy thử: ảnh, `*.db`, log (xem `.gitignore`).
