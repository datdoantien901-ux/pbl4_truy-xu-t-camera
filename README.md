# PBL4 – Truy xuất và phân tích dữ liệu hình ảnh từ Camera qua mạng

Hệ thống gồm 3 phần:

- **Client** (`client/`): kết nối Camera (RTSP / HTTP / webcam / file / YouTube), chụp ảnh theo chu kỳ, lưu cục bộ (file + SQLite) và gửi lên Server.
- **Backend API** (`server/Server.py`): RESTful API bằng Flask, nhận và quản lý ảnh, cấu hình Client từ xa.
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
 │ Flask REST API ── uploads/ + server.db (SQLite WAL)                            │
 │ Website: /  /manage  /config  /stats                                           │
 └────────────────────────────────────────────────────────────────────────────────┘
```

**Điểm chính về Hệ điều hành**

- Client chạy **đa luồng** theo mô hình Producer–Consumer: luồng chụp ảnh không bao giờ bị chặn bởi mạng chậm.
- Đồng bộ giữa các luồng bằng `threading.Lock`, `queue.Queue` (bounded buffer) và `threading.Event`.
- Bắt tín hiệu **SIGINT/SIGTERM** để dừng tuần tự các luồng và giải phóng tài nguyên.
- Ghi file **atomic**: ghi ra file tạm rồi `os.replace`, nên không để lại file hỏng khi bị tắt đột ngột.
- SQLite chế độ **WAL** cho phép đọc và ghi đồng thời.

**Điểm chính về Mạng**

- Đọc luồng **RTSP** (ép dùng TCP để ổn định trên Wi-Fi).
- Upload qua **HTTP multipart/form-data**, giữ kết nối TCP (keep-alive) giữa các lần gửi.
- **Chịu lỗi mạng**: khi server tắt hoặc mất mạng, ảnh được giữ trong DB cục bộ và tự gửi bù khi có mạng lại. Server chống nhận trùng ảnh.
- Website hiển thị IP của Client và trạng thái online.

## Cấu trúc thư mục

```
client/
  Client.py           chương trình chính (các luồng Capture / Upload / Config)
  video_source.py     lớp VideoSource: rtsp | http | webcam | file | youtube
  local_store.py      SQLite cục bộ, đồng thời là hàng đợi gửi bù
  client_config.json  cấu hình Client
  data/               ảnh + client.db (tự tạo, không commit)
  logs/client.log     log hoạt động (tự tạo)
server/
  Server.py           REST API + Web
  templates/, static/ giao diện
  uploads/, server.db ảnh và CSDL phía server
  logs/server.log     log hoạt động (tự tạo)
```

## Cài đặt

Yêu cầu Python 3.9 trở lên.

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

- Mặc định server lắng nghe `0.0.0.0:5000`, nên máy khác trong mạng LAN truy cập được qua `http://<IP-máy-server>:5000`.
- Đổi cổng: `PBL4_PORT=8000 python Server.py`. Trên Windows PowerShell: `$env:PBL4_PORT=8000; python Server.py`.
- Chế độ debug **tắt** mặc định. Chỉ bật (`PBL4_DEBUG=1`) khi chạy một mình trên máy, vì debugger của Flask cho phép chạy code từ xa.

### 2. Client

Sửa `client/client_config.json` (nguồn video, địa chỉ server), rồi chạy:

```bash
cd client
python Client.py
```

Có thể ghi đè cấu hình bằng tham số dòng lệnh:

```bash
python Client.py --source-type rtsp --source-url rtsp://192.168.1.15:8554/live --server http://192.168.1.10:5000
python Client.py --source-type webcam --source-url 0
python Client.py --source-type file --source-url video_test.mp4 --no-preview
```

Trong cửa sổ preview, nhấn `q` để thoát, hoặc nhấn Ctrl+C trong terminal.

## Nguồn video

| `source.type` | `source.url` ví dụ | Ghi chú |
|---|---|---|
| `rtsp` | `rtsp://admin:pass@192.168.1.20:554/Streaming/Channels/102` | Camera IP (đường dẫn tùy hãng) |
| `rtsp` | URL hiện trên màn hình app OctoStream | iPhone làm camera IP |
| `http` | `http://192.168.1.15:8080/video` | Luồng MJPEG qua HTTP |
| `webcam` | `0` | Webcam gắn vào máy |
| `file` | `video_test.mp4` | Test khi không có camera (phát lặp lại) |
| `youtube` | `https://www.youtube.com/@0511.VietNam/live` | Camera công cộng 0511 (luồng đang phát của kênh). Nếu báo lỗi, vào tab *Trực tiếp* của kênh, mở một video đang LIVE và dán link `watch?v=...` |

**Không commit mật khẩu camera lên git.** Đặt URL qua biến môi trường thay vì ghi vào file:

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

## REST API

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/api/images` | Nhận ảnh (multipart: `file`, `capture_time`, `sent_time`, `width`, `height`, `client_id`, ...) |
| GET | `/api/images?page=1&per_page=20&start=...&end=...&q=...` | Danh sách, phân trang, lọc theo thời gian / tên |
| GET | `/api/images/<id>` | Chi tiết ảnh |
| DELETE | `/api/images/<id>` | Xóa ảnh |
| GET | `/api/config` | Client lấy cấu hình mới nhất |
| POST | `/api/config` | Thiết lập `capture_interval`, `jpeg_quality`, `resize_width`, `max_images` |
| GET | `/api/config/history` | Lịch sử thay đổi cấu hình |
| GET | `/api/stats?limit=100` | Thống kê độ trễ và chu kỳ chụp thực tế |
| GET | `/api/clients` | Client đang kết nối (IP, lần cuối hoạt động) |

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
