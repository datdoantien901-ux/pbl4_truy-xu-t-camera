# Server — API ảnh và lưu trữ file

> Mã chức năng: `server-images` · Nhánh sửa lỗi: `fix/server-images` · Cập nhật lần cuối: **2026-11-02**

Nhận ảnh từ Client (`POST /api/images`, chống nhận trùng), liệt kê / lọc / phân trang, chi tiết, xóa, đánh dấu đã hiển thị; lưu file vào `server/uploads/`, dọn ảnh cũ khi vượt `max_images`.

## File thuộc chức năng này

- `server/routes/images.py`
- `server/storage.py`

## Lỗi / tồn tại đã biết

- [ ] Không có xác thực: ai trong LAN cũng gọi được `DELETE /api/images/<id>`.
- [ ] `cleanup_old_images()` chạy đồng bộ sau mỗi lần upload (thêm 1 kết nối DB / request).

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `refactor/server-images` · `dcfa5db` | Tái cấu trúc | Tách API ảnh ra `routes/images.py` (Blueprint `images`), xử lý file ra `storage.py` | routes/images.py, storage.py, Server.py |
