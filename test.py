'''
sudo apt install -y retroarch libretro-fceumm
pip3 install luma.lcd pillow pyboy
flatpak install flathub org.libretro.RetroArch

sudo apt install libretro-fceumm
nano ~/retroarch-st7789.cfg

video_driver = "fbdev"
video_fullscreen = "true"
video_vsync = "true"
audio_driver = "alsa"
menu_driver = "rgui"

'''

import os
import sys
import time
import subprocess
import threading
import signal
import datetime
import textwrap  
import math
import pygame
import board
import busio
from PIL import Image, ImageFont, ImageDraw, ImageOps
from luma.core.interface.serial import spi as luma_spi
from luma.lcd.device import st7789
from xpt2046 import XPT2046
from pyboy import PyBoy
from pyboy.utils import WindowEvent


# ==========================================
# 1. CẤU HÌNH HỆ THỐNG & PHẦN CỨNG
# ==========================================

# Cấu hình Màn hình
WIDTH, HEIGHT = 320, 240

# Theme màu sắc (Palette: Catppuccin Mocha + Custom)
BG_COLOR = "#1e1e2e"       # Nền chính tối
ACCENT_COLOR = "#89b4fa"   # Màu xanh điểm nhấn
TEXT_COLOR = "#cdd6f4"     # Màu chữ chính
WARN_COLOR = "#f38ba8"     # Màu đỏ cảnh báo
SUCCESS_COLOR = "#a6e3a1"  # Màu xanh lá
PLAYER_BG = "#181825"      # Nền trình phát nhạc
READER_BG = "#11111b"      # Nền trình đọc sách
READER_TEXT = "#bac2de"    # Chữ trình đọc sách

# Đường dẫn thư mục (Tự động tạo nếu thiếu)
USER_HOME = "/home/dinhphuc"
DIRS = {
    "MUSIC": os.path.join(USER_HOME, "Music"),
    "VIDEO": os.path.join(USER_HOME, "Videos"),
    "PHOTO": os.path.join(USER_HOME, "Pictures"),
    "BOOK":  os.path.join(USER_HOME, "Documents"),
    "NES": os.path.join(USER_HOME, "Roms/nes"),
    "GB": os.path.join(USER_HOME, "Roms/gb")
}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# Khởi tạo Fonts
def load_font(size):
    try:
        # Ưu tiên font hỗ trợ Unicode tốt để hiển thị icon và tiếng Việt
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except:
        return ImageFont.load_default()

font_icon_lg = load_font(32) # Icon lớn
font_icon = load_font(24)    # Icon vừa
font_lg = load_font(18)      # Tiêu đề
font_md = load_font(14)      # Nội dung thường
font_sm = load_font(10)      # Chú thích nhỏ

# ==========================================
# 2. KHỞI TẠO THIẾT BỊ (LCD & TOUCH)
# ==========================================
try:
    # LCD ST7789
    serial_lcd = luma_spi(port=0, device=0, gpio_DC=24, gpio_RST=25, baudrate=60000000)
    device = st7789(serial_lcd, width=WIDTH, height=HEIGHT, rotate=0, framebuffer="full_frame")
    
    device.backlight(True)

    # Cảm ứng XPT2046
    spi_touch = busio.SPI(board.SCLK_1, board.MOSI_1, board.MISO_1)
    touch = XPT2046(spi_touch, cs_pin=board.D17, irq_pin=board.D26,
                    width=WIDTH, height=HEIGHT, 
                    x_min=100, x_max=1962, y_min=100, y_max=1900, 
                    baudrate=2000000)
except Exception as e:
    print(f"Hardware Error: {e}")
    sys.exit(1)

# Âm thanh
pygame.mixer.init()

# ==========================================
# 3. CLASS CHÍNH: MEDIA CENTER
# ==========================================

class PiMediaCenter:
    def __init__(self, device):
        self.device = device
        self.state = "MENU"  # MENU, MUSIC, VIDEO, PHOTO, BOOK, BT, READING, PLAYING_MUSIC, PLAYING_VIDEO, VIEWING_PHOTO, GAMES, NES_GAMES, GB_GAMES
        self.running = True
        self.files = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.last_touch = 0
        
        # Biến trạng thái chức năng
        self.bt_devices = []
        self.bt_scanning = False
        
        # Book Reader
        self.book_lines = []     # Toàn bộ dòng sau khi wrap
        self.book_page_lines = 10 # Số dòng mỗi trang
        self.book_current_page = 0
        self.book_total_pages = 0
        
        # Music Player
        self.volume = 0.5
        self.music_start_time = 0
        self.music_paused_time = 0
        self.is_paused = False
        
        # Video
        self.is_video_playing = False
        self.video_process = None
        self.audio_process = None

    def emergency_cleanup(self):
        """Dọn dẹp triệt để các tiến trình đang chạy"""
        if self.video_process:
            try: self.video_process.kill()
            except: pass
        if self.audio_process:
            try: self.audio_process.kill()
            except: pass
        os.system("pkill -9 ffplay")
        os.system("pkill -9 ffmpeg")
        pygame.mixer.music.stop()

    # --- HÀM VẼ GIAO DIỆN (UI) ---
    
    def draw_status_bar(self, draw):
        """Vẽ thanh trạng thái trên cùng"""
        draw.rectangle((0, 0, WIDTH, 24), fill="#313244")
        time_str = datetime.datetime.now().strftime("%H:%M")
        draw.text((WIDTH - 45, 5), time_str, fill="white", font=font_sm)
        
        # Vẽ icon pin giả lập
        draw.rectangle((WIDTH - 70, 8, WIDTH - 50, 16), outline="white", width=1)
        draw.rectangle((WIDTH - 68, 10, WIDTH - 55, 14), fill="lime")
        
        draw.text((10, 5), f"Vol: {int(self.volume*100)}%", fill="white", font=font_sm)
        if self.bt_devices: 
            draw.text((WIDTH - 90, 5), "BT", fill="#94e2d5", font=font_sm)

    def draw_button(self, draw, x, y, w, h, text, bg_color="#45475a", text_color="white", icon_font=None):
        """Vẽ nút bấm bo tròn, hỗ trợ font icon"""
        draw.rounded_rectangle((x, y, x+w, y+h), radius=8, fill=bg_color)
        f = icon_font if icon_font else font_md
        bbox = draw.textbbox((0, 0), text, font=f)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Căn giữa text
        draw.text((x + (w - text_w)/2, y + (h - text_h)/2 - 1), text, fill=text_color, font=f)

    def draw_menu(self, draw):
        """Vẽ Menu chính"""
        self.draw_status_bar(draw)
        title = "PI MEDIA HOME"
        bbox = draw.textbbox((0,0), title, font=font_lg)
        draw.text(((WIDTH - (bbox[2]-bbox[0]))/2, 35), title, fill=ACCENT_COLOR, font=font_lg)

        items = [
            ("Music", "♫", "#f9e2af"), ("Video", "►", "#f38ba8"),
            ("Photo", "☘", "#a6e3a1"), ("Books", "☕", "#89b4fa"),
            ("Games", "🎮", "#fab387"), ("BlueTooth", "⚙", "#cba6f7")
        ]
        
        start_y = 70
        btn_w, btn_h = 90, 70
        gap = 20
        start_x = (WIDTH - (btn_w * 3 + gap * 2)) / 2

        for i, (label, icon, color) in enumerate(items):
            row = i // 3
            col = i % 3
            x = start_x + col * (btn_w + gap)
            y = start_y + row * (btn_h + gap)
            
            draw.rounded_rectangle((x, y, x+btn_w, y+btn_h), radius=10, fill="#313244", outline=color, width=2)
            draw.text((x + 35, y + 10), icon, fill=color, font=font_icon)
            draw.text((x + (btn_w - font_sm.getlength(label))/2, y + 45), label, fill="white", font=font_sm)

    def draw_list(self, draw, title):
        """Vẽ danh sách file chung"""
        self.draw_status_bar(draw)
        # Header
        draw.rectangle((0, 24, WIDTH, 50), fill="#45475a")
        draw.text((10, 28), title, fill="yellow", font=font_md)
        self.draw_button(draw, WIDTH-60, 26, 50, 22, "BACK", bg_color=WARN_COLOR, text_color="black")

        # List items
        list_y = 55
        item_h = 30
        max_items = 5
        
        display_list = self.files[self.scroll_offset : self.scroll_offset + max_items]
        
        if not self.files:
            draw.text((WIDTH//2 - 60, 100), "Không có file!", fill="grey", font=font_md)
            return

        for i, item in enumerate(display_list):
            global_idx = self.scroll_offset + i
            is_sel = (global_idx == self.selected_idx)
            
            bg = "#585b70" if is_sel else BG_COLOR
            fg = "cyan" if is_sel else "white"
            
            name = item['name'] if isinstance(item, dict) else item
            
            # Vẽ background item
            draw.rectangle((5, list_y + i*item_h, WIDTH-5, list_y + (i+1)*item_h - 2), fill=bg)
            # Icon folder/file giả
            icon = ">" if "." not in name[-4:] else ">"  # Thay 📂 bằng 📁 nếu font không hỗ trợ
            draw.text((10, list_y + i*item_h + 5), f"{icon} {name[:28]}", fill=fg, font=font_md)

        # Thanh cuộn
        if len(self.files) > max_items:
            sb_h = max(20, int((max_items / len(self.files)) * 140))
            sb_y = list_y + int((self.scroll_offset / len(self.files)) * 140)
            draw.rounded_rectangle((WIDTH-5, sb_y, WIDTH, sb_y+sb_h), radius=2, fill=ACCENT_COLOR)

        # Footer Navigation
        btn_y = 205
        self.draw_button(draw, 10, btn_y, 90, 30, "▲ LÊN")
        self.draw_button(draw, 115, btn_y, 90, 30, "CHỌN", bg_color=SUCCESS_COLOR, text_color="black")
        self.draw_button(draw, 220, btn_y, 90, 30, "▼ XUỐNG")

    def draw_player_ui(self, draw):
        """
        GIAO DIỆN PHÁT NHẠC ĐẸP HƠN
        - Nền màu tối
        - Đĩa nhạc xoay (giả lập)
        - Thanh Progress bar
        - Nút điều khiển icon
        """
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=PLAYER_BG)
        self.draw_status_bar(draw)

        # 1. Thông tin bài hát (Marquee nếu cần, ở đây cắt ngắn)
        if self.files and 0 <= self.selected_idx < len(self.files):
            song_name = self.files[self.selected_idx]
            clean_name = os.path.splitext(song_name)[0]
            # Tách tên nghệ sĩ giả định (nếu tên file dạng "Artist - Song")
            parts = clean_name.split(' - ')
            title = parts[-1]
            artist = parts[0] if len(parts) > 1 else "Unknown Artist"
            
            # Vẽ tên bài hát lớn (cắt ngắn nếu dài)
            draw.text((120, 40), title[:18], fill="white", font=font_lg)
            # Vẽ tên ca sĩ nhỏ hơn
            draw.text((120, 65), artist[:25], fill="#a6adc8", font=font_md)

        # 2. Album Art (Vẽ đĩa Vinyl giả lập)
        cx, cy, r = 60, 80, 40
        # Vẽ viền đĩa
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="#11111b", outline="#313244", width=2)
        # Vẽ nhãn giữa đĩa (màu thay đổi theo bài)
        import random
        random.seed(self.selected_idx) # Màu cố định theo bài
        color_seed = ["#f38ba8", "#fab387", "#a6e3a1", "#89b4fa"][self.selected_idx % 4]
        draw.ellipse((cx-15, cy-15, cx+15, cy+15), fill=color_seed)
        # Lỗ giữa
        draw.ellipse((cx-3, cy-3, cx+3, cy+3), fill="black")
        
        # Hiệu ứng xoay (nếu đang play)
        if pygame.mixer.music.get_busy() and not self.is_paused:
            angle = (time.time() * 2) % (2 * math.pi)
            line_x = cx + math.cos(angle) * (r - 5)
            line_y = cy + math.sin(angle) * (r - 5)
            draw.line((cx, cy, line_x, line_y), fill="#585b70", width=2)

        # 3. Thanh tiến trình (Giả lập vì pygame mixer không trả về duration chính xác cho mp3 stream dễ dàng)
        bar_x, bar_y, bar_w, bar_h = 20, 140, 280, 6
        draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=3, fill="#313244")
        
        # Giả lập progress chạy (reset khi đổi bài)
        if pygame.mixer.music.get_busy():
            elapsed = time.time() - self.music_start_time
            # Giả sử bài hát dài 3 phút (180s) để vẽ visual
            prog = min(1.0, elapsed / 180.0) 
            fill_w = int(bar_w * prog)
            draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=3, fill=ACCENT_COLOR)
            # Đầu tròn chỉ thị
            draw.ellipse((bar_x + fill_w - 6, bar_y - 3, bar_x + fill_w + 6, bar_y + 9), fill="white")
            
            # Thời gian
            m = int(elapsed // 60)
            s = int(elapsed % 60)
            draw.text((WIDTH - 60, 150), f"{m:02}:{s:02}", fill="#a6adc8", font=font_sm)
            draw.text((20, 150), "00:00", fill="#a6adc8", font=font_sm)

        # 4. Nút điều khiển (Sử dụng ký tự Unicode hoặc vẽ)
        btn_y = 180
        # Vol -
        self.draw_button(draw, 20, btn_y + 5, 40, 30, "-", bg_color="#313244")
        # Prev
        self.draw_button(draw, 70, btn_y, 50, 40, "|<", bg_color="#45475a")  # Thay icon prev bằng Unicode hỗ trợ tốt hơn
        # Play/Pause
        is_playing = pygame.mixer.music.get_busy() and not self.is_paused
        play_icon = "||" if is_playing else "►"  # Thay icon play/pause
        play_color = ACCENT_COLOR if is_playing else SUCCESS_COLOR
        self.draw_button(draw, 130, btn_y - 5, 60, 50, play_icon, bg_color=play_color, text_color="#1e1e2e", icon_font=font_lg)
        # Next
        self.draw_button(draw, 200, btn_y, 50, 40, ">|", bg_color="#45475a")  # Thay icon next
        # Vol +
        self.draw_button(draw, 260, btn_y + 5, 40, 30, "+", bg_color="#313244")

    def draw_reader(self, draw):
        """
        GIAO DIỆN ĐỌC SÁCH HỢP LÝ HƠN
        - Có lề (Margin)
        - Ngắt dòng thông minh (Text wrap)
        - Hiển thị số trang
        """
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=READER_BG)
        
        if not self.book_lines:
            draw.text((20, 100), "Không thể đọc nội dung file!", fill=WARN_COLOR, font=font_md)
        else:
            # Lấy các dòng của trang hiện tại
            start_line = self.book_current_page * self.book_page_lines
            end_line = start_line + self.book_page_lines
            page_content = self.book_lines[start_line:end_line]
            
            y = 15
            margin_x = 10
            for line in page_content:
                draw.text((margin_x, y), line, fill=READER_TEXT, font=font_md)
                y += 20 # Khoảng cách dòng (Line height)

        # Footer (Thanh điều hướng trang)
        footer_y = 210
        draw.line((0, footer_y - 5, WIDTH, footer_y - 5), fill="#313244")
        
        page_info = f"Trang {self.book_current_page + 1}/{self.book_total_pages}"
        # Căn giữa số trang
        info_w = font_sm.getlength(page_info)
        draw.text(((WIDTH - info_w)/2, footer_y + 5), page_info, fill="#585b70", font=font_sm)
        
        self.draw_button(draw, 5, footer_y, 60, 25, "Trước", bg_color="#313244", icon_font=font_sm)
        self.draw_button(draw, WIDTH - 65, footer_y, 60, 25, "Sau", bg_color="#313244", icon_font=font_sm)

    def render(self):
        """Hàm render chính, điều phối vẽ dựa trên state"""
        image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(image)

        if self.state == "MENU":
            self.draw_menu(draw)
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT", "GAMES", "NES_GAMES", "GB_GAMES"]:
            title_map = {
                "MUSIC": "Thư viện Nhạc", 
                "VIDEO": "Thư viện Video", 
                "PHOTO": "Thư viện Ảnh", 
                "BOOK": "Kệ Sách", 
                "BT": "Thiết bị Bluetooth",
                "GAMES": "Chọn Hệ Máy",
                "NES_GAMES": "NES Games",
                "GB_GAMES": "Game Boy Games"
            }
            self.draw_list(draw, title_map.get(self.state, ""))
        elif self.state == "PLAYING_MUSIC":
            self.draw_player_ui(draw)
        elif self.state == "READING":
            self.draw_reader(draw)
        elif self.state == "VIEWING_PHOTO":
            pass 

        if self.state != "PLAYING_VIDEO" and self.state != "VIEWING_PHOTO":
            self.device.display(image)

    # --- LOGIC XỬ LÝ (BACKEND) ---

    def load_files(self, type_key, ext):
        self.files = sorted([f for f in os.listdir(DIRS[type_key]) if f.lower().endswith(ext)])
        self.selected_idx = 0
        self.scroll_offset = 0

    def load_files_custom(self, path, exts):
        self.files = sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])
        self.selected_idx = 0
        self.scroll_offset = 0

    def prepare_book_content(self, filename):
        """Xử lý nội dung sách: Đọc file -> Wrap text -> Chia trang"""
        path = os.path.join(DIRS["BOOK"], filename)
        self.book_lines = []
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()
                
            # Xử lý wrap text
            # Với font size 14, width 320, trừ margin, chứa được khoảng 35-40 ký tự
            chars_per_line = 36 
            
            for line in raw_lines:
                line = line.strip()
                if not line:
                    self.book_lines.append("") # Dòng trống
                    continue
                # Tự động xuống dòng nếu câu quá dài
                wrapped = textwrap.wrap(line, width=chars_per_line)
                self.book_lines.extend(wrapped)
                
            self.book_total_pages = math.ceil(len(self.book_lines) / self.book_page_lines)
            if self.book_total_pages == 0: self.book_total_pages = 1
            
        except Exception as e:
            print(f"Lỗi đọc sách: {e}")
            self.book_lines = ["Lỗi đọc file!", str(e)]
            self.book_total_pages = 1
            
        self.book_current_page = 0

    def scan_bt(self):
        self.bt_scanning = True
        self.bt_devices = []
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        d = ImageDraw.Draw(img)
        d.text((80, 100), "Đang quét BT...", fill="lime", font=font_md)
        self.device.display(img)
        
        try:
            subprocess.run(["bluetoothctl", "scan", "on"], timeout=5, stdout=subprocess.DEVNULL)
            out = subprocess.check_output(["bluetoothctl", "devices"]).decode("utf-8")
            for line in out.split('\n'):
                if "Device" in line:
                    p = line.split(' ', 2)
                    if len(p) > 2: self.bt_devices.append({"mac": p[1], "name": p[2]})
        except: pass
        self.bt_scanning = False
        self.files = self.bt_devices
        self.state = "BT"
        self.render()

    def play_music(self):
        """Hàm phụ để phát nhạc theo selected_idx"""
        if not self.files or self.selected_idx < 0 or self.selected_idx >= len(self.files):
            return
        full_path = os.path.join(DIRS["MUSIC"], self.files[self.selected_idx])
        try:
            pygame.mixer.music.load(full_path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
            self.music_start_time = time.time()
            self.is_paused = False
        except Exception as e:
            print(f"Music Error: {e}")

    def play_video_stream(self, filepath):
        if self.is_video_playing: return
        self.is_video_playing = True
        self.state = "PLAYING_VIDEO"
        self.emergency_cleanup()
        
        audio_cmd = ['ffplay', '-nodisp', '-autoexit', '-volume', str(int(self.volume*100)), filepath]
        video_cmd = [
            'ffmpeg', '-re', '-i', filepath, 
            '-vf', f'scale={WIDTH}:{HEIGHT},format=rgb24', 
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 
            '-threads', '2', '-preset', 'ultrafast',
            '-loglevel', 'quiet', '-'
        ]

        try:
            self.audio_process = subprocess.Popen(audio_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.video_process = subprocess.Popen(video_cmd, stdout=subprocess.PIPE, bufsize=WIDTH*HEIGHT*3)
            
            frame_size = WIDTH * HEIGHT * 3
            while self.is_video_playing:
                raw = self.video_process.stdout.read(frame_size)
                if not raw or self.audio_process.poll() is not None:
                    break
                
                img = Image.frombytes('RGB', (WIDTH, HEIGHT), raw)
                img = ImageOps.invert(img) # Đôi khi ST7789 cần invert màu, nếu sai màu hãy xóa dòng này
                self.device.display(img)

                if touch.is_touched():
                    break
        except Exception as e:
            print(f"Video Error: {e}")
        finally:
            self.is_video_playing = False
            self.emergency_cleanup()
            self.state = "VIDEO"
            self.render()

    def show_photo(self, filepath):
        self.state = "VIEWING_PHOTO"
        try:
            img = Image.open(filepath)
            img = ImageOps.fit(img, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            img = ImageOps.invert(img) # Bỏ comment nếu màu bị đảo ngược
            self.device.display(img)
            
            while True:
                time.sleep(0.1)
                if touch.is_touched():
                    time.sleep(0.2)
                    break
        except Exception as e:
            print(e)
        self.state = "PHOTO"
        self.render()

    def run_nes(self, rom):
        subprocess.run([
            "retroarch",
            "-L", "/usr/lib/libretro/fceumm_libretro.so",
            rom,
            "--config", "/home/pi/retroarch-st7789.cfg"
        ])

    def run_gb(self, rom):
        pyboy = PyBoy(rom, window="null", sound=True)
        button_map = {
            "a": (WindowEvent.PRESS_BUTTON_A, WindowEvent.RELEASE_BUTTON_A),
            "b": (WindowEvent.PRESS_BUTTON_B, WindowEvent.RELEASE_BUTTON_B),
            "select": (WindowEvent.PRESS_SELECT, WindowEvent.RELEASE_SELECT),
            "start": (WindowEvent.PRESS_START, WindowEvent.RELEASE_START),
            "right": (WindowEvent.PRESS_ARROW_RIGHT, WindowEvent.RELEASE_ARROW_RIGHT),
            "left": (WindowEvent.PRESS_ARROW_LEFT, WindowEvent.RELEASE_ARROW_LEFT),
            "up": (WindowEvent.PRESS_ARROW_UP, WindowEvent.RELEASE_ARROW_UP),
            "down": (WindowEvent.PRESS_ARROW_DOWN, WindowEvent.RELEASE_ARROW_DOWN),
        }
        current_buttons = set()

        try:
            while True:
                pyboy.tick()
                touch_pt = touch.get_touch()
                new_buttons = set()
                if touch_pt:
                    tx, ty = touch_pt
                    if ty < 30 and tx > 280:
                        break
                    button = None
                    if ty > 200:
                        if tx < 160:
                            button = "select"
                        else:
                            button = "start"
                    elif tx < 160:
                        if tx > 40 and tx < 120 and ty > 80 and ty < 160:
                            if ty < 120:
                                button = "up"
                            else:
                                button = "down"
                            if tx < 80:
                                button = "left"
                            else:
                                button = "right"
                    else:
                        if tx > 200 and tx < 280:
                            if ty < 120:
                                button = "a"
                            else:
                                button = "b"
                    if button:
                        new_buttons.add(button)
                for b in current_buttons - new_buttons:
                    pyboy.send_input(button_map[b][1])
                for b in new_buttons - current_buttons:
                    pyboy.send_input(button_map[b][0])
                current_buttons = new_buttons
                frame = pyboy.screen.ndarray
                img = Image.fromarray(frame, "RGB")
                new_w = int(160 * (240 / 144))
                new_h = 240
                img = img.resize((new_w, new_h), Image.NEAREST)
                bg = Image.new("RGB", (WIDTH, HEIGHT), "black")
                bg.paste(img, ((WIDTH - new_w) // 2, 0))
                self.device.display(bg)
                time.sleep(0.01)
        finally:
            pyboy.stop()

    # --- XỬ LÝ SỰ KIỆN CẢM ỨNG ---
    def handle_touch(self, x, y):
        now = time.time()
        if now - self.last_touch < 0.3: return
        self.last_touch = now

        # --- MENU CHÍNH ---
        if self.state == "MENU":
            start_y = 70
            btn_w, btn_h = 90, 70
            gap = 20
            start_x = (WIDTH - (btn_w * 3 + gap * 2)) / 2
            
            col, row = -1, -1
            if start_y <= y <= start_y + btn_h * 2 + gap:
                if start_x <= x <= start_x + btn_w: col = 0
                elif start_x + btn_w + gap <= x <= start_x + 2*btn_w + gap: col = 1
                elif start_x + 2*(btn_w + gap) <= x <= start_x + 3*btn_w + gap: col = 2
                
                if start_y <= y <= start_y + btn_h: row = 0
                elif start_y + btn_h + gap <= y <= start_y + 2*btn_h + gap: row = 1
            
            if row != -1 and col != -1:
                idx = row * 3 + col
                if idx == 0: 
                    self.state = "MUSIC"
                    self.load_files("MUSIC", ('.mp3', '.wav'))
                elif idx == 1: 
                    self.state = "VIDEO"
                    self.load_files("VIDEO", ('.mp4',))
                elif idx == 2: 
                    self.state = "PHOTO"
                    self.load_files("PHOTO", ('.jpg', '.png', '.jpeg'))
                elif idx == 3: 
                    self.state = "BOOK"
                    self.load_files("BOOK", ('.txt',))
                elif idx == 4: 
                    self.state = "GAMES"
                    self.files = ["NES", "Game Boy"]
                    self.selected_idx = 0
                    self.scroll_offset = 0
                elif idx == 5: 
                    threading.Thread(target=self.scan_bt).start()
                    return
                self.render()

        # --- DANH SÁCH FILE ---
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT", "GAMES", "NES_GAMES", "GB_GAMES"]:
            # Nút BACK
            if x > WIDTH - 70 and y < 50:
                if self.state in ["NES_GAMES", "GB_GAMES"]:
                    self.state = "GAMES"
                else:
                    self.state = "MENU"
                pygame.mixer.music.stop()
                self.render()
                return

            # Nav Buttons
            if y > 200:
                if x < 100: # LÊN
                    if not self.files:
                        return
                    self.selected_idx = max(0, self.selected_idx - 1)
                    if self.selected_idx < self.scroll_offset: self.scroll_offset = self.selected_idx
                elif x > 220: # XUỐNG
                    if not self.files:
                        return
                    self.selected_idx = min(len(self.files) - 1, self.selected_idx + 1)
                    if self.selected_idx >= self.scroll_offset + 5: self.scroll_offset += 1
                else: # CHỌN
                    if not self.files: 
                        return
                    if self.selected_idx < 0 or self.selected_idx >= len(self.files):
                        self.selected_idx = 0
                        return
                    item = self.files[self.selected_idx]
                    
                    if self.state == "MUSIC":
                        self.state = "PLAYING_MUSIC"
                        self.play_music()
                    
                    elif self.state == "VIDEO":
                        full_path = os.path.join(DIRS["VIDEO"], item)
                        threading.Thread(target=self.play_video_stream, args=(full_path,), daemon=True).start()
                        return

                    elif self.state == "PHOTO":
                        full_path = os.path.join(DIRS["PHOTO"], item)
                        self.show_photo(full_path)
                        return
                    
                    elif self.state == "BOOK":
                        self.prepare_book_content(item)
                        self.state = "READING"
                    
                    elif self.state == "BT":
                        mac = item['mac']
                        subprocess.run(["bluetoothctl", "connect", mac])
                        self.state = "MENU"

                    elif self.state == "GAMES":
                        system = item
                        if system == "NES":
                            self.load_files_custom(DIRS["NES"], ('.nes',))
                            self.state = "NES_GAMES"
                        else:
                            self.load_files_custom(DIRS["GB"], ('.gb', '.gbc'))
                            self.state = "GB_GAMES"

                    elif self.state in ["NES_GAMES", "GB_GAMES"]:
                        dir_key = "NES" if self.state == "NES_GAMES" else "GB"
                        full_path = os.path.join(DIRS[dir_key], item)
                        if self.state == "NES_GAMES":
                            self.run_nes(full_path)
                        else:
                            self.run_gb(full_path)
                        self.render()
                        return

                self.render()

        # --- TRÌNH PHÁT NHẠC (MUSIC PLAYER UI) ---
        elif self.state == "PLAYING_MUSIC":
            # Nút ESC (Góc phải trên)
            if x > WIDTH - 60 and y < 30:  # Điều chỉnh vùng chạm để khớp vị trí nút mới
                pygame.mixer.music.stop()
                self.state = "MUSIC"
                self.render()
                return

            # Controls (Hàng dưới)
            if y > 170:
                if x < 60: # Vol -
                    self.volume = max(0, self.volume - 0.1)
                    pygame.mixer.music.set_volume(self.volume)
                elif x < 120: # Prev
                    if not self.files:
                        return
                    self.selected_idx = (self.selected_idx - 1) % len(self.files)
                    self.play_music()
                elif x < 190: # Play/Pause
                    if self.is_paused:
                        pygame.mixer.music.unpause()
                        # Bù thời gian pause để progress bar đúng
                        self.music_start_time += (time.time() - self.music_paused_time)
                        self.is_paused = False
                    else:
                        pygame.mixer.music.pause()
                        self.music_paused_time = time.time()
                        self.is_paused = True
                elif x < 250: # Next
                    if not self.files:
                        return
                    self.selected_idx = (self.selected_idx + 1) % len(self.files)
                    self.play_music()
                else: # Vol +
                    self.volume = min(1, self.volume + 0.1)
                    pygame.mixer.music.set_volume(self.volume)
            
            self.render()

        # --- TRÌNH ĐỌC SÁCH (BOOK READER UI) ---
        elif self.state == "READING":
            # Nút Thoát
            if x > WIDTH - 60 and y < 30:  # Điều chỉnh vùng chạm
                self.state = "BOOK"
                self.render()
                return
            
            # Nav Trang
            if y > 180:
                if x < 100: # Trước
                    self.book_current_page = max(0, self.book_current_page - 1)
                elif x > 220: # Sau
                    self.book_current_page = min(self.book_total_pages - 1, self.book_current_page + 1)
                self.render()

    def run(self):
        self.render()
        while self.running:
            # Liên tục cập nhật UI khi nghe nhạc để quay đĩa/chạy thanh progress
            if self.state == "PLAYING_MUSIC" and not self.is_paused:
                self.render()
            
            touch_pt = touch.get_touch()
            if touch_pt:
                tx, ty = touch_pt
                self.handle_touch(tx, ty)
            
            time.sleep(0.1 if self.state == "PLAYING_MUSIC" else 0.05)

# ==========================================
# 4. ENTRY POINT
# ==========================================
if __name__ == "__main__":
    def signal_handler(sig, frame):
        print("Exiting...")
        pygame.mixer.quit()
        os.system("pkill -9 ffmpeg")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    app = PiMediaCenter(device)
    app.run()
