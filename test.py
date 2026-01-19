import os
import time
import numpy as np
from mss import mss
from PIL import Image
from luma.core.interface.serial import spi
from luma.lcd.device import st7789
import RPi.GPIO as GPIO
import multiprocessing as mp
import sys

# 1. Environment Setup
os.environ["DISPLAY"] = ":0"

def screen_capture_worker(queue, lcd_w, lcd_h):
    """
    PRODUCER: Dedicated to capturing and resizing.
    Runs on a separate CPU core.
    """
    with mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        
        while True:
            # Capture raw pixels
            sct_img = sct.grab(monitor)
            
            # FASTEST PROCESSING:
            # 1. Convert to array and drop Alpha channel
            frame = np.array(sct_img, dtype=np.uint8)[..., :3]
            
            # 2. In-place Inversion (much faster than 255 - frame)
            np.bitwise_not(frame, out=frame)
            
            # 3. Swap BGR to RGB
            frame = frame[..., ::-1]
            
            # 4. Resize using NEAREST (Essential for 60fps)
            img = Image.fromarray(frame).resize((lcd_w, lcd_h), Image.Resampling.NEAREST)
            
            # Keep only the latest frame in queue to prevent lag buildup
            if queue.full():
                try:
                    queue.get_nowait()
                except:
                    pass
            queue.put(img)

def display_worker(queue):
    """
    CONSUMER: Dedicated SPI pusher.
    """
    # SILENCE GPIO WARNINGS inside the process
    GPIO.setwarnings(False)
    
    try:
        # SPI at 80MHz (Max for ST7789)
        serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, baudrate=80000000)
        device = st7789(serial, width=320, height=240, rotate=0)
        
        last_time = time.time()
        frames = 0
        
        while True:
            img = queue.get()
            device.display(img)
            
            # Calculate real-time FPS
            frames += 1
            now = time.time()
            if now - last_time >= 1.0:
                sys.stdout.write(f"\r>>> Performance: {frames} FPS | CPU: 1.8GHz | SPI: 80MHz   ")
                sys.stdout.flush()
                frames = 0
                last_time = now
                
    except Exception as e:
        print(f"\nDisplay Error: {e}")

if __name__ == "__main__":
    LCD_W, LCD_H = 320, 240
    
    # We use a Queue of size 1. This ensures that the Display process 
    # NEVER renders an "old" frame, eliminating visual lag.
    image_queue = mp.Queue(maxsize=1)
    
    p_cap = mp.Process(target=screen_capture_worker, args=(image_queue, LCD_W, LCD_H), daemon=True)
    p_dis = mp.Process(target=display_worker, args=(image_queue,), daemon=True)
    
    try:
        print(f"--- Starting 60FPS Turbo Mirroring (ARM @ 1.8GHz) ---")
        p_cap.start()
        p_dis.start()
        
        # Main loop just monitors the processes
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
        p_cap.terminate()
        p_dis.terminate()
        GPIO.cleanup()
