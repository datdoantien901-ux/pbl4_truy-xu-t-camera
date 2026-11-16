"""
Danh sách camera Client cần chụp = các camera trên Website được admin bật "Client chụp ảnh":
    livestream YouTube (bảng live_streams)  → id "yt-<video_id>",  type "youtube"
    camera IP (bảng ip_cameras)             → id "ip-<id>",        type "rtsp" / "http"
id này là cột images.source của ảnh Client gửi lên → tab "Ảnh từ Client" ghép được ảnh với camera.
"""


def stream_cam_id(video_id):
    return f'yt-{video_id}'


def ipcam_cam_id(cam_id):
    return f'ip-{cam_id}'


def capture_list(cur, with_url):
    """Camera đang bật chụp. with_url=False → không trả URL (URL camera IP có thể chứa mật khẩu)."""
    cams = []
    cur.execute('SELECT video_id, title FROM live_streams WHERE capture = 1 ORDER BY id')
    for r in cur.fetchall():
        c = {'id': stream_cam_id(r['video_id']), 'name': r['title'], 'type': 'youtube'}
        if with_url:
            c['url'] = f"https://www.youtube.com/watch?v={r['video_id']}"
        cams.append(c)
    cur.execute('SELECT id, name, url FROM ip_cameras WHERE capture = 1 ORDER BY id')
    for r in cur.fetchall():
        c = {'id': ipcam_cam_id(r['id']), 'name': r['name'],
             'type': 'rtsp' if r['url'].lower().startswith('rtsp') else 'http'}
        if with_url:
            c['url'] = r['url']
        cams.append(c)
    return cams


def names(cur):
    """id camera → tên hiển thị (mọi camera trên Website, kể cả đang tắt chụp)."""
    out = {}
    cur.execute('SELECT video_id, title FROM live_streams')
    for r in cur.fetchall():
        out[stream_cam_id(r['video_id'])] = r['title']
    cur.execute('SELECT id, name FROM ip_cameras')
    for r in cur.fetchall():
        out[ipcam_cam_id(r['id'])] = r['name']
    return out
