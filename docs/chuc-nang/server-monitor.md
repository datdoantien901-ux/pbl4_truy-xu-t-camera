# Server — giám sát, thống kê độ trễ

> Mã chức năng: `server-monitor` · Nhánh sửa lỗi: `fix/server-monitor` · Cập nhật lần cuối: **2026-11-16**

Thống kê độ trễ chụp → nhận → hiển thị, chu kỳ chụp thực tế (`/api/stats`); danh sách Client đang kết nối (`/api/clients`); danh sách camera (`/api/cameras`).

## File thuộc chức năng này

- `server/routes/monitor.py`

## Lỗi / tồn tại đã biết

- [ ] Client và Server ở 2 máy phải đồng bộ đồng hồ (NTP) thì số liệu độ trễ mới đúng.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-16 | `feature/client-chup-tu-web` | Tính năng | `/api/cameras` thêm `name` (tên camera trên Website), `capture`; camera đang bật chụp xếp đầu; nguồn không còn trên Website ghi "(ảnh cũ)" | routes/monitor.py |
| 2026-11-16 | `fix/vao-trang-va-chon-nguon` | Tính năng | `/api/cameras` trả thêm `last_image` (ảnh mới nhất của mỗi camera) cho danh sách nguồn | routes/monitor.py |
| 2026-11-02 | `feature/web-camera-filter` | Tính năng | Thêm `GET /api/cameras`: camera Client khai báo (đúng thứ tự cấu hình) + camera chỉ còn ảnh cũ, kèm số ảnh, lần chụp cuối | routes/monitor.py |
| 2026-11-02 | `feature/client-multi-camera` | Sửa lỗi | `actual_gap` tính theo từng (client_id, source) — trước đây 1 Client gửi ảnh 2 camera xen kẽ cho ra khoảng cách sai (1s/4s thay vì 5s); thêm trường `source` vào từng item của `/api/stats` | routes/monitor.py |
| 2026-11-02 | `refactor/server-monitor` · `257d65c` | Tái cấu trúc | Tách `/api/stats`, `/api/clients` ra `routes/monitor.py` (Blueprint `monitor`) | routes/monitor.py, Server.py |
