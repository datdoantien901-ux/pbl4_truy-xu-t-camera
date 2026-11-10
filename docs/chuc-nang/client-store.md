# Client — lưu trữ cục bộ (SQLite)

> Mã chức năng: `client-store` · Nhánh sửa lỗi: `fix/client-store` · Cập nhật lần cuối: **2026-11-02**

SQLite WAL `client/data/client.db`: metadata ảnh đã chụp, đồng thời là hàng đợi gửi bù. Mỗi thao tác mở connection riêng (không chia sẻ giữa luồng).

## File thuộc chức năng này

- `client/local_store.py`

## Lỗi / tồn tại đã biết

_(chưa có)_

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `docs/nhat-ky-chuc-nang` | Tài liệu | Tạo nhật ký (chưa sửa gì kể từ khi tách module) | — |
