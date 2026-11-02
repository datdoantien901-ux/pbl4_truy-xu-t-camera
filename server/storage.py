"""
Lưu trữ file ảnh trên Server (thư mục uploads/): kiểm tra định dạng, xóa file, dọn ảnh cũ.
"""
import os

from db import get_db
from settings import BASE_DIR, log


# ============ DỌN DẸP ẢNH CŨ ============
def cleanup_old_images():
    """Nếu số ảnh vượt max_images → xóa ảnh cũ nhất (file + DB record)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT max_images FROM config WHERE id = 1')
    row = cur.fetchone()
    max_images = row['max_images'] if row else None
    if not max_images or max_images < 1:
        conn.close()
        return

    cur.execute('SELECT COUNT(*) AS n FROM images')
    total = cur.fetchone()['n']
    if total > max_images:
        excess = total - max_images
        cur.execute('SELECT id, file_path FROM images ORDER BY id ASC LIMIT %s', (excess,))
        for r in cur.fetchall():
            remove_file(r['file_path'])
            cur.execute('DELETE FROM images WHERE id = %s', (r['id'],))
        conn.commit()
        log.info('[CLEANUP] %d ảnh > giới hạn %d → đã xóa %d ảnh cũ nhất', total, max_images, excess)
    conn.close()


def remove_file(rel_path):
    abs_path = os.path.join(BASE_DIR, rel_path)
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
        except OSError as e:
            log.warning('Lỗi xóa file %s: %s', abs_path, e)


def looks_like_image(head, ext):
    if ext in ('.jpg', '.jpeg'):
        return head[:3] == b'\xff\xd8\xff'
    if ext == '.png':
        return head[:8] == b'\x89PNG\r\n\x1a\n'
    return False
