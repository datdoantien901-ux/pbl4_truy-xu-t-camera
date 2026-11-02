# Server — giám sát, thống kê độ trễ

> Mã chức năng: `server-monitor` · Nhánh sửa lỗi: `fix/server-monitor` · Cập nhật lần cuối: **2026-11-02**

Thống kê độ trễ chụp → nhận → hiển thị, chu kỳ chụp thực tế (`/api/stats`); danh sách Client đang kết nối (`/api/clients`).

## File thuộc chức năng này

- `server/routes/monitor.py`

## Lỗi / tồn tại đã biết

- [ ] Client và Server ở 2 máy phải đồng bộ đồng hồ (NTP) thì số liệu độ trễ mới đúng.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `feature/client-multi-camera` | Sửa lỗi | `actual_gap` tính theo từng (client_id, source) — trước đây 1 Client gửi ảnh 2 camera xen kẽ cho ra khoảng cách sai (1s/4s thay vì 5s); thêm trường `source` vào từng item của `/api/stats` | routes/monitor.py |
| 2026-11-02 | `refactor/server-monitor` · `257d65c` | Tái cấu trúc | Tách `/api/stats`, `/api/clients` ra `routes/monitor.py` (Blueprint `monitor`) | routes/monitor.py, Server.py |
