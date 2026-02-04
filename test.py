import spidev
import numpy as np
import time
import RPi.GPIO as GPIO
import os
import cv2

# --- Cấu hình đường dẫn ---
USER_HOME = "/home/dinhphuc"
VIDEO_DIR = os.path.join(USER_HOME, "Videos")

# --- Cấu hình màn hình 240x320 ---
WIDTH, HEIGHT = 240, 320
DC_PIN, RST_PIN = 24, 25

# --- Khởi tạo SPI ---
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 80000000 # 80MHz cho Pi 4

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
    
    write_cmd(0x01); time.sleep(0.15) # SW Reset
    write_cmd(0x11); time.sleep(0.1)  # Sleep Out
    write_cmd(0x3A); write_data([0x05]) # 16-bit RGB565
    write_cmd(0x36); write_data([0x00]) # Hướng dọc
    
    # Thiết lập Window (0,0) -> (239,319)
    write_cmd(0x2A); write_data([0x00, 0x00, (WIDTH-1) >> 8, (WIDTH-1) & 0xFF])
    write_cmd(0x2B); write_data([0x00, 0x00, (HEIGHT-1) >> 8, (HEIGHT-1) & 0xFF])
    
    write_cmd(0x21) # Inversion On
    write_cmd(0x29) # Display On
    print("Màn hình đã khởi tạo thành công.")

def frame_to_rgb565(frame):
    """Chuyển đổi BGR sang RGB565 bằng NumPy"""
    frame = cv2.resize(frame, (WIDTH, HEIGHT))
    # Tách kênh màu trực tiếp để tăng tốc
    b, g, r = cv2.split(frame)
    # Ép kiểu và dịch bit tạo RGB565
    rgb = ((r.astype(np.uint16) & 0xF8) << 8) | \
          ((g.astype(np.uint16) & 0xFC) << 3) | \
          (b.astype(np.uint16) >> 3)
    return rgb.flatten()

def get_first_video():
    """Lấy file video đầu tiên tìm thấy trong thư mục Videos"""
    if not os.path.exists(VIDEO_DIR):
        print(f"Lỗi: Thư mục {VIDEO_DIR} không tồn tại.")
        return None
    
    valid_extensions = ('.mp4', '.avi', '.mkv', '.mov')
    for f in os.listdir(VIDEO_DIR):
        if f.lower().endswith(valid_extensions):
            return os.path.join(VIDEO_DIR, f)
    return None

# --- Main ---
init_display()
video_path = get_first_video()

if not video_path:
    print(f"Không tìm thấy file video nào trong {VIDEO_DIR}!")
    print("Vui lòng copy file video (.mp4) vào thư mục đó.")
else:
    print(f"Đang mở video: {os.path.basename(video_path)}")
    cap = cv2.VideoCapture(video_path)

    frames = 0
    start_time = time.time()

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                # Quay lại đầu video nếu hết
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            # Xử lý frame
            data_565 = frame_to_rgb565(frame)

            # Đẩy lên màn hình
            write_cmd(0x2C)
            GPIO.output(DC_PIN, GPIO.HIGH)
            spi.writebytes2(data_565.byteswap().tobytes())

            frames += 1
            if time.time() - start_time >= 1.0:
                print(f"FPS: {frames}")
                frames = 0
                start_time = time.time()

    except KeyboardInterrupt:
        print("\nĐã dừng.")
    finally:
        cap.release()
        spi.close()
        GPIO.cleanup()
