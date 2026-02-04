import spidev
import numpy as np
import time
import RPi.GPIO as GPIO
import os
import cv2
import subprocess

# --- Cấu hình ---
USER_HOME = "/home/dinhphuc"
VIDEO_DIR = os.path.join(USER_HOME, "Videos")
WIDTH, HEIGHT = 240, 320
DC_PIN, RST_PIN = 24, 25

# --- Khởi tạo SPI & GPIO ---
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 80000000 

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(DC_PIN, GPIO.OUT)
GPIO.setup(RST_PIN, GPIO.OUT)

def write_cmd(cmd):
    GPIO.output(DC_PIN, GPIO.LOW)
    spi.writebytes([cmd])

def write_data(data):
    GPIO.output(DC_PIN, GPIO.HIGH)
    spi.writebytes(data)

def init_display():
    GPIO.output(RST_PIN, GPIO.LOW); time.sleep(0.05)
    GPIO.output(RST_PIN, GPIO.HIGH); time.sleep(0.05)
    write_cmd(0x01); time.sleep(0.15)
    write_cmd(0x11); time.sleep(0.1)
    write_cmd(0x3A); write_data([0x05])
    write_cmd(0x36); write_data([0x00])
    write_cmd(0x2A); write_data([0x00, 0x00, (WIDTH-1) >> 8, (WIDTH-1) & 0xFF])
    write_cmd(0x2B); write_data([0x00, 0x00, (HEIGHT-1) >> 8, (HEIGHT-1) & 0xFF])
    write_cmd(0x21); write_cmd(0x29)
    print("Màn hình ST7789 đã sẵn sàng.")

def frame_to_rgb565(frame):
    """Chuyển đổi frame sang RGB565 tối ưu"""
    frame = cv2.resize(frame, (WIDTH, HEIGHT))
    b, g, r = cv2.split(frame)
    rgb = ((r.astype(np.uint16) & 0xF8) << 8) | \
          ((g.astype(np.uint16) & 0xFC) << 3) | \
          (b.astype(np.uint16) >> 3)
    return rgb.flatten()

def get_videos():
    exts = ('.mp4', '.avi', '.mkv', '.webm')
    return [os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR) if f.lower().endswith(exts)]

def play_video(video_path):
    """Sử dụng FFmpeg để pipe dữ liệu vào OpenCV nếu cần, tránh lỗi AV1"""
    print(f"\nĐang xử lý: {os.path.basename(video_path)}")
    
    # Dùng FFmpeg để giải mã video và đẩy luồng raw thô sang Pipe
    # Cách này giúp bỏ qua việc OpenCV phải tự giải mã AV1 lỗi thời
    command = [
        'ffmpeg',
        '-i', video_path,
        '-f', 'image2pipe',
        '-pix_fmt', 'bgr24',
        '-vcodec', 'rawvideo',
        '-vf', f'scale={WIDTH}:{HEIGHT}',
        '-an', '-', # '-' nghĩa là đẩy ra stdout
        '-loglevel', 'quiet'
    ]
    
    pipe = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=WIDTH*HEIGHT*3)
    
    frames = 0
    start_t = time.time()

    try:
        while True:
            # Đọc đúng số lượng byte cho 1 frame (W*H*3 kênh màu)
            raw_frame = pipe.stdout.read(WIDTH * HEIGHT * 3)
            if not raw_frame:
                break
            
            # Chuyển byte thô thành mảng NumPy
            frame = np.frombuffer(raw_frame, dtype='uint8').reshape((HEIGHT, WIDTH, 3))
            
            # Chuyển sang RGB565 (đã resize sẵn trong ffmpeg nên bước này cực nhanh)
            b, g, r = cv2.split(frame)
            data = ((r.astype(np.uint16) & 0xF8) << 8) | \
                   ((g.astype(np.uint16) & 0xFC) << 3) | \
                   (b.astype(np.uint16) >> 3)

            # Đẩy lên màn hình
            write_cmd(0x2C)
            GPIO.output(DC_PIN, GPIO.HIGH)
            spi.writebytes2(data.byteswap().tobytes())
            
            frames += 1
            if time.time() - start_t >= 1.0:
                print(f"FPS: {frames}", end='\r')
                frames = 0
                start_t = time.time()
                
    except Exception as e:
        print(f"Lỗi khi phát: {e}")
    finally:
        pipe.terminate()

# --- Vòng lặp chính ---
init_display()
videos = get_videos()

if not videos:
    print(f"Không tìm thấy video trong {VIDEO_DIR}!")
    exit()

try:
    while True:
        for v in videos:
            play_video(v)
except KeyboardInterrupt:
    print("\nĐã dừng chương trình.")
finally:
    spi.close()
    GPIO.cleanup()
