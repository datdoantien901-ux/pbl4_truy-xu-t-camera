# Tiến trình dự án

> Cập nhật file này ở cuối mỗi phiên làm việc: ghi việc đã xong, việc đang dở, lỗi mới phát hiện.
> Cập nhật lần cuối: **2026-11-10**

## Đã hoàn thành

| Thời điểm | Commit / việc | Nội dung |
|---|---|---|
| 09/2026 | `1efc4b0`, `d1f7623` | Phiên bản đầu: client chụp ảnh đơn luồng, lưu `timestamp/`, `images/` |
| 10/2026 | `8bde8bc` | Client đa luồng (Capture / Upload / Config), nhiều nguồn video, gửi bù ảnh khi mất mạng; trang quản lý và thống kê độ trễ |
| 10/2026 | `ac2fa0a` | Làm lại giao diện web; nguồn YouTube dùng luồng trực tiếp kênh 0511 |
| 11/2026 | `d574d5e` (trên `main`) | Chuyển Server từ SQLite sang MySQL, thêm `schema.sql`, `migrate_sqlite_to_mysql.py` |
| 2026-11-02 | `5d924da` merge `main` → `feature/multithread-client` | Gỡ xung đột: giữ toàn bộ tính năng nhánh đa luồng + chạy hoàn toàn trên MySQL, `DATETIME(3)`, schema/migrate đủ 4 bảng. Bỏ `server/server.db` khỏi git, `.gitignore` thêm `*.db`, `server/uploads/`. Thêm CLAUDE.md, AGENTS.md, PROGRESS.md |
| 2026-11-02 | `docs/danh-gia-de-tai` | Đối chiếu yêu cầu đề tài (~75% phần bắt buộc), số liệu độ trễ thật, sắp lại việc cần làm |
| 2026-11-02 | `feature/web-camera-filter` | Website: ô chọn camera ở *Ảnh trực tiếp* và *Quản lý ảnh*; `/api/images?camera=`, `/api/cameras`; cột `clients.cameras` (Client báo camera khai báo qua `/api/config`). Đã test với MySQL thật (cổng phụ 5055) + chụp màn hình Chrome headless, dọn dữ liệu thử |
| 2026-11-02 | `feature/client-multi-camera` | Client chạy nhiều camera cùng lúc (YouTube + camera nhà), mỗi camera 1 luồng chụp; preview đổi camera bằng phím 1/2/Tab, `--view`; link camera trong `client/.env`. Server: `actual_gap` tính theo từng camera. Camera nhà chưa có link thật (người dùng chưa biết loại camera) |
| 2026-11-02 | `feature/server-env` | Server đọc cấu hình MySQL từ `server/.env` (không commit), khỏi gõ lại cổng/mật khẩu |
| 2026-11-02 | `docs/nhat-ky-chuc-nang` | Tạo `docs/chuc-nang/*.md`: nhật ký + lỗi tồn tại theo từng chức năng; chuyển danh sách lỗi Server/Client từ PROGRESS.md sang đó |
| 2026-11-10 | `refactor/don-repo` | Bỏ 311 file rác của phiên bản đầu khỏi git (`timestamp/`, `images/`, `client/timestamp/`, `camera_metadata.db`, `client/camera_metadata.db`) — vẫn giữ trên đĩa; thêm vào `.gitignore` |
| 2026-11-10 | merge `feature/multithread-client` → `main` | Đưa toàn bộ nhánh đa luồng vào `main` (merge `--no-ff`) |
| 2026-11-02 | 9 nhánh `refactor/*` + `docs/cau-truc-module`, merge `--no-ff` vào `feature/multithread-client` | Tách code theo chức năng, không đổi hành vi. Server: `settings`, `timeutil`, `db`, `storage`, `routes/{images,config,monitor,web}` (Blueprint). Client: `settings`, `shared_config`, `capture_thread`, `upload_thread`, `config_thread`. `migrate_sqlite_to_mysql.py` import trực tiếp `db`/`settings`/`timeutil` |

### Đã kiểm thử (2026-11-02, MySQL 8.0.46 cổng 3307, Python 3.13)
- `pip install -r server/requirements.txt` trong venv mới: OK.
- Migrate: 52 ảnh + 1 client + config sang MySQL; chạy lần 2 không thêm trùng.
- 21/21 kiểm thử API qua HTTP đạt: upload, chống trùng, file không hợp lệ (400), lọc/phân trang, chi tiết, displayed, xóa, config GET/POST + validate, history, stats, clients, 5 trang web.
- ~~Chưa chạy thử Client thật kết nối Server MySQL (end-to-end).~~ Người dùng đã chạy Client (YouTube) với Server MySQL: 52 ảnh chụp, 51 đã gửi (xem số liệu ở mục đối chiếu đề tài).

### Đã kiểm thử sau khi tách module (2026-11-02, KHÔNG có MySQL thật — thiếu mật khẩu)
- Server (MySQL giả lập bằng mock): 17/17 route giống hệt bản trước khi tách; 11 smoke check (lỗi 400 của upload/config, 4 trang web, static) đạt ở cả bản cũ và mới; pyflakes sạch.
- Client (video mẫu + server Flask giả): chụp 7 ảnh / 14s, gửi đủ 7, nhận cấu hình mới từ server — giống bản cũ; kịch bản tắt server rồi bật lại → gửi bù đủ.
- Sau đó đã chạy Server thật với MySQL (cổng 5055) khi làm `feature/web-camera-filter`: upload, lọc, `/api/cameras`, config, các trang web đều đạt. Bộ 21 kiểm thử API đầy đủ chưa chạy lại.

## Đối chiếu yêu cầu đề tài (đánh giá 2026-11-02)

**Phần bắt buộc: ~75%** · Phần nâng cao (tùy chọn): 0/3. Thang điểm tự đặt theo khối lượng từng bước của đề.

| # | Yêu cầu đề tài | Trọng số | Đạt | Hiện trạng |
|---|---|---|---|---|
| 1 | Mô hình mạng vật lý: Camera IP ONVIF + Router + laptop cùng LAN, DHCP, dò IP camera (ONVIF Device Manager / nmap) | 10 | 3 | README có sơ đồ mô hình mạng + hướng dẫn dò camera. **Chưa có camera IP thật**, chưa dựng/chụp minh chứng mô hình mạng |
| 2 | Tìm hiểu ONVIF, xác định luồng RTSP, đọc bằng `cv2.VideoCapture` | 10 | 5 | Đọc RTSP (ép TCP), HTTP MJPEG, webcam, file, YouTube bằng OpenCV — xong. **ONVIF chưa có trong code** (chưa lấy RTSP URI qua ONVIF), chỉ nhắc trong README |
| 3 | Client: kết nối RTSP, chụp theo chu kỳ, lưu file tên theo timestamp, metadata vào CSDL cục bộ | 15 | 14 | Xong: đa luồng, nhiều camera, lưu atomic `data/images/<camera>/<ngày>/`, metadata SQLite `client.db`. Chưa chạy với camera RTSP thật (mới YouTube / file) |
| 4 | Gửi ảnh lên Server (HTTP POST multipart), cấu hình resize / interval / JPEG quality, xử lý bằng OpenCV | 10 | 10 | Xong + retry, gửi bù khi mất mạng, chống nhận trùng |
| 5 | Backend RESTful: CRUD ảnh (phân trang, lọc thời gian), `POST /api/config`, lưu file + metadata | 15 | 15 | Xong (Flask + MySQL). Thêm: lịch sử cấu hình, `/api/stats`, `/api/clients`, `/api/cameras`, lọc theo camera |
| 6 | Website: gallery real-time, trang cấu hình, trang quản lý (tìm, chi tiết, xóa) | 15 | 15 | Xong + trang thống kê độ trễ, ô chọn camera |
| 7 | Kiểm thử: end-to-end, điều khiển từ xa (5s → 2s), đo độ trễ chụp → hiển thị | 15 | 8 | Đã chạy thật Client (YouTube) → Server MySQL → Website: 51/52 ảnh đã gửi; log `[CONFIG] Áp dụng cấu hình mới` (9 lần) + `config_history`; độ trễ đo tự động. **Chưa có kịch bản kiểm thử ghi lại có hệ thống** (ảnh chụp, bảng số liệu), chưa test với camera thật |
| 8 | Báo cáo minh chứng + tài liệu cài đặt, cấu hình mạng, triển khai | 10 | 5 | README: cài đặt, chạy, mô hình mạng, REST API, nguồn video. **Chưa có báo cáo minh chứng kiểm thử** |
| | **Tổng phần bắt buộc** | **100** | **75** | |
| N1 | Phát hiện chuyển động / nhận diện khuôn mặt (OpenCV) | — | ✗ | Chưa làm |
| N2 | Live streaming trên Website | — | ✗ | Chưa làm (gallery làm mới ảnh tĩnh mỗi 2 giây) |
| N3 | Cảnh báo email khi có chuyển động | — | ✗ | Chưa làm |

### Số liệu đo thật (30 ảnh YouTube gần nhất, MySQL, 2026-11-02)
- Chụp → Server nhận: trung vị **0.046 s** (nhỏ nhất 0.025 s) — Client và Server cùng máy.
- Gửi → nhận (truyền mạng + ghi): trung vị **0.009 s**.
- Chụp → hiển thị trên Website: nhỏ nhất **0.73 s**, trung vị 11.2 s — trung vị lớn vì ảnh chỉ được tính "đã hiển thị" khi trình duyệt đang mở trang; cần đo lại khi mở sẵn trang Ảnh trực tiếp suốt phiên đo.
- Trung bình toàn bộ bị lệch bởi ảnh gửi bù (chụp lúc Server tắt) → khi báo cáo dùng trung vị / lọc ảnh gửi bù.

## Đang dở — làm tiếp ở phiên sau

Theo thứ tự ưu tiên để tăng % đáp ứng đề tài:

1. **Camera thật (bước 1–3, 7):** xác định loại camera nhà → điền `CAMERA_NHA_URL` trong `client/.env`. Không có camera IP → dùng điện thoại (IP Webcam / OctoStream) làm camera. Chụp minh chứng: sơ đồ LAN, IP camera trên router, ONVIF Device Manager / nmap, VLC mở được RTSP.
2. **ONVIF (bước 2):** thêm công cụ nhỏ dò camera + lấy RTSP URI qua ONVIF (vd thư viện `onvif-zeep`, WS-Discovery) — hoặc tối thiểu minh chứng bằng ONVIF Device Manager.
3. **Báo cáo kiểm thử (bước 7–8):** chạy kịch bản có ghi lại — E2E, đổi interval 5s → 2s trên Website (ảnh log Client + `config_history`), tắt/bật Server (gửi bù), đo độ trễ khi mở sẵn trang gallery; chụp màn hình các trang. Đặt trong `docs/bao-cao/`.
4. (Nâng cao, nếu còn thời gian) phát hiện chuyển động bằng OpenCV (frame differencing) — dễ nhất trong 3 mục nâng cao.
5. Chạy lại bộ 21 kiểm thử API với MySQL thật (sau khi tách module mới test bằng mock).

## Lỗi / tồn tại đã biết

### Repo
- ~~File rác đang được git track~~ (đã dọn 2026-11-10, `refactor/don-repo`). File cũ vẫn còn trên đĩa, có thể xóa tay nếu không cần.
- Chưa có test tự động trong repo.

### Theo chức năng
Lỗi của từng chức năng (Server / Client) ghi trong **[docs/chuc-nang/](docs/chuc-nang/README.md)** — mỗi chức năng một file, kèm nhật ký sửa đổi. Không ghi trùng ở đây.

## Ghi chú môi trường (máy phát triển)
- Windows 11, Python 3.13, MySQL80 service tại `D:\MySQL\PBL4`, cổng 3307 (đã ghi trong `server/.env`), user `root` (mật khẩu: hỏi người dùng, **không ghi vào repo**).
- Database: `pbl4_camera`.
