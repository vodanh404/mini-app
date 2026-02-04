import spidev
import numpy as np
import time
import RPi.GPIO as GPIO
import os
import cv2

# --- Cấu hình thư mục và thông số ---
USER_HOME = "/home/dinhphuc"
VIDEO_DIR = os.path.join(USER_HOME, "Videos")
WIDTH, HEIGHT = 240, 320
DC_PIN, RST_PIN = 24, 25

# --- Khởi tạo SPI ---
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
    GPIO.output(RST_PIN, GPIO.LOW); time.sleep(0.05)
    GPIO.output(RST_PIN, GPIO.HIGH); time.sleep(0.05)
    
    write_cmd(0x01); time.sleep(0.15) # Software Reset
    write_cmd(0x11); time.sleep(0.1)  # Sleep Out
    write_cmd(0x3A); write_data([0x05]) # 16-bit RGB565
    write_cmd(0x36); write_data([0x00]) # Hướng dọc (Portrait)
    
    # Thiết lập vùng vẽ cố định
    write_cmd(0x2A); write_data([0x00, 0x00, (WIDTH-1) >> 8, (WIDTH-1) & 0xFF])
    write_cmd(0x2B); write_data([0x00, 0x00, (HEIGHT-1) >> 8, (HEIGHT-1) & 0xFF])
    
    write_cmd(0x21) # Display Inversion On
    write_cmd(0x29) # Display On
    time.sleep(0.1)

def frame_to_rgb565(frame):
    """Chuyển đổi frame BGR từ OpenCV sang mảng RGB565 uint16 cực nhanh bằng NumPy"""
    # Resize về kích thước màn hình
    frame = cv2.resize(frame, (WIDTH, HEIGHT))
    # Tách kênh màu và ép kiểu uint16
    b, g, r = cv2.split(frame)
    r = r.astype(np.uint16)
    g = g.astype(np.uint16)
    b = b.astype(np.uint16)
    
    # Ghép bit theo chuẩn RGB565: R(5 bit) | G(6 bit) | B(5 bit)
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.flatten()

def get_video_files(directory):
    """Lấy danh sách các file video trong thư mục"""
    extensions = ('.mp4', '.avi', '.mkv', '.mov')
    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(extensions)]
    return sorted(files)

# --- Thực thi chính ---
init_display()

video_list = get_video_files(VIDEO_DIR)

if not video_list:
    print(f"Không tìm thấy file video nào trong {VIDEO_DIR}")
    exit()

print(f"Tìm thấy {len(video_list)} videos. Bắt đầu phát...")

try:
    while True: # Vòng lặp phát đi phát lại danh sách
        for video_path in video_list:
            print(f"Đang phát: {os.path.basename(video_path)}")
            cap = cv2.VideoCapture(video_path)
            
            frames = 0
            start_time = time.time()
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break # Chuyển sang video tiếp theo khi hết file
                
                # Xử lý và chuyển đổi định dạng
                rgb565_data = frame_to_rgb565(frame)
                
                # Đẩy dữ liệu qua SPI
                write_cmd(0x2C) # RAM Write
                GPIO.output(DC_PIN, GPIO.HIGH)
                # byteswap() đổi endianness cho đúng chuẩn màn hình SPI
                spi.writebytes2(rgb565_data.byteswap().tobytes())
                
                frames += 1
                
                # Hiển thị FPS mỗi giây
                now = time.time()
                if now - start_time >= 1.0:
                    print(f"  - FPS: {frames / (now - start_time):.2f}")
                    frames = 0
                    start_time = now

            cap.release()
            
except KeyboardInterrupt:
    print("\nNgười dùng dừng chương trình.")
finally:
    spi.close()
    GPIO.cleanup()
    print("Đã dọn dẹp hệ thống.")
