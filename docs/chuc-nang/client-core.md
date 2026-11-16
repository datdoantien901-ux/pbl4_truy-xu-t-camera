# Client — lõi (cấu hình, log, khởi động)

> Mã chức năng: `client-core` · Nhánh sửa lỗi: `fix/client-core` · Cập nhật lần cuối: **2026-11-16**

Đọc cấu hình (mặc định < `client_config.json` < biến môi trường / `client/.env` < dòng lệnh), danh sách camera, log, cấu hình dùng chung giữa các luồng, khởi động / dừng các luồng (1 luồng chụp / camera), cửa sổ preview chọn camera.

## File thuộc chức năng này

- `client/Client.py`
- `client/camera_manager.py`
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
| 2026-11-16 | `feature/client-chup-tu-web` | Tính năng | Client chụp **các camera admin bật trên Website** (`cameras_from_server`, mặc định true): `CameraManager` mở / dừng `CaptureThread` khi danh sách đổi (mỗi luồng 1 `Event` dừng riêng), không cần khởi động lại; preview chịu được danh sách camera thay đổi (chờ danh sách → màn hình "Dang cho..."). Đã test với Client thật: bật Hà Nội + camera IP → ~25 s sau 2 luồng mới chụp; tắt Nguyễn Huệ → dừng đúng luồng đó sau 3 s, 2 luồng kia vẫn chạy | Client.py, camera_manager.py (mới), settings.py, client_config.json |
| 2026-11-16 | `feature/phan-quyen` | Tính năng | Cấu hình `api_key` (mặc định rỗng), lấy từ `PBL4_API_KEY` trong `client/.env` | settings.py, .env.example |
| 2026-11-02 | `feature/web-camera-filter` | Tính năng | `load_cameras()` trả về thêm danh sách id camera khai báo (để ConfigThread báo cho Server) | settings.py, Client.py |
| 2026-11-02 | `feature/client-multi-camera` | Tính năng | Nhiều camera: mảng `cameras` + `load_cameras()` (id hợp lệ, `enabled`, `url_env`, bỏ qua camera chưa có link); đọc `client/.env`; `Client.py` tạo 1 CaptureThread/camera, preview đổi camera bằng 1/2/Tab, `--view`. Sửa copy nông `DEFAULT_SETTINGS` (dùng `deepcopy`) | settings.py, Client.py, client_config.json, .env.example |
| 2026-11-02 | `refactor/client-core` · `9739676` | Tái cấu trúc | Tách đọc cấu hình, log ra `settings.py`; `SharedConfig` ra `shared_config.py` | Client.py, settings.py, shared_config.py |
