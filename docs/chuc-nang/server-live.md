# Server — camera YouTube xem trực tiếp

> Mã chức năng: `server-live` · Nhánh sửa lỗi: `fix/server-live` · Cập nhật lần cuối: **2026-11-16**

Trang `/live` xem livestream YouTube ngay trên Website qua khung nhúng `youtube-nocookie.com/embed/<id>` (trình duyệt tải video thẳng từ YouTube, Server không chuyển tiếp luồng). Danh sách link lưu ở bảng `live_streams`. Admin thêm link (Server kiểm tra bằng yt-dlp: còn tồn tại, cho nhúng), tìm livestream đang phát theo từ khóa, xóa link.

## File thuộc chức năng này

- `server/youtube.py` — `parse_video_id`, `inspect`, `search_live`, `DEFAULT_STREAMS` (10 link mẫu)
- `server/routes/streams.py` — `/api/streams…`
- `server/templates/live.html`
- Liên quan: bảng `live_streams` trong `db.py` (nạp mẫu khi tạo bảng lần đầu), CSS mục "Camera YouTube" trong `style.css`

## Lỗi / tồn tại đã biết

- [ ] Livestream có thể dừng / đổi id bất cứ lúc nào → link mẫu sẽ cũ dần; hiện chỉ kiểm tra khi bấm *Kiểm tra còn phát*, chưa tự động đánh dấu link chết.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-16 | `feature/camera-ip` | Tính năng | Đổi tên trang thành *Camera trực tiếp*, là trang mặc định sau khi vào; dẫn sang Camera IP | templates/live.html |
| 2026-11-16 | `feature/phan-quyen` | Tính năng | Tạo chức năng: trang Camera YouTube (1 camera lớn + danh sách, hoặc lưới tối đa 6); admin thêm link / tìm livestream đang phát (yt-dlp, bộ lọc "Trực tiếp", kiểm tra cho nhúng song song 8 luồng) / xóa; nạp 10 camera mẫu đã kiểm tra (Đà Nẵng, Hà Nội, Nha Trang, Tokyo, Mỹ…). Đã test: link sai / trùng / chặn nhúng / bị gỡ đều báo lỗi đúng; tìm kiếm ~5 s; chụp màn hình Chrome headless | youtube.py, routes/streams.py, templates/live.html, db.py, static/style.css |
