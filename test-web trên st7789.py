import webview
import sys
import os
import time
import numpy as np
import cv2
import spidev
import RPi.GPIO as GPIO
from PIL import Image
import threading

# ==================== CONFIGURATION ====================
WIDTH, HEIGHT = 320, 240
DC_PIN, RST_PIN = 24, 25

# ==================== SPI & GPIO INITIALIZATION ====================
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
    # Hardware reset
    GPIO.output(RST_PIN, GPIO.LOW)
    time.sleep(0.1)
    GPIO.output(RST_PIN, GPIO.HIGH)
    time.sleep(0.1)
    
    write_cmd(0x01); time.sleep(0.15)  # Software Reset
    write_cmd(0x11); time.sleep(0.1)   # Sleep Out
    
    # Display Inversion Control
    # Use 0x20 or 0x21 depending on whether colors appear inverted
    write_cmd(0x20)                    # Inversion OFF (try 0x21 if colors are reversed)
    
    write_cmd(0x3A); write_data([0x05])  # RGB565 (16-bit) color mode
    
    # MADCTL - Memory Access Control (screen orientation)
    # Common values:
    # 0x00 = Portrait
    # 0x60 = Landscape
    # 0xC0 = Portrait inverted
    # 0xA0 = Landscape inverted
    write_cmd(0x36); write_data([0x60])  # Landscape mode
    
    # Set display window (full screen)
    write_cmd(0x2A); write_data([0x00, 0x00, (WIDTH-1)>>8, (WIDTH-1)&0xFF])
    write_cmd(0x2B); write_data([0x00, 0x00, (HEIGHT-1)>>8, (HEIGHT-1)&0xFF])
    
    write_cmd(0x29)  # Display ON
    print("ST7789 display initialized.")

# ==================== PUSH FRAME TO DISPLAY ====================
def push_frame_to_display(frame_bgr):
    # frame_bgr: numpy array (240, 320, 3) in BGR format
    b, g, r = cv2.split(frame_bgr)
    
    # Convert to RGB565 (16-bit)
    rgb565 = ((r.astype(np.uint16) & 0xF8) << 8) | \
             ((g.astype(np.uint16) & 0xFC) << 3) | \
             (b.astype(np.uint16) >> 3)
    
    write_cmd(0x2C)  # Memory Write command
    GPIO.output(DC_PIN, GPIO.HIGH)
    
    # Send data efficiently
    spi.writebytes2(rgb565.byteswap().tobytes())

# ==================== CAPTURE WEBVIEW SCREENSHOT LOOP ====================
def capture_loop(window):
    print("Starting screen capture and display update to ST7789...")
    
    while True:
        try:
            # Take screenshot from webview (returns PIL Image)
            img = window.get_screenshot()
            
            # Resize to match ST7789 resolution
            img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            
            # Convert to OpenCV BGR format
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            # Send frame to ST7789 display
            push_frame_to_display(frame)
            
            # Control frame rate to reduce CPU usage
            time.sleep(0.08)  # ~12 fps - adjust as needed
            
        except Exception as e:
            print("Error during capture/display:", e)
            time.sleep(1)

# ==================== MAIN PROGRAM ====================
def main():
    init_display()
    
    try:
        # Create webview window
        window = webview.create_window(
            title       = 'ST7789 Web Display',
            url         = 'https://www.google.com',   # change to your desired URL
            width       = 800,
            height      = 480,
            resizable   = False,
            fullscreen  = False,
            frameless   = True,           # hide title bar
            easy_drag   = False,
            on_top      = True,
            confirm_close = False
        )

        # Optional: enable debug mode to see logs
        # webview.start(gui='gtk', debug=True)

        # Start screen capture in a background thread
        capture_thread = threading.Thread(target=capture_loop, args=(window,), daemon=True)
        capture_thread.start()

        # Start webview (must run on the main thread)
        webview.start(gui='gtk')

    except Exception as e:
        print("Main error:", e)
    
    finally:
        print("Cleaning up...")
        spi.close()
        GPIO.cleanup()

if __name__ == '__main__':
    main()
