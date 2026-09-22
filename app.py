import cv2
import yt_dlp
import time
import os
from datetime import datetime

# Cấu hình
YOUTUBE_URL = 'https://www.youtube.com/watch?v=oC8ttZHG50I' 
SAVE_FOLDER = 'images'
CAPTURE_INTERVAL = 5

# Tự động tạo thư mục nếu chưa có
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)
    print(f"📁 Đã tạo thư mục lưu ảnh: {SAVE_FOLDER}/")

def get_live_stream_url(youtube_url):
    ydl_opts = {
        # CHỐT CHẶN 1: Chỉ lấy video có chiều cao <= 720p, hoặc lấy định dạng tốt nhất có sẵn nếu không lọc được
        'format': 'best[height<=720]/best',
        'noplaylist': True,
        'quiet': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        if 'url' in info:
            return info['url']
        formats = info.get('formats', [info])
        return formats[-1]['url']
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        if 'url' in info:
            return info['url']
        formats = info.get('formats', [info])
        return formats[-1]['url']

def main():
    print("⏳ Đang bóc tách luồng HLS từ YouTube...")
    try:
        stream_url = get_live_stream_url(YOUTUBE_URL)
        print("✅ Lấy luồng thành công! Đang khởi động OpenCV...")
    except Exception as e:
        print(f"❌ Có lỗi xảy ra khi lấy luồng: {e}")
        return

    while True:
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            print("❌ Không thể mở luồng video. Đang thử kết nối lại...")
            time.sleep(2)
            continue

        print(f"▶️ Video đang phát. Tự động chụp ảnh mỗi {CAPTURE_INTERVAL} giây...")
        
        last_capture_time = time.time()

        while True:
            ret, frame = cap.read()
            if not ret:
                print("⚠️ Video bị gián đoạn. Đang kết nối lại luồng...")
                try:
                    stream_url = get_live_stream_url(YOUTUBE_URL)
                except:
                    pass
                break

            # LOGIC CẮT ẢNH
            current_time = time.time()
            if current_time - last_capture_time >= CAPTURE_INTERVAL:
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{SAVE_FOLDER}/cam_{timestamp_str}.jpg"
                cv2.imwrite(filename, frame)
                print(f"📸 Đã lưu: {filename}")
                last_capture_time = current_time

            cv2.imshow("Client - Camera Da Nang", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("🛑 Đã đóng ứng dụng thủ công.")
                cap.release()
                cv2.destroyAllWindows()
                return

        cap.release()

if __name__ == "__main__":
    main()