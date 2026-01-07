#!/usr/bin/env python3
# =========================================================
# PI MEDIA CENTER & RETRO GAME LAUNCHER
# Hợp nhất: Media Center (Touch) + NES/GB (Keyboard/Buttons)
# Hardware: Raspberry Pi 4 + ST7789 (320x240) + XPT2046
# =========================================================

import os
import sys
import time
import subprocess
import threading
import signal
import datetime
import textwrap
import math
import select
import termios
import tty

# --- Audio & Graphics ---
import pygame
import board
import busio
from PIL import Image, ImageFont, ImageDraw, ImageOps
from luma.core.interface.serial import spi as luma_spi
from luma.lcd.device import st7789
from xpt2046 import XPT2046

# --- Emulation ---
try:
    from pyboy import PyBoy
except ImportError:
    print("Cảnh báo: Chưa cài đặt PyBoy. Chức năng Game Boy sẽ không hoạt động.")
    PyBoy = None

# ==========================================
# 1. CẤU HÌNH HỆ THỐNG
# ==========================================

# Cấu hình Màn hình (Landscape)
WIDTH, HEIGHT = 320, 240

# Theme màu sắc (Palette: Catppuccin Mocha)
BG_COLOR = "#1e1e2e"       # Nền chính
ACCENT_COLOR = "#89b4fa"   # Xanh dương điểm nhấn
TEXT_COLOR = "#cdd6f4"     # Chữ trắng ngà
WARN_COLOR = "#f38ba8"     # Đỏ cảnh báo
SUCCESS_COLOR = "#a6e3a1"  # Xanh lá
PLAYER_BG = "#181825"      # Nền nhạc
GAME_BG = "#11111b"        # Nền game

# Đường dẫn thư mục
USER_HOME = "/home/dinhphuc" # Cập nhật theo user của bạn (hoặc /home/pi)
DIRS = {
    "MUSIC": os.path.join(USER_HOME, "Music"),
    "VIDEO": os.path.join(USER_HOME, "Videos"),
    "PHOTO": os.path.join(USER_HOME, "Pictures"),
    "BOOK":  os.path.join(USER_HOME, "Documents"),
    "NES":   os.path.join(USER_HOME, "Roms/nes"),
    "GB":    os.path.join(USER_HOME, "Roms/gb")
}

# Cấu hình RetroArch (NES)
RETROARCH_BIN = "retroarch"
NES_CORE_PATH = "/usr/lib/libretro/fceumm_libretro.so"
RA_CONFIG_PATH = os.path.join(USER_HOME, "retroarch-st7789.cfg")

# Tạo thư mục nếu chưa có
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# Khởi tạo Fonts
def load_font(size):
    try:
        # Font hỗ trợ tiếng Việt và Icon
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except:
        return ImageFont.load_default()

font_icon_lg = load_font(32)
font_icon = load_font(24)
font_lg = load_font(18)
font_md = load_font(14)
font_sm = load_font(10)

# ==========================================
# 2. KHỞI TẠO PHẦN CỨNG
# ==========================================
try:
    # 1. LCD ST7789 (Landscape: Rotate=0 cho 320x240 ngang, tùy driver/cách lắp)
    # Lưu ý: Nếu màn hình bị ngược, chỉnh rotate=180 hoặc đổi h-flip/v-flip
    serial_lcd = luma_spi(port=0, device=0, gpio_DC=24, gpio_RST=25, baudrate=60000000)
    device = st7789(serial_lcd, width=WIDTH, height=HEIGHT, rotate=0, framebuffer="full_frame")
    device.backlight(True)

    # 2. Touch XPT2046
    spi_touch = busio.SPI(board.SCLK_1, board.MOSI_1, board.MISO_1)
    touch = XPT2046(spi_touch, cs_pin=board.D17, irq_pin=board.D26,
                    width=WIDTH, height=HEIGHT,
                    x_min=100, x_max=1962, y_min=100, y_max=1900,
                    baudrate=2000000)
    
    # 3. Audio (Ban đầu init cho Music Player)
    pygame.mixer.init()

except Exception as e:
    print(f"Lỗi khởi tạo phần cứng: {e}")
    sys.exit(1)

# ==========================================
# 3. HÀM HỖ TRỢ (INPUT/UTILS)
# ==========================================

def kb_hit():
    """Kiểm tra phím bấm từ stdin (cho game)"""
    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr:
        return sys.stdin.read(1)
    return None

def set_terminal_mode(raw=True):
    """Chuyển đổi chế độ terminal để đọc phím game"""
    fd = sys.stdin.fileno()
    if raw:
        tty.setcbreak(fd)
    else:
        # Khôi phục (cần lưu old_term ở main hoặc dùng os.system reset đơn giản)
        os.system("stty sane")

# ==========================================
# 4. CLASS CHÍNH: SYSTEM CONTROLLER
# ==========================================

class PiSystem:
    def __init__(self):
        # State: MENU, MUSIC, VIDEO, PHOTO, BOOK, BT, READING, PLAYING_MUSIC,
        #        GAMES_MENU, GAME_SELECT_NES, GAME_SELECT_GB
        self.state = "MENU"
        self.running = True
        
        # Data List
        self.files = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.last_touch = 0
        
        # Bluetooth
        self.bt_devices = []
        self.bt_scanning = False
        
        # Music
        self.volume = 0.5
        self.is_paused = False
        self.music_start_time = 0
        self.music_paused_time = 0
        
        # Book
        self.book_lines = []
        self.book_page_lines = 10
        self.book_current_page = 0
        self.book_total_pages = 0

        # Video/Game Process
        self.video_process = None
        self.audio_process = None

    def cleanup_media(self):
        """Dọn dẹp ffmpeg/video"""
        if self.video_process:
            try: self.video_process.kill()
            except: pass
        if self.audio_process:
            try: self.audio_process.kill()
            except: pass
        os.system("pkill -9 ffplay")
        os.system("pkill -9 ffmpeg")

    # ---------------- UI RENDERING ----------------

    def draw_status_bar(self, draw):
        draw.rectangle((0, 0, WIDTH, 24), fill="#313244")
        time_str = datetime.datetime.now().strftime("%H:%M")
        draw.text((WIDTH - 45, 5), time_str, fill="white", font=font_sm)
        
        # Pin giả lập
        draw.rectangle((WIDTH - 70, 8, WIDTH - 50, 16), outline="white", width=1)
        draw.rectangle((WIDTH - 68, 10, WIDTH - 55, 14), fill="lime")
        
        vol_str = f"Vol: {int(self.volume*100)}%"
        draw.text((10, 5), vol_str, fill="white", font=font_sm)

    def draw_button(self, draw, x, y, w, h, text, bg_color="#45475a", text_color="white", icon_font=None):
        draw.rounded_rectangle((x, y, x+w, y+h), radius=8, fill=bg_color)
        f = icon_font if icon_font else font_md
        bbox = draw.textbbox((0, 0), text, font=f)
        tx_w, tx_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((x + (w - tx_w)/2, y + (h - tx_h)/2 - 1), text, fill=text_color, font=f)

    def draw_menu_grid(self, draw, title, items):
        """Vẽ menu dạng lưới (Main Menu & Game Menu)"""
        self.draw_status_bar(draw)
        bbox = draw.textbbox((0,0), title, font=font_lg)
        draw.text(((WIDTH - (bbox[2]-bbox[0]))/2, 35), title, fill=ACCENT_COLOR, font=font_lg)

        start_y = 70
        btn_w, btn_h = 90, 70
        gap = 20
        # Tính toán để căn giữa dựa trên số cột (tối đa 3)
        cols = min(3, len(items))
        start_x = (WIDTH - (btn_w * cols + gap * (cols - 1))) / 2

        for i, (label, icon, color) in enumerate(items):
            row = i // 3
            col = i % 3
            x = start_x + col * (btn_w + gap)
            y = start_y + row * (btn_h + gap)
            
            draw.rounded_rectangle((x, y, x+btn_w, y+btn_h), radius=10, fill="#313244", outline=color, width=2)
            draw.text((x + 35, y + 10), icon, fill=color, font=font_icon)
            draw.text((x + (btn_w - font_sm.getlength(label))/2, y + 45), label, fill="white", font=font_sm)
        
        # Nút Back nếu không phải Main Menu
        if self.state != "MENU":
             self.draw_button(draw, 10, 30, 60, 25, "BACK", bg_color=WARN_COLOR, text_color="black")

    def draw_list(self, draw, title):
        """Vẽ danh sách file (Nhạc, Game, Video...)"""
        self.draw_status_bar(draw)
        draw.rectangle((0, 24, WIDTH, 50), fill="#45475a")
        draw.text((10, 28), title, fill="yellow", font=font_md)
        self.draw_button(draw, WIDTH-60, 26, 50, 22, "BACK", bg_color=WARN_COLOR, text_color="black")

        list_y = 55
        item_h = 30
        max_items = 5
        
        if not self.files:
            draw.text((WIDTH//2 - 50, 100), "Trống!", fill="grey", font=font_md)
            return

        display_list = self.files[self.scroll_offset : self.scroll_offset + max_items]

        for i, item in enumerate(display_list):
            is_sel = (self.scroll_offset + i == self.selected_idx)
            bg = "#585b70" if is_sel else BG_COLOR
            fg = "cyan" if is_sel else "white"
            
            name = item['name'] if isinstance(item, dict) else item
            draw.rectangle((5, list_y + i*item_h, WIDTH-5, list_y + (i+1)*item_h - 2), fill=bg)
            draw.text((10, list_y + i*item_h + 5), f"> {name[:28]}", fill=fg, font=font_md)

        # Scrollbar
        if len(self.files) > max_items:
            sb_h = max(20, int((max_items / len(self.files)) * 140))
            sb_y = list_y + int((self.scroll_offset / len(self.files)) * 140)
            draw.rounded_rectangle((WIDTH-5, sb_y, WIDTH, sb_y+sb_h), radius=2, fill=ACCENT_COLOR)

        # Footer Navigation
        btn_y = 205
        self.draw_button(draw, 10, btn_y, 90, 30, "▲ LÊN")
        self.draw_button(draw, 115, btn_y, 90, 30, "CHỌN", bg_color=SUCCESS_COLOR, text_color="black")
        self.draw_button(draw, 220, btn_y, 90, 30, "▼ XUỐNG")

    def draw_player(self, draw):
        """Giao diện nghe nhạc"""
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=PLAYER_BG)
        self.draw_status_bar(draw)
        
        if self.files and 0 <= self.selected_idx < len(self.files):
            title = self.files[self.selected_idx]
            draw.text((20, 40), title[:25], fill="white", font=font_md)

        # Đĩa nhạc
        cx, cy, r = WIDTH//2, 110, 40
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="#11111b", outline="#313244", width=2)
        draw.ellipse((cx-15, cy-15, cx+15, cy+15), fill="#f38ba8")
        
        # Progress Bar giả lập
        draw.rounded_rectangle((40, 160, 280, 166), radius=3, fill="#313244")
        if pygame.mixer.music.get_busy():
            elapsed = time.time() - self.music_start_time
            prog = min(1.0, elapsed / 180.0)
            draw.rounded_rectangle((40, 160, 40 + int(240*prog), 166), radius=3, fill=ACCENT_COLOR)

        # Controls
        btn_y = 180
        self.draw_button(draw, 20, btn_y, 40, 40, "-", bg_color="#313244")
        self.draw_button(draw, 70, btn_y, 50, 40, "|<", bg_color="#45475a")
        
        play_icon = "||" if (pygame.mixer.music.get_busy() and not self.is_paused) else "►"
        self.draw_button(draw, 130, btn_y-5, 60, 50, play_icon, bg_color=ACCENT_COLOR, text_color="black")
        
        self.draw_button(draw, 200, btn_y, 50, 40, ">|", bg_color="#45475a")
        self.draw_button(draw, 260, btn_y, 40, 40, "+", bg_color="#313244")
        
        # Nút thoát nhỏ góc phải trên
        self.draw_button(draw, WIDTH-40, 26, 35, 20, "X", bg_color=WARN_COLOR)

    def draw_reader(self, draw):
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#11111b")
        page_lines = self.book_lines[self.book_current_page*self.book_page_lines : (self.book_current_page+1)*self.book_page_lines]
        y = 10
        for line in page_lines:
            draw.text((10, y), line, fill="#bac2de", font=font_md)
            y += 22
        
        footer_y = 210
        draw.line((0, footer_y-5, WIDTH, footer_y-5), fill="#313244")
        pg_info = f"Trang {self.book_current_page + 1}/{self.book_total_pages}"
        draw.text(((WIDTH-font_sm.getlength(pg_info))/2, footer_y+5), pg_info, fill="grey", font=font_sm)
        
        self.draw_button(draw, 5, footer_y, 60, 25, "Trước", bg_color="#313244")
        self.draw_button(draw, WIDTH-65, footer_y, 60, 25, "Sau", bg_color="#313244")
        self.draw_button(draw, WIDTH-50, 5, 45, 20, "Exit", bg_color=WARN_COLOR)

    def render(self):
        """Điều phối vẽ giao diện"""
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        if self.state == "MENU":
            items = [
                ("Music", "♫", "#f9e2af"), ("Video", "►", "#f38ba8"),
                ("Photo", "☘", "#a6e3a1"), ("Games", "🎮", "#f38ba8"),
                ("Books", "☕", "#89b4fa"), ("BT", "⚙", "#cba6f7")
            ]
            self.draw_menu_grid(draw, "PI MEDIA HOME", items)
            
        elif self.state == "GAMES_MENU":
            items = [("NES", "N", "#e78284"), ("GameBoy", "G", "#a6d189")]
            self.draw_menu_grid(draw, "CHỌN HỆ MÁY", items)
            
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT", "GAME_SELECT_NES", "GAME_SELECT_GB"]:
            title_map = {
                "MUSIC": "Thư viện Nhạc", "VIDEO": "Video", "PHOTO": "Ảnh", "BOOK": "Sách", "BT": "Bluetooth",
                "GAME_SELECT_NES": "Chọn Game NES", "GAME_SELECT_GB": "Chọn Game GB"
            }
            self.draw_list(draw, title_map.get(self.state, "List"))
            
        elif self.state == "PLAYING_MUSIC":
            self.draw_player(draw)
        elif self.state == "READING":
            self.draw_reader(draw)
        
        if self.state not in ["PLAYING_VIDEO", "VIEWING_PHOTO", "RUNNING_GAME"]:
            device.display(img)

    # ---------------- LOGIC & EMULATION ----------------

    def load_files(self, type_key, exts):
        """Load danh sách file từ thư mục"""
        path = DIRS.get(type_key)
        if not path or not os.path.exists(path):
            self.files = []
        else:
            self.files = sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])
        self.selected_idx = 0
        self.scroll_offset = 0

    def run_nes_game(self, rom_name):
        """Chạy NES bằng RetroArch (Subprocess)"""
        rom_path = os.path.join(DIRS["NES"], rom_name)
        
        # Tạm dừng audio của media center để nhường cho RetroArch
        pygame.mixer.quit()
        
        # Vẽ màn hình chờ
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        d = ImageDraw.Draw(img)
        d.text((80, 100), "Launching NES...", fill="red", font=font_lg)
        device.display(img)

        try:
            # Gọi RetroArch. RetroArch cần được config để output ra fb0 hoặc dispmanx
            subprocess.run([
                RETROARCH_BIN, "-L", NES_CORE_PATH, rom_path, "--config", RA_CONFIG_PATH
            ])
        except Exception as e:
            print(f"NES Error: {e}")
        
        # Khởi động lại Audio sau khi thoát game
        pygame.mixer.init()
        self.state = "GAME_SELECT_NES" # Quay lại list game

    def run_gb_game(self, rom_name):
        """Chạy GameBoy bằng PyBoy (Vẽ trực tiếp lên ST7789)"""
        if PyBoy is None: return
        
        rom_path = os.path.join(DIRS["GB"], rom_name)
        pygame.mixer.quit() # Tắt nhạc nền
        
        # Chuẩn bị terminal input
        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        tty.setcbreak(fd)

        try:
            pyboy = PyBoy(rom_path, window="null", sound=True)
            self.state = "RUNNING_GAME"
            
            # Loop Game
            while pyboy.tick():
                # Input từ bàn phím
                k = kb_hit()
                if k == "z": pyboy.button("a")
                elif k == "x": pyboy.button("b")
                elif k == "\n": pyboy.button("start") # Enter
                elif k == "\t": pyboy.button("select") # Tab
                elif k == "w": pyboy.button("up")
                elif k == "s": pyboy.button("down")
                elif k == "a": pyboy.button("left")
                elif k == "d": pyboy.button("right")
                elif k == "\x1b": # ESC để thoát
                    break

                # Lấy hình ảnh từ PyBoy (160x144)
                frame = pyboy.screen.ndarray
                img_gb = Image.fromarray(frame, "RGB")
                
                # Resize fit chiều cao 240 (Landscape)
                # 160x144 -> scale 1.66 -> 266x240
                # Hoặc giữ tỉ lệ 1.5 -> 240x216 (đẹp nhất)
                img_gb = img_gb.resize((240, 216))
                
                # Tạo nền đen 320x240 và paste vào giữa
                bg = Image.new("RGB", (320, 240), "black")
                bg.paste(img_gb, ((320-240)//2, (240-216)//2))
                
                device.display(bg)
                
            pyboy.stop()

        except Exception as e:
            print(f"GB Error: {e}")
        finally:
            # Khôi phục terminal và audio
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
            pygame.mixer.init()
            self.state = "GAME_SELECT_GB"

    # ---------------- TOUCH HANDLING ----------------

    def handle_touch(self, x, y):
        """Xử lý sự kiện cảm ứng cho toàn bộ hệ thống"""
        now = time.time()
        if now - self.last_touch < 0.25: return
        self.last_touch = now

        # 1. MAIN MENU
        if self.state == "MENU":
            # Grid logic 3 cột
            start_y, btn_w, btn_h, gap = 70, 90, 70, 20
            start_x = (WIDTH - (btn_w * 3 + gap * 2)) / 2
            
            row = -1
            if start_y <= y <= start_y + btn_h: row = 0
            elif start_y + btn_h + gap <= y <= start_y + 2*btn_h + gap: row = 1
            
            col = -1
            if start_x <= x <= start_x + btn_w: col = 0
            elif start_x + btn_w + gap <= x <= start_x + 2*btn_w + gap: col = 1
            elif start_x + 2*(btn_w+gap) <= x <= start_x + 3*btn_w + gap: col = 2
            
            if row != -1 and col != -1:
                idx = row * 3 + col
                mapping = [
                    ("MUSIC", ".mp3"), ("VIDEO", ".mp4"), ("PHOTO", ".jpg"),
                    ("GAMES_MENU", None), ("BOOK", ".txt"), ("BT", None)
                ]
                if idx < len(mapping):
                    target, ext = mapping[idx]
                    self.state = target
                    if ext: self.load_files(target, (ext, ".wav", ".png", ".jpeg"))
                    if target == "BT": threading.Thread(target=self.scan_bt).start()
                    self.render()

        # 2. GAMES MENU (Chọn hệ máy)
        elif self.state == "GAMES_MENU":
            if x < 80 and y < 50: # Back Button
                self.state = "MENU"
            else:
                # 2 nút NES / GB
                if y > 70:
                    if x < WIDTH/2: # NES
                        self.state = "GAME_SELECT_NES"
                        self.load_files("NES", (".nes",))
                    else: # GB
                        self.state = "GAME_SELECT_GB"
                        self.load_files("GB", (".gb", ".gbc"))
            self.render()

        # 3. GENERIC LIST (Music, Video, Games...)
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT", "GAME_SELECT_NES", "GAME_SELECT_GB"]:
            # Back Button
            if x > WIDTH - 70 and y < 50:
                self.state = "GAMES_MENU" if "GAME" in self.state else "MENU"
                if "GAME" not in self.state: pygame.mixer.music.stop()
                self.render()
                return

            # Navigation Buttons
            if y > 200:
                if x < 100: # LÊN
                    self.selected_idx = max(0, self.selected_idx - 1)
                    if self.selected_idx < self.scroll_offset: self.scroll_offset = self.selected_idx
                elif x > 220: # XUỐNG
                    if self.files:
                        self.selected_idx = min(len(self.files) - 1, self.selected_idx + 1)
                        if self.selected_idx >= self.scroll_offset + 5: self.scroll_offset += 1
                else: # CHỌN (Select)
                    if not self.files: return
                    item = self.files[self.selected_idx]
                    
                    if self.state == "MUSIC":
                        try:
                            pygame.mixer.music.load(os.path.join(DIRS["MUSIC"], item))
                            pygame.mixer.music.play()
                            self.state = "PLAYING_MUSIC"
                            self.music_start_time = time.time()
                            self.is_paused = False
                        except: pass
                    
                    elif self.state == "GAME_SELECT_NES":
                        self.run_nes_game(item) # Blocking call
                        
                    elif self.state == "GAME_SELECT_GB":
                        self.run_gb_game(item) # Blocking call (Keyboard loop inside)
                        
                    elif self.state == "BOOK":
                        self.prepare_book(item)
                        self.state = "READING"
                        
                    elif self.state == "VIDEO":
                        path = os.path.join(DIRS["VIDEO"], item)
                        threading.Thread(target=self.play_video, args=(path,), daemon=True).start()
                
                self.render()

        # 4. PLAYER UI
        elif self.state == "PLAYING_MUSIC":
            if x > WIDTH - 60 and y < 40: # Exit mini button
                pygame.mixer.music.stop()
                self.state = "MUSIC"
            elif y > 170:
                if x < 60: pygame.mixer.music.set_volume(max(0, self.volume - 0.1)); self.volume -= 0.1
                elif x < 190 and x > 120: # Play/Pause
                    if self.is_paused: pygame.mixer.music.unpause(); self.is_paused = False
                    else: pygame.mixer.music.pause(); self.is_paused = True
                elif x > 250: pygame.mixer.music.set_volume(min(1, self.volume + 0.1)); self.volume += 0.1
            self.render()

        # 5. BOOK READER
        elif self.state == "READING":
            if x > WIDTH-60 and y < 40: self.state = "BOOK"
            elif y > 180:
                if x < 100: self.book_current_page = max(0, self.book_current_page - 1)
                elif x > 220: self.book_current_page = min(self.book_total_pages - 1, self.book_current_page + 1)
            self.render()

    # ---------------- UTILS METHODS ----------------

    def prepare_book(self, filename):
        try:
            path = os.path.join(DIRS["BOOK"], filename)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            self.book_lines = []
            for line in lines:
                if not line.strip(): self.book_lines.append("")
                else: self.book_lines.extend(textwrap.wrap(line.strip(), width=40))
            self.book_total_pages = max(1, math.ceil(len(self.book_lines)/self.book_page_lines))
            self.book_current_page = 0
        except: pass

    def play_video(self, filepath):
        if self.state == "PLAYING_VIDEO": return
        self.state = "PLAYING_VIDEO"
        self.cleanup_media()
        
        # Lệnh ffmpeg stream ra stdout -> đọc bởi Python -> vẽ lên LCD
        # Lưu ý: Cần ffmpeg và ffplay cài sẵn
        video_cmd = [
            'ffmpeg', '-re', '-i', filepath, 
            '-vf', f'scale={WIDTH}:{HEIGHT},format=rgb24', 
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 
            '-loglevel', 'quiet', '-'
        ]
        # Audio chạy tiến trình riêng bằng ffplay
        audio_cmd = ['ffplay', '-nodisp', '-autoexit', '-volume', str(int(self.volume*100)), filepath]
        
        try:
            self.audio_process = subprocess.Popen(audio_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.video_process = subprocess.Popen(video_cmd, stdout=subprocess.PIPE, bufsize=WIDTH*HEIGHT*3)
            
            frame_len = WIDTH * HEIGHT * 3
            while self.state == "PLAYING_VIDEO":
                raw = self.video_process.stdout.read(frame_len)
                if not raw or self.audio_process.poll() is not None: break
                
                img = Image.frombytes('RGB', (WIDTH, HEIGHT), raw)
                device.display(img) # Có thể cần ImageOps.invert(img) tùy driver
                
                if touch.is_touched(): # Chạm để thoát
                    break
        except Exception as e:
            print(e)
        finally:
            self.cleanup_media()
            self.state = "VIDEO"
            self.render()

    def scan_bt(self):
        # Giả lập scan
        self.state = "BT"
        self.files = [{"name": "Scanning..."}]
        self.render()
        time.sleep(1)
        # Thực tế dùng bluetoothctl...
        self.files = [{"name": "Speaker JBL"}, {"name": "Headphone Sony"}]
        self.render()

    def run(self):
        self.render()
        while self.running:
            # Nếu đang chơi nhạc, cần update UI liên tục (cho thanh progress)
            if self.state == "PLAYING_MUSIC" and not self.is_paused:
                self.render()
                time.sleep(0.5)
            else:
                time.sleep(0.1)
                
            # Kiểm tra touch (trừ khi đang chạy game blocking loop)
            if self.state not in ["RUNNING_GAME"]: 
                t_pt = touch.get_touch()
                if t_pt:
                    self.handle_touch(*t_pt)

# ==========================================
# 5. MAIN
# ==========================================
if __name__ == "__main__":
    app = PiSystem()
    
    def signal_handler(sig, frame):
        print("\nExiting System...")
        app.cleanup_media()
        pygame.mixer.quit()
        os.system("stty sane") # Reset terminal
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    app.run()
