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
WIDTH, HEIGHT = 320,240  # Đảm bảo đúng tỉ lệ màn hình của bạn
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
    # Reset vật lý
    GPIO.output(RST_PIN, GPIO.LOW); time.sleep(0.1)
    GPIO.output(RST_PIN, GPIO.HIGH); time.sleep(0.1)
    
    write_cmd(0x01); time.sleep(0.15) # Software Reset
    write_cmd(0x11); time.sleep(0.1)  # Sleep Out
    
    # 1. SỬA NGƯỢC MÀU (Inversion Control)
    # Nếu màu bị âm bản (ví dụ màu trắng thành đen), hãy thử đổi 0x21 thành 0x20
    write_cmd(0x20) # Display Inversion ON (Thử 0x20 nếu vẫn sai)
    
    write_cmd(0x3A); write_data([0x05]) # 16-bit RGB565
    
    # 2. SỬA QUAY SAI HƯỚNG (MADCTL)
    # Các giá trị phổ biến: 
    # 0x00: Dọc (Portrait)
    # 0x60: Ngang (Landscape)
    # 0xC0: Dọc ngược (Portrait Inverted)
    # 0xA0: Ngang ngược (Landscape Inverted)
    write_cmd(0x36); write_data([0x60]) 
    
    # Thiết lập Window hiển thị
    write_cmd(0x2A); write_data([0x00, 0x00, (WIDTH-1) >> 8, (WIDTH-1) & 0xFF])
    write_cmd(0x2B); write_data([0x00, 0x00, (HEIGHT-1) >> 8, (HEIGHT-1) & 0xFF])
    
    write_cmd(0x29) # Display On
    print("Màn hình đã khởi tạo với cấu hình mới.")

def play_video(video_path):
    print(f"\nĐang phát: {os.path.basename(video_path)}")
    
    # FFmpeg giải mã và scale đúng kích thước
    command = [
        'ffmpeg',
        '-i', video_path,
        '-f', 'image2pipe',
        '-pix_fmt', 'bgr24',
        '-vcodec', 'rawvideo',
        '-vf', f'scale={WIDTH}:{HEIGHT}',
        '-an', '-', 
        '-loglevel', 'quiet'
    ]
    
    pipe = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=WIDTH*HEIGHT*3)
    
    try:
        while True:
            raw_frame = pipe.stdout.read(WIDTH * HEIGHT * 3)
            if not raw_frame:
                break
            
            frame = np.frombuffer(raw_frame, dtype='uint8').reshape((HEIGHT, WIDTH, 3))
            
            # Chuyển đổi sang RGB565
            b, g, r = cv2.split(frame)
            # Dùng uint16 để tránh tràn bit
            data = ((r.astype(np.uint16) & 0xF8) << 8) | \
                   ((g.astype(np.uint16) & 0xFC) << 3) | \
                   (b.astype(np.uint16) >> 3)

            # Đẩy dữ liệu qua SPI
            write_cmd(0x2C)
            GPIO.output(DC_PIN, GPIO.HIGH)
            spi.writebytes2(data.byteswap().tobytes())
                
    except Exception as e:
        print(f"Lỗi: {e}")
    finally:
        pipe.terminate()

# --- Thực thi ---
init_display()
video_files = [os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR) if f.lower().endswith(('.mp4', '.mkv', '.avi'))]

try:
    if not video_files:
        print("Không có video!")
    else:
        while True:
            for v in video_files:
                play_video(v)
except KeyboardInterrupt:
    print("\nDừng.")
finally:
    spi.close()
    GPIO.cleanup()
