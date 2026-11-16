"""
Livestream YouTube cho trang "Camera YouTube": tách video id từ link, kiểm tra link bằng yt-dlp
(đang phát trực tiếp? có cho nhúng vào web khác không?), tìm livestream theo từ khóa.

Website xem bằng khung nhúng https://www.youtube-nocookie.com/embed/<id> → trình duyệt tải video
thẳng từ YouTube, Server không phải chuyển tiếp luồng video.
"""
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

try:
    import yt_dlp
except ImportError:          # Server vẫn chạy được, chỉ mất chức năng kiểm tra / tìm kiếm
    yt_dlp = None

# Danh sách mẫu nạp vào bảng live_streams lần đầu (đã kiểm tra: đang phát + cho nhúng, 16/11/2026).
# Livestream có thể dừng bất cứ lúc nào → admin xóa / thêm link mới trên Website.
DEFAULT_STREAMS = [
    ('sJvEFrG0wq0', 'Camera cổng trường Nguyễn Huệ Đà Nẵng', 'Phát Triển Đà Nẵng'),
    ('oif_zZFIfB4', 'Camera cổng sau bệnh viện C Đà Nẵng', 'Phát Triển Đà Nẵng'),
    ('x8tUUv-NGXs', 'Camera view công trình bệnh viện Đà Nẵng', 'Phát Triển Đà Nẵng'),
    ('6Vwsx3igmIQ', 'Hà Nội 24/7 - Cầu Vĩnh Tuy & Sông Hồng', 'Ha Noi Live Cam'),
    ('n8lmPY3dEfA', 'Nha Trang - bãi biển (ЖК Океанус)', 'Аренда в Нячанге'),
    ('5B4LmH4JbnY', 'Tokyo - ngã tư Shibuya Scramble (ANN)', 'ANNnewsCH'),
    ('dfVK7ld38Ys', 'Tokyo - ngã tư Shibuya Scramble (FNN)', 'FNNプライムオンライン'),
    ('92awjbqabkg', 'Mỹ - camera giao thông khắp nước', 'Total Traffic & Weather Network'),
    ('iSeH45R-8R0', 'St Maarten - bãi biển Maho cạnh sân bay', 'SHOWME Caribbean'),
    ('EO_1LWqsCNE', 'Los Angeles - bãi biển Venice', 'Teleport.camera'),
]

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
_YDL_OPTS = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'socket_timeout': 10}
# Bộ lọc "Trực tiếp" của trang tìm kiếm YouTube
_LIVE_FILTER = 'EgJAAQ%253D%253D'


def available():
    return yt_dlp is not None


def parse_video_id(text):
    """Nhận link YouTube (watch?v=, youtu.be/, /live/, /embed/, /shorts/) hoặc id 11 ký tự → id; sai → None."""
    text = (text or '').strip()
    if _ID_RE.match(text):
        return text
    try:
        u = urllib.parse.urlparse(text if '://' in text else 'https://' + text)
    except ValueError:
        return None
    host = (u.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    if host == 'youtu.be':
        cand = u.path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'music.youtube.com', 'youtube-nocookie.com'):
        cand = urllib.parse.parse_qs(u.query).get('v', [''])[0]
        if not cand:
            parts = u.path.strip('/').split('/')
            if len(parts) >= 2 and parts[0] in ('live', 'embed', 'shorts', 'v'):
                cand = parts[1]
    else:
        return None
    return cand if _ID_RE.match(cand or '') else None


def inspect(video_id):
    """Hỏi YouTube thông tin 1 video. Trả về dict: title, channel, live_status, embeddable;
    lỗi (video bị gỡ, riêng tư...) → {'error': ...}."""
    if yt_dlp is None:
        return {'error': 'Server chưa cài yt-dlp (pip install yt-dlp)'}
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            # process=False: chỉ đọc thông tin trang, không phân giải luồng video → nhanh
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False, process=False)
    except Exception as e:  # yt_dlp.utils.DownloadError...
        msg = re.sub(r'^ERROR:\s*(\[[^\]]+\]\s*)?', '', str(e)).split('\n')[0]
        return {'error': msg[:200] or 'Không đọc được video'}
    return {
        'video_id': video_id,
        'title': (info.get('title') or video_id)[:255],
        'channel': (info.get('channel') or info.get('uploader') or '')[:255],
        'live_status': info.get('live_status'),           # is_live, was_live, not_live, is_upcoming...
        'embeddable': info.get('playable_in_embed') is not False,
    }


def search_live(query, limit=12):
    """Tìm livestream đang phát theo từ khóa, kèm kiểm tra cho nhúng hay không (song song)."""
    if yt_dlp is None:
        raise RuntimeError('Server chưa cài yt-dlp (pip install yt-dlp)')
    url = ('https://www.youtube.com/results?search_query=' + urllib.parse.quote(query)
           + '&sp=' + _LIVE_FILTER)
    with yt_dlp.YoutubeDL({**_YDL_OPTS, 'extract_flat': True, 'playlistend': limit}) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = [e for e in (info.get('entries') or [])
               if e.get('id') and _ID_RE.match(e['id']) and e.get('live_status') == 'is_live'][:limit]
    # Kết quả tìm kiếm không cho biết video có cho nhúng không → hỏi từng video (8 luồng song song)
    with ThreadPoolExecutor(max_workers=8) as pool:
        details = list(pool.map(inspect, [e['id'] for e in entries]))
    results = []
    for e, d in zip(entries, details):
        results.append({
            'video_id': e['id'],
            'title': e.get('title') or e['id'],
            'channel': e.get('channel') or e.get('uploader') or '',
            'live_status': d.get('live_status', e.get('live_status')),
            'embeddable': d.get('embeddable', False) if 'error' not in d else False,
        })
    return results
