import spidev
import numpy as np
import time
import RPi.GPIO as GPIO
import webview
import threading
import pyautogui
from PIL import Image

# --- Cấu hình Hardware (Giữ nguyên từ code của bạn) ---
WIDTH, HEIGHT = 320, 240  
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
    """Hàm khởi tạo màn hình ST7789 dùng lệnh SPI thô"""
    GPIO.output(RST_PIN, GPIO.LOW); time.sleep(0.1)
    GPIO.output(RST_PIN, GPIO.HIGH); time.sleep(0.1)
    
    write_cmd(0x01); time.sleep(0.15) # Software Reset
    write_cmd(0x11); time.sleep(0.1)  # Sleep Out
    write_cmd(0x20)                   # Display Inversion ON
    write_cmd(0x3A); write_data([0x05]) # 16-bit RGB565
    write_cmd(0x36); write_data([0x60]) # Landscape mode
    
    # Định nghĩa vùng vẽ (Window)
    write_cmd(0x2A); write_data([0x00, 0x00, (WIDTH-1) >> 8, (WIDTH-1) & 0xFF])
    write_cmd(0x2B); write_data([0x00, 0x00, (HEIGHT-1) >> 8, (HEIGHT-1) & 0xFF])
    
    write_cmd(0x29) # Display On
    print("ST7789 đã sẵn sàng.")

def stream_webview_to_spi(window):
    """Hàm chụp cửa sổ pywebview và đẩy qua SPI"""
    print("Bắt đầu stream GUI...")
    while True:
        try:
            # 1. Chụp ảnh vùng cửa sổ (Sử dụng tọa độ thực tế của cửa sổ)
            # PyAutoGUI chụp theo (x, y, width, height)
            screenshot = pyautogui.screenshot(region=(window.x, window.y, window.width, window.height))
            
            # 2. Xử lý ảnh nhanh bằng NumPy (Convert sang RGB565)
            # Resize về đúng kích thước màn hình ST7789
            img = screenshot.resize((WIDTH, HEIGHT)).convert("RGB")
            frame = np.array(img)
            
            # Tách kênh màu
            r = (frame[:,:,0].astype(np.uint16) & 0xF8) << 8
            g = (frame[:,:,1].astype(np.uint16) & 0xFC) << 3
            b = (frame[:,:,2].astype(np.uint16) >> 3)
            
            rgb565 = r | g | b
            
            # 3. Đẩy dữ liệu lên màn hình
            write_cmd(0x2C) # RAM Write
            GPIO.output(DC_PIN, GPIO.HIGH)
            # Dùng byteswap để sửa lỗi ngược byte (Little Endian vs Big Endian)
            spi.writebytes2(rgb565.byteswap().tobytes())
            
            # Giới hạn FPS để tránh quá tải CPU (ví dụ: ~20 FPS)
            time.sleep(0.04)
            
        except Exception as e:
            # Cửa sổ có thể chưa hiện lên hoặc đã đóng
            time.sleep(1)

def main():
    # Khởi tạo phần cứng
    init_display()

    # Tạo cửa sổ Webview (GUI)
    # Lưu ý: để tỉ lệ 320x240 để hiển thị trên màn hình không bị méo
    window = webview.create_window(
        title='Pi Webview', 
        url='https://www.google.com',
        width=WIDTH,
        height=HEIGHT,
        resizable=True
    )

    # Chạy luồng chụp màn hình song song
    t = threading.Thread(target=stream_webview_to_spi, args=(window,))
    t.daemon = True
    t.start()

    # Bắt đầu vòng lặp GUI
    webview.start()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nĐang thoát...")
    finally:
        spi.close()
        GPIO.cleanup()
