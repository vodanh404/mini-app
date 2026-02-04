import spidev
import numpy as np
import time
import RPi.GPIO as GPIO
import os
import cv2

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
    print("Màn hình đã sẵn sàng.")

def frame_to_rgb565(frame):
    # Resize nhanh bằng OpenCV
    frame = cv2.resize(frame, (WIDTH, HEIGHT))
    b, g, r = cv2.split(frame)
    # Gộp bit chuẩn RGB565
    rgb = ((r.astype(np.uint16) & 0xF8) << 8) | \
          ((g.astype(np.uint16) & 0xFC) << 3) | \
          (b.astype(np.uint16) >> 3)
    return rgb.flatten()

def get_videos():
    exts = ('.mp4', '.avi', '.mkv')
    return [os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR) if f.lower().endswith(exts)]

# --- Chạy ---
init_display()
videos = get_videos()

if not videos:
    print("Thư mục Videos trống!")
    exit()

try:
    while True:
        for v_path in videos:
            print(f"\nĐang thử phát: {os.path.basename(v_path)}")
            cap = cv2.VideoCapture(v_path)
            
            if not cap.isOpened():
                print("Không thể mở file này.")
                continue

            frames = 0
            start_t = time.time()

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret: break # Hết video

                try:
                    # Xử lý frame và đẩy SPI
                    data = frame_to_rgb565(frame)
                    write_cmd(0x2C)
                    GPIO.output(DC_PIN, GPIO.HIGH)
                    spi.writebytes2(data.byteswap().tobytes())
                    
                    frames += 1
                    if time.time() - start_t >= 1.0:
                        print(f"FPS: {frames}", end='\r')
                        frames = 0
                        start_t = time.time()
                except Exception as e:
                    print(f"\nLỗi khi xử lý frame: {e}")
                    break

            cap.release()
except KeyboardInterrupt:
    print("\nKết thúc.")
finally:
    spi.close()
    GPIO.cleanup()
