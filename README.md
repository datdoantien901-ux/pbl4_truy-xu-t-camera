# PBL4 – Truy xuất và phân tích dữ liệu hình ảnh từ Camera qua mạng

Hệ thống gồm 3 phần:

- **Client** (`client/`): kết nối Camera (RTSP / HTTP / webcam / file / YouTube), chụp ảnh theo chu kỳ, lưu cục bộ (file + SQLite) và gửi lên Server.
- **Backend API** (`server/Server.py`): RESTful API bằng Flask + MySQL, nhận và quản lý ảnh, cấu hình Client từ xa.
- **Website** (`server/templates/`): trang ảnh trực tiếp, trang quản lý (tìm kiếm / xem / xóa), trang cấu hình, trang thống kê độ trễ có biểu đồ. Màu sắc chỉnh trong `server/static/style.css` (các biến ở đầu file).

## Kiến trúc

```
 Camera IP / iPhone ──RTSP──┐
 Webcam / file / YouTube ───┤
                            ▼
 ┌───────────────────── CLIENT (máy A) ─────────────────────┐
 │ CaptureThread ──▶ lưu file + SQLite ──▶ Queue ──▶ UploadThread ──HTTP POST──┐
 │      ▲  (producer)                     (bounded)    (consumer)              │
 │      │ cấu hình dùng chung (Lock)                                          │
 │ ConfigThread ◀──HTTP GET /api/config (mỗi 10s)───────────────┐             │
 └──────────────────────────────────────────────────────────────┼─────────────┘
                                                                │             ▼
 ┌───────────────────── SERVER (máy B) ──────────────────────────────────────────┐
 │ Flask REST API ── uploads/ + MySQL (InnoDB)                                    │
 │ Website: /  /manage  /config  /stats                                           │
 └────────────────────────────────────────────────────────────────────────────────┘
```

**Điểm chính về Hệ điều hành**

- Client chạy **đa luồng** theo mô hình Producer–Consumer: luồng chụp ảnh không bao giờ bị chặn bởi mạng chậm.
- Đồng bộ giữa các luồng bằng `threading.Lock`, `queue.Queue` (bounded buffer) và `threading.Event`.
- Bắt tín hiệu **SIGINT/SIGTERM** để dừng tuần tự các luồng và giải phóng tài nguyên.
- Ghi file **atomic**: ghi ra file tạm rồi `os.replace`, nên không để lại file hỏng khi bị tắt đột ngột.
- Client: SQLite chế độ **WAL** cho phép đọc và ghi đồng thời. Server: MySQL InnoDB (khóa theo dòng), mỗi request một kết nối riêng.

**Điểm chính về Mạng**

- Đọc luồng **RTSP** (ép dùng TCP để ổn định trên Wi-Fi).
- Upload qua **HTTP multipart/form-data**, giữ kết nối TCP (keep-alive) giữa các lần gửi.
- **Chịu lỗi mạng**: khi server tắt hoặc mất mạng, ảnh được giữ trong DB cục bộ và tự gửi bù khi có mạng lại. Server chống nhận trùng ảnh.
- Website hiển thị IP của Client và trạng thái online.

## Cấu trúc thư mục

```
client/
  Client.py           điểm khởi động: đọc tham số, tạo và nối các luồng, cửa sổ preview
  settings.py         đường dẫn, cấu hình mặc định, đọc cấu hình, log
  shared_config.py    tham số chụp dùng chung giữa các luồng (có Lock)
  capture_thread.py   luồng chụp ảnh (producer): đọc frame, nén JPEG, lưu file + SQLite
  upload_thread.py    luồng gửi ảnh (consumer): POST lên Server, retry, gửi bù
  config_thread.py    luồng lấy cấu hình + danh sách camera từ Server định kỳ
  camera_manager.py   mở / dừng luồng chụp khi admin bật / tắt camera trên Website
  video_source.py     lớp VideoSource: rtsp | http | webcam | file | youtube
  local_store.py      SQLite cục bộ, đồng thời là hàng đợi gửi bù
  client_config.json  cấu hình Client
  data/               ảnh + client.db (tự tạo, không commit)
  logs/client.log     log hoạt động (tự tạo)
server/
  Server.py           điểm khởi động: tạo Flask app, đăng ký các nhóm route
  settings.py         cấu hình (đường dẫn, MySQL, giới hạn tham số) + log
  timeutil.py         xử lý thời gian DATETIME(3) ↔ chuỗi ISO, tính độ trễ
  db.py               kết nối MySQL, tạo / nâng cấp bảng
  storage.py          file ảnh trong uploads/: kiểm tra, xóa, dọn ảnh cũ
  routes/images.py    API ảnh       /api/images..., /uploads/<file>
  routes/config.py    API cấu hình  /api/config, /api/config/history
  routes/monitor.py   API giám sát  /api/stats, /api/clients, /api/cameras
  routes/web.py       các trang web /login, /live (2 tab: video | ảnh từ Client), /ipcam, /manage, /config, /users, /account, /stats, /image/<id>
  routes/streams.py   API camera YouTube  /api/streams...
  camera_sources.py   danh sách camera Client cần chụp (camera bật "Client chụp ảnh" trên Website)
  routes/ipcams.py    API camera IP /api/ipcams..., luồng MJPEG /ipcam/<id>/stream
  ipcam.py            đọc camera IP bằng OpenCV, phát lại MJPEG (1 luồng đọc dùng chung / camera)
  routes/users.py     API tài khoản /api/me, /api/users...
  auth.py             đăng nhập + phân quyền (admin / viewer) + khóa API của Client
  youtube.py          kiểm tra / tìm livestream YouTube bằng yt-dlp
  templates/, static/ giao diện
  schema.sql          schema MySQL (db.py cũng tự tạo khi chạy)
  migrate_sqlite_to_mysql.py  chuyển dữ liệu cũ từ server.db (SQLite) sang MySQL
  uploads/            ảnh phía server
  logs/server.log     log hoạt động (tự tạo)
```

## Cài đặt

Yêu cầu Python 3.9 trở lên và MySQL 8 (hoặc MariaDB 10.5+) cho Server.

```bash
# Server
cd server
pip install -r requirements.txt

# Client
cd client
pip install -r requirements.txt
```

## Chạy

### 1. Server

```bash
cd server
python Server.py
```

- Server kết nối MySQL theo biến môi trường `MYSQL_HOST` (mặc định `localhost`), `MYSQL_PORT` (`3306`), `MYSQL_USER` (`root`), `MYSQL_PASSWORD` (rỗng), `MYSQL_DATABASE` (`pbl4_camera`). Database và các bảng tự tạo khi chạy lần đầu. Để khỏi gõ lại mỗi lần chạy: chép `server/.env.example` thành `server/.env` rồi điền cổng, mật khẩu (file `.env` không được commit). Hoặc đặt tạm trong PowerShell: `$env:MYSQL_PASSWORD="matkhau"; python Server.py` — biến đặt trong terminal được ưu tiên hơn `.env`.
- **Bảo mật** (đặt trong `server/.env`, xem `.env.example`):
  - `PBL4_API_KEY`: khóa bí mật Client phải gửi kèm (header `X-API-Key`). Đặt **giống hệt** trong `client/.env`. Sinh khóa: `python -c "import secrets; print(secrets.token_urlsafe(24))"`.
  - `PBL4_ADMIN_USER` / `PBL4_ADMIN_PASSWORD`: tài khoản admin tạo lần đầu. Để trống mật khẩu → Server sinh ngẫu nhiên và in ra màn hình.
  - `PBL4_SECRET_KEY`: khóa ký cookie đăng nhập (để trống → khởi động lại Server là phải đăng nhập lại).
- Có dữ liệu cũ trong `server.db` (SQLite)? Chạy một lần `python migrate_sqlite_to_mysql.py` để chép sang MySQL.

- Mặc định server lắng nghe `0.0.0.0:5000`, nên máy khác trong mạng LAN truy cập được qua `http://<IP-máy-server>:5000`.
- Đổi cổng: `PBL4_PORT=8000 python Server.py`. Trên Windows PowerShell: `$env:PBL4_PORT=8000; python Server.py`.
- Chế độ debug **tắt** mặc định. Chỉ bật (`PBL4_DEBUG=1`) khi chạy một mình trên máy, vì debugger của Flask cho phép chạy code từ xa.

### 2. Client

Sửa `client/client_config.json` (danh sách camera, địa chỉ server), rồi chạy:

Chép `client/.env.example` thành `client/.env` và điền `PBL4_API_KEY` **trùng với Server**. Sai hoặc thiếu khóa thì Server trả `401`; Client ghi lỗi vào log và giữ ảnh lại để gửi bù khi sửa xong khóa.

Cửa sổ xem trước chỉ để xem: **đóng cửa sổ thì Client vẫn tiếp tục chụp và gửi ảnh**; dừng Client bằng phím `q` trong cửa sổ hoặc Ctrl+C trong terminal.

**Client chụp camera nào?** Mặc định (`"cameras_from_server": true` trong `client_config.json`) Client chụp **các camera trên Website được admin bật "Client chụp ảnh"**:
- mục *Camera trực tiếp* → **chọn camera** (quản trị viên chọn camera nào thì Client chụp camera đó; camera đang chụp có nhãn *Client đang chụp*),
- mục *Camera IP* → nút **Chụp ảnh** trên từng camera.

Client hỏi Server mỗi 10 giây (cùng lúc lấy cấu hình), nên bật / tắt trên Website thì khoảng 10 giây sau Client tự mở / dừng luồng chụp, **không cần khởi động lại Client**. Ảnh gửi lên mang id camera (`yt-<video id>`, `ip-<số>`), tab *Ảnh từ Client* hiện đúng tên camera. Muốn dùng danh sách camera tự khai báo như trước: đặt `"cameras_from_server": false` (dùng mảng `"cameras"`), hoặc chạy với `--source-type/--source-url`.

```bash
cd client
python Client.py               # chạy mọi camera trong "cameras"
python Client.py --view nha    # cửa sổ preview mở camera "nha" trước (hoặc --view 2)
```

#### Nhiều camera cùng lúc (YouTube + camera nhà)

Mảng `"cameras"` trong `client_config.json`: mỗi camera chạy **một luồng chụp riêng**, dùng chung luồng gửi ảnh và luồng lấy cấu hình. Mặc định có 2 camera:

| id | Nguồn | Link lấy từ |
|---|---|---|
| `youtube` | YouTube kênh 0511 | `source.url` trong `client_config.json` |
| `nha` | Camera nhà (mặc định RTSP) | biến `CAMERA_NHA_URL` trong `client/.env` (chép từ `client/.env.example`, có mẫu link theo hãng camera) |

- Camera chưa có link → bị bỏ qua kèm cảnh báo, camera còn lại vẫn chạy. Tắt tạm 1 camera: `"enabled": false`.
- Cửa sổ preview hiện **1 camera**: nhấn `1`, `2`… hoặc `Tab` để đổi camera đang xem, `q` để thoát.
- Website: ô **Camera** ở trang *Ảnh trực tiếp* và *Quản lý ảnh* (Tất cả / youtube / nha) — chỉ hiện ảnh của camera đã chọn; lựa chọn nằm trên URL (`/?camera=nha`). Camera Client khai báo nhưng chưa gửi ảnh vẫn có trong ô chọn (ghi "chưa có ảnh").
- Ảnh lưu ở `client/data/images/<id camera>/<ngày>/`, gửi lên Server với trường `source` = id camera (xem ở trang chi tiết ảnh).

Có thể ghi đè cấu hình bằng tham số dòng lệnh (chỉ định `--source-type` / `--source-url` → chỉ chạy đúng 1 nguồn đó):

```bash
python Client.py --source-type rtsp --source-url rtsp://192.168.1.15:8554/live --server http://192.168.1.10:5000
python Client.py --source-type webcam --source-url 0
python Client.py --source-type file --source-url video_test.mp4 --no-preview
```

Trong cửa sổ preview, nhấn `1`/`2`/`Tab` để đổi camera, `q` để thoát, hoặc nhấn Ctrl+C trong terminal.

## Nguồn video

| `source.type` | `source.url` ví dụ | Ghi chú |
|---|---|---|
| `rtsp` | `rtsp://admin:pass@192.168.1.20:554/Streaming/Channels/102` | Camera IP (đường dẫn tùy hãng) |
| `rtsp` | URL hiện trên màn hình app OctoStream | iPhone làm camera IP |
| `http` | `http://192.168.1.15:8080/video` | Luồng MJPEG qua HTTP |
| `webcam` | `0` | Webcam gắn vào máy |
| `file` | `video_test.mp4` | Test khi không có camera (phát lặp lại) |
| `youtube` | `https://www.youtube.com/@0511.VietNam/live` | Camera công cộng 0511 (luồng đang phát của kênh). Nếu báo lỗi, vào tab *Trực tiếp* của kênh, mở một video đang LIVE và dán link `watch?v=...` |

**Không commit mật khẩu camera lên git.** Ghi link vào `client/.env` (không commit, xem `client/.env.example`) hoặc đặt biến môi trường:

```bash
CAMERA_URL="rtsp://admin:matkhau@192.168.1.20:554/stream1" python Client.py --source-type rtsp
```

### Dùng iPhone làm camera IP

1. Cài app **OctoStream RTSP Server** (App Store), bấm phát luồng và ghi lại URL `rtsp://...` hiện trên màn hình.
2. Kiểm tra bằng VLC trên laptop (cùng Wi-Fi): *Media → Open Network Stream* → dán URL.
3. Cắm sạc, tắt tự khóa màn hình và để app luôn mở ở màn hình chính (iOS dừng camera khi app chạy nền).
4. Đặt `source.type = "rtsp"` và `source.url = <URL đó>` trong `client_config.json`.

### Đổi sang camera IP thật

Chỉ cần đổi `source.url` sang đường dẫn RTSP của camera, không phải sửa code. Có thể dùng **ONVIF Device Manager** hoặc `nmap -p 554,80 192.168.1.0/24` để tìm IP camera và đường dẫn luồng. Nếu OpenCV không đọc được, vào cài đặt camera đổi codec từ H.265 sang H.264.

## Mô hình mạng triển khai

```
iPhone / Camera IP ──Wi-Fi/LAN──┐
                                ├── Router (DHCP) ──┬── Laptop A: Client
                                │                   └── Laptop B: Server (+ trình duyệt)
```

1. Các thiết bị kết nối cùng một router. Xem IP từng máy bằng `ipconfig` (Windows) hoặc `ip a` (Linux), hoặc trong trang quản lý router.
2. Trên máy Server (Windows), mở cổng 5000 trong tường lửa: *Windows Defender Firewall → Inbound Rules → New Rule → Port 5000 TCP*.
3. Trên máy Client, đặt `server_url = "http://<IP-máy-Server>:5000"`.
4. **Đồng bộ đồng hồ hai máy (NTP)** trước khi đo độ trễ. Trên Windows: *Settings → Time → Sync now*.

## Phân quyền

Trang đăng nhập cho chọn vai trò trước:

| Ai | Vào bằng | Được làm |
|---|---|---|
| **Người xem** | bấm *Người xem* — vào thẳng, **không cần mật khẩu** | chỉ xem: camera trực tiếp, camera IP, ảnh, thống kê |
| **Quản trị viên** | bấm *Quản trị viên* → nhập mật khẩu | mọi chức năng: xóa ảnh, đổi cấu hình, thêm/xóa camera, quản lý người dùng |
| **Client** (máy chụp ảnh) | header `X-API-Key` = `PBL4_API_KEY` | gửi ảnh, lấy cấu hình |

- Vào địa chỉ Server (`http://<IP>:5000/`) **luôn hiện màn hình chọn vai trò**; nếu đang có phiên thì có thêm nút *Tiếp tục*. Phiên mất khi đóng trình duyệt, và Server tự hủy phiên sau 12 giờ.
- Đang ở chế độ Người xem, bấm nút **Quản trị** ở cuối thanh bên trái để chuyển sang đăng nhập quản trị.
- Muốn bắt mọi người phải có mật khẩu: đặt `PBL4_ALLOW_GUEST=0` trong `server/.env` (tài khoản quyền `viewer` tạo ở trang Người dùng vẫn đăng nhập được).

- Mặc định từ chối: mọi trang và API đều phải vào (khách hoặc đăng nhập), trừ `/login`, `/static/…` và 2 API của Client. Ảnh trong `/uploads/` cũng cần đăng nhập.
- Mật khẩu lưu dạng băm (werkzeug). Cookie phiên có `HttpOnly`, `SameSite=Lax` (chống CSRF) và hết hạn sau 12 giờ. Đăng nhập sai 5 lần trong 5 phút từ một IP thì IP đó bị khóa 5 phút. Admin đổi quyền hoặc xóa tài khoản thì phiên của tài khoản đó mất hiệu lực ngay.
- **Hạn chế:** Server chạy HTTP thường nên mật khẩu và khóa API đi qua mạng ở dạng rõ. Khi triển khai thật cần HTTPS (TLS), ví dụ đặt Server sau nginx có chứng chỉ.

## Camera trực tiếp (`/live`)

Trang mặc định sau khi vào. **Chọn một camera** trong danh sách (giống nhau ở cả 2 tab):
- tab **Video trực tiếp** phát video của camera đó (YouTube nhúng),
- tab **Ảnh từ Client** hiện ảnh **Client chụp từ chính camera đó** (khung hình mới nhất + độ trễ, ảnh gần đây, tự cập nhật mỗi 2 giây).

**Quản trị viên chọn camera nào thì Client chụp camera đó** (Server đặt camera đó là camera chụp, Client nhận qua `/api/config` trong ≤ 10 giây và tự chuyển luồng chụp; ảnh đầu tiên có sau khoảng 10–20 giây). Người xem chọn camera chỉ để xem — không làm đổi camera Client đang chụp; nếu chọn camera khác camera đang chụp, trang báo "Client đang chụp camera …". Camera đang chụp có nhãn *Client đang chụp*. Tab ảnh chỉ làm mới khi đang mở, để số đo "chụp → hiển thị" chỉ tính ảnh người dùng thật sự thấy.

Tab Video trực tiếp: xem livestream YouTube ngay trên Website bằng khung nhúng (`youtube-nocookie.com/embed`). Trình duyệt tải video thẳng từ YouTube, Server chỉ lưu danh sách link (bảng `live_streams`).
- Chọn camera ở danh sách bên phải, hoặc bật **Xem nhiều camera cùng lúc** (lưới, tối đa 6).
- Admin dán link (`watch?v=`, `youtu.be/`, `/live/`) → Server dùng **yt-dlp** kiểm tra video có tồn tại và có cho nhúng không. Admin cũng có thể **tìm camera đang phát** theo từ khóa (bộ lọc "Trực tiếp" của YouTube); kết quả đánh dấu link không cho nhúng.
- Lần chạy đầu, Server nạp sẵn 10 camera mẫu đã kiểm tra (Đà Nẵng, Hà Nội, Nha Trang, Tokyo, Mỹ…). Livestream có thể dừng bất cứ lúc nào: dùng nút *Kiểm tra còn phát*, rồi xóa hoặc thêm link khác.

## Camera IP (`/ipcam`)

Xem trực tiếp camera trong mạng LAN chỉ bằng địa chỉ IP. Trình duyệt không mở được RTSP, nên **Server làm trung gian**:

```
Camera IP ──RTSP / HTTP──▶ Server (OpenCV đọc khung, nén JPEG) ──MJPEG qua HTTP──▶ trình duyệt (<img>)
```

- Admin chọn **loại camera** (Imou/Dahua, Ezviz, Hikvision, TP-Link Tapo, RTSP chung, điện thoại Android app IP Webcam) rồi nhập **IP**, cổng, tài khoản / mật khẩu camera → Server tự ghép đường dẫn luồng. Cũng có thể dán URL đầy đủ (`rtsp://…`, `http://…`).
- **Thử kết nối** chụp 1 khung để kiểm tra trước khi lưu (IP sai → báo lỗi sau khoảng 6 giây). **Lưu và xem** → mọi người (cả Người xem) xem được.
- Mỗi camera chỉ có **1 luồng đọc** dùng chung cho mọi người đang xem (đồng bộ bằng `threading.Condition`); không ai xem 20 giây thì Server tự đóng camera. Phát tối đa 10 khung/giây, rộng 960 px.
- Mật khẩu camera chỉ lưu trên Server; trình duyệt chỉ thấy `rtsp://admin:***@…`. Chỉ admin được nhập IP mới (tránh người ngoài dùng Server dò các máy khác trong mạng).
- Trình duyệt chỉ mở khoảng 6 kết nối tới một Server → trang tự phát tối đa 4 camera, camera khác bấm *Xem*.

## Nhận diện vật thể (YOLOv5)

Server tự nhận diện vật thể trong mỗi ảnh Client gửi lên bằng **YOLOv5s** (mô hình ONNX chính thức của Ultralytics, 80 loại COCO),
chạy bằng **OpenCV DNN** — không cần cài PyTorch.

```powershell
cd server
python detector.py --download          # tải models/yolov5s.onnx (14 MB, một lần; không commit)
python detector.py uploads\<anh>.jpg   # thử trên 1 ảnh
```

- `POST /api/images` đưa id ảnh vào `queue.Queue` rồi trả lời ngay; **1 luồng nền** `YoloWorker` (luồng duy nhất dùng mô hình) chạy YOLOv5 (~50–150 ms/ảnh CPU), ghi bảng `detections` (loại, độ tin cậy, khung) và cột `images.detected_time / detect_ms / object_count`.
- Ảnh còn sót (hàng đợi đầy, Server khởi động lại) được **quét bù** định kỳ.
- Website: khung vật thể ở trang chi tiết ảnh, lọc ảnh theo vật thể ở Quản lý ảnh, thời gian YOLOv5 ở Thống kê.
- Biến môi trường: `PBL4_YOLO=0` (tắt), `PBL4_YOLO_CONF` (ngưỡng tin cậy, mặc định 0.35), `PBL4_YOLO_MODEL` (đường dẫn file .onnx).

## REST API

Xem đầy đủ và gọi thử trên Website: mục **Tài liệu API** (`/apidocs`, Swagger UI; đặc tả OpenAPI ở `/api/openapi.json`, nội dung trong `server/openapi.py`).

| Method | Endpoint | Quyền | Mô tả |
|---|---|---|---|
| POST | `/api/images` | Client | Nhận ảnh (multipart: `file`, `capture_time`, `sent_time`, `width`, `height`, `client_id`, ...) |
| GET | `/api/images?page=1&per_page=20&camera=...&start=...&end=...&q=...` | viewer | Danh sách, phân trang, lọc theo camera (`source`) / thời gian / tên |
| GET | `/api/images/<id>` | viewer | Chi tiết ảnh |
| DELETE | `/api/images/<id>` | admin | Xóa ảnh |
| GET | `/api/config?client_id=...&cameras=yt-...,ip-1` | Client / viewer | Cấu hình mới nhất; Client (có khóa API) nhận thêm `cameras` = các camera cần chụp `[{id, name, type, url}]` và báo lại camera đang chụp |
| POST | `/api/config` | admin | Thiết lập `capture_interval`, `jpeg_quality`, `resize_width`, `max_images` |
| GET | `/api/config/history` | admin | Lịch sử thay đổi cấu hình |
| GET | `/api/stats?limit=100` | viewer | Thống kê độ trễ và chu kỳ chụp thực tế |
| GET | `/api/clients` | viewer | Client đang kết nối (IP, lần cuối hoạt động) |
| GET | `/api/cameras` | viewer | Các camera (đã gửi ảnh hoặc Client khai báo): `id`, `image_count`, `last_capture`, `last_image`, `clients` — dùng cho danh sách nguồn / ô chọn camera trên Website |
| GET | `/api/streams` | viewer | Danh sách livestream YouTube |
| GET | `/api/ipcams` · `/api/ipcams/presets` | viewer | Camera IP đã lưu (URL ẩn mật khẩu) · các loại camera |
| POST | `/api/ipcams/test` | admin | Thử kết nối `{preset, ip, port, user, password}` hoặc `{url}` → 1 ảnh JPEG |
| POST / DELETE | `/api/ipcams`, `/api/ipcams/<id>` | admin | Lưu (`name` + như trên) / xóa camera IP |
| GET | `/ipcam/<id>/stream` | viewer | Luồng MJPEG (`multipart/x-mixed-replace`) để hiển thị bằng `<img>` |
| GET | `/api/ipcams/<id>/status` | viewer | Luồng đọc đang chạy, số người xem, lỗi kết nối |
| POST | `/api/streams` | admin | Thêm link `{url}` (Server kiểm tra bằng yt-dlp) |
| DELETE | `/api/streams/<id>` | admin | Xóa link |
| GET | `/api/streams/<id>/check` | viewer | Link còn phát trực tiếp không |
| GET | `/api/streams/search?q=...` | admin | Tìm livestream đang phát trên YouTube |
| GET / POST | `/api/me`, `/api/me/password` | viewer | Người đang đăng nhập / tự đổi mật khẩu `{old, new}` |
| GET / POST | `/api/users` | admin | Danh sách / tạo tài khoản `{username, password, role}` |
| POST | `/api/streams/<id>/select` | admin | Chọn livestream này cho Client chụp (tắt chụp các livestream khác) — trang Camera trực tiếp gọi khi admin chọn camera |
| PATCH | `/api/streams/<id>`, `/api/ipcams/<id>` | admin | `{capture: true/false}` bật / tắt Client chụp ảnh từ camera này |
| PATCH / DELETE | `/api/users/<id>` | admin | Đổi quyền, đặt lại mật khẩu `{role?, password?}` / xóa |

"Quyền viewer" nghĩa là đã vào (khách hoặc tài khoản). Chưa đăng nhập thì API trả `401`, không đủ quyền thì trả `403`.

## Kiểm thử

1. **Luồng đầy đủ**: chạy Server, chạy Client, mở `http://<server>:5000/`. Ảnh mới hiện trên gallery sau khoảng 1–3 giây.
2. **Điều khiển từ xa**: vào trang *Cấu hình*, đổi tần suất từ 5 xuống 2 giây. Kiểm tra ba nơi:
   - log Client có dòng `[CONFIG] Áp dụng cấu hình mới từ server`;
   - trang *Cấu hình*, mục *Lịch sử thay đổi*;
   - trang *Thống kê*, cột *Interval thực tế* chuyển về khoảng 2 giây.
3. **Hiệu năng / độ trễ**: mở trang *Gallery* trong lúc Client chạy, rồi vào trang *Thống kê* để xem độ trễ *truyền mạng*, *chụp → nhận*, *chụp → hiển thị* (trung bình / min / max / P95). Bấm *Tải CSV* để đưa số liệu vào báo cáo.
4. **Mất kết nối**: tắt Server (hoặc ngắt Wi-Fi) trong lúc Client chạy, đợi khoảng 30 giây rồi bật lại. Log Client hiện `Server đã hoạt động lại. Còn N ảnh chờ gửi bù`, và số ảnh hai bên khớp nhau.

Kết quả chạy thử với nguồn file video, Client và Server trên cùng một máy:

- Đổi chu kỳ từ 9 giây xuống 1 giây: Client áp dụng sau khoảng 0,25 giây.
- Interval thực tế đo được: 1,001–1,004 giây.
- Thời gian truyền qua mạng: khoảng 3 ms.
- Độ trễ chụp → hiển thị trung bình: khoảng 1,1 giây (do gallery làm mới mỗi 2 giây).
- Tắt server khoảng 14 giây: Client giữ lại 13 ảnh và gửi bù đủ khi server bật lại, server nhận 31/31 ảnh, không trùng.

Log hoạt động nằm ở `client/logs/client.log` và `server/logs/server.log`.
