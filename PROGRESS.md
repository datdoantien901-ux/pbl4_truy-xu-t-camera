# Tiến trình dự án

> Cập nhật file này ở cuối mỗi phiên làm việc: ghi việc đã xong, việc đang dở, lỗi mới phát hiện.
> Cập nhật lần cuối: **2026-11-02**

## Đã hoàn thành

| Thời điểm | Commit / việc | Nội dung |
|---|---|---|
| 09/2026 | `1efc4b0`, `d1f7623` | Phiên bản đầu: client chụp ảnh đơn luồng, lưu `timestamp/`, `images/` |
| 10/2026 | `8bde8bc` | Client đa luồng (Capture / Upload / Config), nhiều nguồn video, gửi bù ảnh khi mất mạng; trang quản lý và thống kê độ trễ |
| 10/2026 | `ac2fa0a` | Làm lại giao diện web; nguồn YouTube dùng luồng trực tiếp kênh 0511 |
| 11/2026 | `d574d5e` (trên `main`) | Chuyển Server từ SQLite sang MySQL, thêm `schema.sql`, `migrate_sqlite_to_mysql.py` |
| 2026-11-02 | `5d924da` merge `main` → `feature/multithread-client` | Gỡ xung đột: giữ toàn bộ tính năng nhánh đa luồng + chạy hoàn toàn trên MySQL, `DATETIME(3)`, schema/migrate đủ 4 bảng. Bỏ `server/server.db` khỏi git, `.gitignore` thêm `*.db`, `server/uploads/`. Thêm CLAUDE.md, AGENTS.md, PROGRESS.md |
| 2026-11-02 | `feature/server-env` | Server đọc cấu hình MySQL từ `server/.env` (không commit), khỏi gõ lại cổng/mật khẩu |
| 2026-11-02 | `docs/nhat-ky-chuc-nang` | Tạo `docs/chuc-nang/*.md`: nhật ký + lỗi tồn tại theo từng chức năng; chuyển danh sách lỗi Server/Client từ PROGRESS.md sang đó |
| 2026-11-02 | 9 nhánh `refactor/*` + `docs/cau-truc-module`, merge `--no-ff` vào `feature/multithread-client` | Tách code theo chức năng, không đổi hành vi. Server: `settings`, `timeutil`, `db`, `storage`, `routes/{images,config,monitor,web}` (Blueprint). Client: `settings`, `shared_config`, `capture_thread`, `upload_thread`, `config_thread`. `migrate_sqlite_to_mysql.py` import trực tiếp `db`/`settings`/`timeutil` |

### Đã kiểm thử (2026-11-02, MySQL 8.0.46 cổng 3307, Python 3.13)
- `pip install -r server/requirements.txt` trong venv mới: OK.
- Migrate: 52 ảnh + 1 client + config sang MySQL; chạy lần 2 không thêm trùng.
- 21/21 kiểm thử API qua HTTP đạt: upload, chống trùng, file không hợp lệ (400), lọc/phân trang, chi tiết, displayed, xóa, config GET/POST + validate, history, stats, clients, 5 trang web.
- Chưa chạy thử Client thật kết nối Server MySQL (end-to-end).

### Đã kiểm thử sau khi tách module (2026-11-02, KHÔNG có MySQL thật — thiếu mật khẩu)
- Server (MySQL giả lập bằng mock): 17/17 route giống hệt bản trước khi tách; 11 smoke check (lỗi 400 của upload/config, 4 trang web, static) đạt ở cả bản cũ và mới; pyflakes sạch.
- Client (video mẫu + server Flask giả): chụp 7 ảnh / 14s, gửi đủ 7, nhận cấu hình mới từ server — giống bản cũ; kịch bản tắt server rồi bật lại → gửi bù đủ.
- **Cần chạy lại 21 kiểm thử API với MySQL thật** sau đợt tách module.

## Đang dở — làm tiếp ở phiên sau

1. Chạy Server với MySQL thật sau khi tách module (xem mục kiểm thử ở trên), rồi chạy end-to-end: Server (MySQL) + Client, kiểm tra gallery, trang Thống kê, kịch bản tắt server rồi bật lại.
2. Tạo PR `feature/multithread-client` → `main`.
3. Hỏi người dùng có dọn file rác đang track không (xem mục Repo bên dưới).

## Lỗi / tồn tại đã biết

### Repo
- **File rác đang được git track** (~309 ảnh + DB từ phiên bản đầu): `timestamp/`, `images/`, `client/timestamp/`, `camera_metadata.db`, `client/camera_metadata.db`. Code hiện tại không dùng các file này (client mới lưu ở `client/data/`). Nên `git rm --cached` và bổ sung `.gitignore` (cần hỏi người dùng trước).
- Chưa có test tự động trong repo.

### Theo chức năng
Lỗi của từng chức năng (Server / Client) ghi trong **[docs/chuc-nang/](docs/chuc-nang/README.md)** — mỗi chức năng một file, kèm nhật ký sửa đổi. Không ghi trùng ở đây.

## Ghi chú môi trường (máy phát triển)
- Windows 11, Python 3.13, MySQL80 service tại `D:\MySQL\PBL4`, cổng 3307 (đã ghi trong `server/.env`), user `root` (mật khẩu: hỏi người dùng, **không ghi vào repo**).
- Database: `pbl4_camera`.
