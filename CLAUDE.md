# CLAUDE.md

Hướng dẫn cho Claude Code (và các AI agent khác) khi làm việc trong repo này.
**Đọc thêm [PROGRESS.md](PROGRESS.md)** để biết tiến trình hiện tại, việc đang dở. Cập nhật PROGRESS.md ở cuối mỗi phiên làm việc.

**Nhật ký theo chức năng — [docs/chuc-nang/](docs/chuc-nang/README.md)**: mỗi chức năng một file `<mã>.md` (file code thuộc chức năng, lỗi tồn tại, nhật ký thay đổi).
- Trước khi sửa: đọc file `.md` của chức năng đó (lỗi đã biết, lần sửa trước).
- **Sau mỗi lần sửa code, tự cập nhật** file `.md` tương ứng theo "Quy tắc cập nhật" trong [docs/chuc-nang/README.md](docs/chuc-nang/README.md) và commit cùng với code — không cần người dùng nhắc.

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
python Server.py      # đọc MYSQL_PORT / MYSQL_PASSWORD... từ server/.env (không commit; mẫu: .env.example)
# Biến môi trường đặt trong terminal được ưu tiên hơn .env
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

Mỗi chức năng một file — sửa lỗi chức năng nào thì vào đúng file đó (bảng "Cấu trúc thư mục" trong README.md).

### Client (`client/`)
- `Client.py`: chỉ khởi động — đọc tham số, tạo 3 luồng + luồng chính (preview), dừng khi có tín hiệu.
  - `capture_thread.py` — `CaptureThread` (producer): đọc frame, lưu file ảnh **atomic** (ghi file tạm → `os.replace`), ghi `LocalStore`, đẩy id vào `queue.Queue` có giới hạn.
  - `upload_thread.py` — `UploadThread` (consumer): gửi multipart lên `POST /api/images`, retry; định kỳ quét ảnh `pending` trong DB để **gửi bù** khi mất mạng.
  - `config_thread.py` — `ConfigThread`: mỗi `config_poll_interval` giây gọi `GET /api/config?client_id=...`, cập nhật `SharedConfig` (`shared_config.py`, có `threading.Lock`).
  - Dừng bằng `threading.Event` khi nhận SIGINT/SIGTERM.
  - `settings.py`: đường dẫn, `DEFAULT_SETTINGS`, `load_settings()`, log. Thứ tự ưu tiên cấu hình: `DEFAULT_SETTINGS` < `client_config.json` < biến môi trường `CAMERA_URL` < tham số dòng lệnh.
- `video_source.py`: lớp `VideoSource` (OpenCV; YouTube được phân giải URL bằng yt-dlp; RTSP ép TCP).
- `local_store.py`: SQLite WAL `client/data/client.db`, vừa là kho metadata vừa là hàng đợi gửi bù. Mỗi thao tác mở connection riêng (không chia sẻ giữa luồng).

### Server (`server/`)
- `Server.py` chỉ tạo Flask app và đăng ký 4 Blueprint: `routes/images.py` (`/api/images…`, `/uploads/…`), `routes/config.py` (`/api/config…`), `routes/monitor.py` (`/api/stats`, `/api/clients`), `routes/web.py` (các trang HTML).
- Module dùng chung: `settings.py` (đường dẫn, `MYSQL_CONFIG`, `CONFIG_LIMITS`, `log`), `timeutil.py` (thời gian), `db.py` (`get_db`, `init_db`, `to_json`, `touch_client`), `storage.py` (`cleanup_old_images`, `remove_file`, `looks_like_image`). Import kiểu tuyệt đối (`from db import get_db`) — chạy từ thư mục `server/`.
- Mỗi request mở **một kết nối MySQL riêng** (`get_db()`, `DictCursor`) → an toàn với `threaded=True`.
- `init_db()` (trong `db.py`) được `Server.py` gọi khi import: tạo database, tạo bảng, **tự thêm cột thiếu / nâng `DATETIME` → `DATETIME(3)`** cho DB cũ (qua `information_schema`). Đổi schema thì sửa cả `init_db()`, `schema.sql` và `migrate_sqlite_to_mysql.py`.
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
- Mỗi chức năng làm trên một nhánh riêng tách từ `feature/multithread-client`, xong thì `git merge --no-ff` về: `refactor/<phần>` khi tái cấu trúc, `fix/<chức-năng>` khi sửa lỗi, `feature/<tên>` khi thêm tính năng. Tên chức năng theo file: `server-core`, `server-images`, `server-config`, `server-monitor`, `server-web`, `client-core`, `client-source`, `client-store`, `client-capture`, `client-upload`, `client-config` (danh sách đầy đủ: [docs/chuc-nang/](docs/chuc-nang/README.md)).
- Commit message viết tiếng Việt, ngắn gọn (xem `git log`).
- Không commit dữ liệu chạy thử: ảnh, `*.db`, log (xem `.gitignore`).
