# Client — lõi (cấu hình, log, khởi động)

> Mã chức năng: `client-core` · Nhánh sửa lỗi: `fix/client-core` · Cập nhật lần cuối: **2026-11-02**

Đọc cấu hình (mặc định < `client_config.json` < biến môi trường / `client/.env` < dòng lệnh), danh sách camera, log, cấu hình dùng chung giữa các luồng, khởi động / dừng các luồng (1 luồng chụp / camera), cửa sổ preview chọn camera.

## File thuộc chức năng này

- `client/Client.py`
- `client/settings.py`
- `client/shared_config.py`
- `client/client_config.json`
- `client/.env.example` (mẫu link camera; `client/.env` không commit)

## Lỗi / tồn tại đã biết

- [ ] `DEFAULT_SETTINGS` có URL YouTube khác `client_config.json` (link live có thể hết hạn → cập nhật khi lỗi mở nguồn).
- [ ] `.gitignore` có `client/client_config.local.json` nhưng Client không đọc file này.
- [x] (đã sửa 2026-11-02, `feature/client-multi-camera`) `load_settings()` dùng `dict(DEFAULT_SETTINGS)` (copy nông) → khi không có file cấu hình, gán `settings['source'][...]` sửa luôn `DEFAULT_SETTINGS`. Chưa gây lỗi vì chỉ gọi 1 lần.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `feature/client-multi-camera` | Tính năng | Nhiều camera: mảng `cameras` + `load_cameras()` (id hợp lệ, `enabled`, `url_env`, bỏ qua camera chưa có link); đọc `client/.env`; `Client.py` tạo 1 CaptureThread/camera, preview đổi camera bằng 1/2/Tab, `--view`. Sửa copy nông `DEFAULT_SETTINGS` (dùng `deepcopy`) | settings.py, Client.py, client_config.json, .env.example |
| 2026-11-02 | `refactor/client-core` · `9739676` | Tái cấu trúc | Tách đọc cấu hình, log ra `settings.py`; `SharedConfig` ra `shared_config.py` | Client.py, settings.py, shared_config.py |
