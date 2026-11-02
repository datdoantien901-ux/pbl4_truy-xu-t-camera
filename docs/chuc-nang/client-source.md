# Client — nguồn video

> Mã chức năng: `client-source` · Nhánh sửa lỗi: `fix/client-source` · Cập nhật lần cuối: **2026-11-02**

Mở nguồn RTSP (ép TCP) / HTTP MJPEG / webcam / file (giả lập tốc độ thật, lặp vô hạn) / YouTube (phân giải URL bằng yt-dlp); che mật khẩu trong URL khi ghi log.

## File thuộc chức năng này

- `client/video_source.py`

## Lỗi / tồn tại đã biết

- [ ] Nguồn YouTube phụ thuộc `yt-dlp`, dễ hỏng khi YouTube đổi API → `pip install -U yt-dlp`.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `docs/nhat-ky-chuc-nang` | Tài liệu | Tạo nhật ký (chưa sửa gì kể từ khi tách module) | — |
