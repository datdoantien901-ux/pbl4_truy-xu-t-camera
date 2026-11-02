# Nhật ký theo chức năng

Mỗi chức năng có một file ghi: file code thuộc chức năng, lỗi còn tồn tại, nhật ký thay đổi.
Mã chức năng trùng với tên nhánh (`refactor/<mã>`, `fix/<mã>`, `feature/<mã>-...`).

| Mã | Chức năng | File chính | Lỗi đang mở |
|---|---|---|---|
| [`server-core`](server-core.md) | lõi (cấu hình, thời gian, CSDL) | `Server.py`, `settings.py`, `timeutil.py`, `db.py`, `schema.sql`, `migrate_sqlite_to_mysql.py`, `.env.example` | 2 |
| [`server-images`](server-images.md) | API ảnh và lưu trữ file | `images.py`, `storage.py` | 2 |
| [`server-config`](server-config.md) | API cấu hình từ xa | `config.py` | 1 |
| [`server-monitor`](server-monitor.md) | giám sát, thống kê độ trễ | `monitor.py` | 1 |
| [`server-web`](server-web.md) | giao diện web | `web.py`, `*.html`, `style.css` | 1 |
| [`client-core`](client-core.md) | lõi (cấu hình, log, khởi động) | `Client.py`, `settings.py`, `shared_config.py`, `client_config.json`, `.env.example` | 2 |
| [`client-source`](client-source.md) | nguồn video | `video_source.py` | 1 |
| [`client-store`](client-store.md) | lưu trữ cục bộ (SQLite) | `local_store.py` | 0 |
| [`client-capture`](client-capture.md) | luồng chụp ảnh | `capture_thread.py` | 0 |
| [`client-upload`](client-upload.md) | luồng gửi ảnh, gửi bù | `upload_thread.py` | 0 |
| [`client-config`](client-config.md) | luồng lấy cấu hình từ Server | `config_thread.py` | 0 |

## Quy tắc cập nhật (bắt buộc sau mỗi lần sửa code)

1. Xác định chức năng theo file đã sửa (bảng trên). Sửa nhiều chức năng → cập nhật từng file.
2. Thêm **một dòng lên đầu** bảng "Nhật ký thay đổi": ngày, nhánh · commit, loại, nội dung (sửa gì, vì sao), file.
   Lúc ghi chưa có commit hash → ghi tên nhánh; hash bổ sung ở lần cập nhật sau.
3. Sửa xong một mục trong "Lỗi / tồn tại đã biết" → đổi `- [ ]` thành `- [x]`, ghi kèm `(đã sửa <ngày>, <nhánh>)`.
   Phát hiện lỗi mới → thêm `- [ ]` vào mục đó.
4. Đổi ngày "Cập nhật lần cuối" ở đầu file; cập nhật cột "Lỗi đang mở" ở bảng trên.
5. Commit file nhật ký **cùng commit** với phần code đã sửa.
6. Thêm file code mới → ghi vào "File thuộc chức năng này" (và bảng trên). Chức năng mới → tạo `<mã>.md` theo mẫu các file hiện có.
