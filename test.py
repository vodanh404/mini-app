import os,sys,time,subprocess,threading,signal
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
from pynput import keyboard
import numpy as np
import requests
import json
import smtplib
from email.mime.text import MIMEText
import webview 
import wikipedia
import cv2
import pyaudio
import wave

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
    "GAMES": os.path.join(USER_HOME, "Roms/gb"),
    "RECORDINGS": os.path.join(USER_HOME, "Recordings"),
}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# Khởi tạo Fonts
def load_font(size):
    try:
        # Ưu tiên font hỗ trợ Unicode tốt để hiển thị icon và tiếng Việt
        return ImageFont.truetype("/usr/share/fonts/truetype/jetbrains-nerd/JetBrainsMonoNerdFont-Bold.ttf", size)
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
    serial_lcd = luma_spi(port=0, device=0, gpio_DC=24, gpio_RST=25, baudrate=62500000)
    device = st7789(serial_lcd, width=WIDTH, height=HEIGHT, rotate=0)
    
    device.backlight(True)
    device.contrast(255)
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
# 3. CLASS CHÍNH: MEDIA CENTER (Tích hợp GameBoy từ main.py và Chat Bot từ chat_bot.py)
# ==========================================

GEMINI_API_KEY = "AIzaSyBFQc4ATm3WY5oD8BWHIsd3J4K8kxZ-GuY"  
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

# Định nghĩa TONE_MARKERS cho dấu tiếng Việt
TONE_MARKERS = {
    'a': ['a', 'à', 'á', 'ả', 'ã', 'ạ'],
    'A': ['A', 'À', 'Á', 'Ả', 'Ã', 'Ạ'],
    'e': ['e', 'è', 'é', 'ẻ', 'ẽ', 'ẹ'],
    'E': ['E', 'È', 'É', 'Ẻ', 'Ẽ', 'Ẹ'],
    'i': ['i', 'ì', 'í', 'ỉ', 'ĩ', 'ị'],
    'I': ['I', 'Ì', 'Í', 'Ỉ', 'Ĩ', 'Ị'],
    'o': ['o', 'ò', 'ó', 'ỏ', 'õ', 'ọ'],
    'O': ['O', 'Ò', 'Ó', 'Ỏ', 'Õ', 'Ọ'],
    'u': ['u', 'ù', 'ú', 'ủ', 'ũ', 'ụ'],
    'U': ['U', 'Ù', 'Ú', 'Ủ', 'Ũ', 'Ụ'],
    'y': ['y', 'ỳ', 'ý', 'ỷ', 'ỹ', 'ỵ'],
    'Y': ['Y', 'Ỳ', 'Ý', 'Ỷ', 'Ỹ', 'Ỵ'],
    'â': ['â', 'ầ', 'ấ', 'ẩ', 'ẫ', 'ậ'],
    'Â': ['Â', 'Ầ', 'Ấ', 'Ẩ', 'Ẫ', 'Ậ'],
    'ă': ['ă', 'ằ', 'ắ', 'ẳ', 'ẵ', 'ặ'],
    'Ă': ['Ă', 'Ằ', 'Ắ', 'Ẳ', 'Ẵ', 'Ặ'],
    'ê': ['ê', 'ề', 'ế', 'ể', 'ễ', 'ệ'],
    'Ê': ['Ê', 'Ề', 'Ế', 'Ể', 'Ễ', 'Ệ'],
    'ô': ['ô', 'ồ', 'ố', 'ổ', 'ỗ', 'ộ'],
    'Ô': ['Ô', 'Ồ', 'Ố', 'Ổ', 'Ỗ', 'Ộ'],
    'ơ': ['ơ', 'ờ', 'ớ', 'ở', 'ỡ', 'ợ'],
    'Ơ': ['Ơ', 'Ờ', 'Ớ', 'Ở', 'Ỡ', 'Ợ'],
    'ư': ['ư', 'ừ', 'ứ', 'ử', 'ữ', 'ự'],
    'Ư': ['Ư', 'Ừ', 'Ứ', 'Ử', 'Ữ', 'Ự'],
    'đ': ['đ'],  # Không cycle
    'Đ': ['Đ']
}

# --- Cấu hình Email ---
sender_email = "ungdungthu3@gmail.com"
sender_name = 'pi_phone'
sender_app_password = "sknt raic nnbx pfrr"
recipient_email = ['dinhphuchd2008@gmail.com']
current_email_index = 0
email_subject = "Tin nhắn từ Myphone"

items = [   
                ("Music", "♫", "#f9e2af"), ("Video", "►", "#f38ba8"),
                ("Photo", "☘", "#a6e3a1"), ("Books", "☕", "#89b4fa"),
                ("Games", "🎮", "#f9e2af"), ("Chat", "💬", "#cba6f7"),
                ("Wikipedia", "🌐", "#bd93f9"), ("Gửi Thư", "✉", "#f5c2e7"),
                ("Camera", "📷", "#fab387"),   ("Cài Đặt", "⚙", "#cba6f7")]
class PiMediaCenter:
    def __init__(self):
        self.state = "MENU"  # MENU, MUSIC, VIDEO, PHOTO, BOOK, BT, READING, PLAYING_MUSIC, PLAYING_VIDEO, VIEWING_PHOTO, GAMES, PLAYING_GAME, CHAT, EMAIL, SETTINGS
        self.menu_page = 0   # Thêm biến cho trang menu
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
        self.is_web_reading = False  # Biến mới để phân biệt đọc web hay sách
        
        # Music Player
        self.volume = 0.5
        self.music_start_time = 0
        self.music_paused_time = 0
        self.is_paused = False
        
        # Video
        self.is_video_playing = False
        self.video_process = None
        self.audio_process = None
        
        # GameBoy (từ main.py)
        self.pyboy = None
        
        # Chat Bot variables
        self.current_message_text = ""
        self.last_physical_key_multi_tap = None
        self.multi_tap_press_count = 0
        self.last_multi_tap_time = 0
        self.MULTI_TAP_TIMEOUT_MS_MSG = 800
        self.ac_press_count = 0
        self.last_ac_press_time = 0
        self.AC_TIMEOUT_MS = 500
        self.MAX_CHARS_PER_LINE = 20
        self.LINE_SPACING = 15
        self.MSG_START_Y = 10
        self.chat_scroll_offset = 0
        self.needs_redraw = True

        self.messages_history = []
        self.is_shift = False
        self.kb_mode = "abc"
        self.chat_needs_update = False  # Flag mới để cập nhật UI từ thread

        self.current_email_index = 0
        self.device = device
        self.frame_buffer = np.zeros((HEIGHT, WIDTH, 3), dtype= np.uint8)
        self.layout_abc = [

            ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
            ["a", "s", "d","đ", "f", "g", "h", "j", "k", "l"],
            ["Shift", "z", "x", "c", "v", "b", "n", "m", "Del"],
            ["123","ơ", "ư", "ă","Space", ",", ".", "Send"]
        ]
        
        # Layout số và ký tự
        self.layout_123 = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["@", "#", "$", "&", "-", "+", "(", ")", "/", "*"],
            ["abc", "!", "?", "'", "\"", ":", ";", ",", "Del"],
            ["123", "â", "ê", "ô","Space", "_", "=", "Send"]
        ]

        # Settings items
        self.settings_items = ["Kết Nối WiFi", "Bluetooth"]


        self.cap = None                     # OpenCV VideoCapture
        self.is_recording_video = False
        self.video_writer = None
        self.video_path = None

        self.is_recording_audio = False
        self.audio_frames = []
        self.audio_stream = None
        self.audio_p = None
        self.audio_recording_thread = None

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
        if self.pyboy:
            self.pyboy.stop()
            self.pyboy = None

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
        """Vẽ Menu chính (Chia thành 2 trang, mỗi trang 6 items, nhưng tổng 7 nên trang 1:6, trang 2:1)"""
        self.draw_status_bar(draw)
        title = "PI MEDIA HOME"
        bbox = draw.textbbox((0,0), title, font=font_lg)
        draw.text(((WIDTH - (bbox[2]-bbox[0]))/2, 28), title, fill=ACCENT_COLOR, font=font_lg)

        page_items = items[self.menu_page * 6 : (self.menu_page + 1) * 6]
        
        start_y = 55
        btn_w, btn_h = 140, 50  # Giảm chiều cao để phù hợp
        gap = 5
        cols = 2  # 2 cột mỗi trang
        rows = math.ceil(len(page_items) / cols)
        start_x = (WIDTH - (btn_w * cols + gap * (cols - 1))) / 2

        for i, (label, icon, color) in enumerate(page_items):
            row = i // cols
            col = i % cols
            x = start_x + col * (btn_w + gap)
            y = start_y + row * (btn_h + gap)
            
            draw.rounded_rectangle((x, y, x+btn_w, y+btn_h), radius=10, fill="#313244", outline=color, width=2)
            draw.text((x + (btn_w / 2) - 10, y + 5), icon, fill=color, font=font_icon)
            draw.text((x + (btn_w - font_sm.getbbox(label)[2])/2, y + 30), label, fill="white", font=font_sm)  # Sửa getlength -> getbbox cho tương thích Pillow cũ

        # Nút chuyển trang
        total_pages = math.ceil(len(items) / 6)
        if total_pages > 1:
            btn_y = HEIGHT - 35
            if self.menu_page > 0:
                self.draw_button(draw, 10, btn_y, 70, 25, "◀ Trước", bg_color="#45475a")
            if self.menu_page < total_pages - 1:
                self.draw_button(draw, WIDTH - 80, btn_y, 70, 25, "Sau ▶", bg_color="#45475a")

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
            icon = ">" if "." not in name[-4:] else ">"
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
        
        # Thêm tiêu đề phân biệt web hay sách
        title_text = "Nội dung Web" if self.is_web_reading else "Nội dung Sách"
        draw.text((10, 5), title_text, fill=ACCENT_COLOR, font=font_md)
        
        if not self.book_lines:
            draw.text((20, 100), "Không thể đọc nội dung file!", fill=WARN_COLOR, font=font_md)
        else:
            # Lấy các dòng của trang hiện tại
            start_line = self.book_current_page * self.book_page_lines
            end_line = start_line + self.book_page_lines
            page_content = self.book_lines[start_line:end_line]
            
            y = 30  # Dịch xuống để có chỗ cho tiêu đề
            margin_x = 10
            for line in page_content:
                draw.text((margin_x, y), line, fill=READER_TEXT, font=font_md)
                y += 20 # Khoảng cách dòng (Line height)

        # Footer (Thanh điều hướng trang)
        footer_y = 210
        draw.line((0, footer_y - 5, WIDTH, footer_y - 5), fill="#313244")
        
        page_info = f"Trang {self.book_current_page + 1}/{self.book_total_pages}"
        # Căn giữa số trang
        info_w = font_sm.getbbox(page_info)[2]
        draw.text(((WIDTH - info_w)/2, footer_y + 5), page_info, fill="#585b70", font=font_sm)
        
        self.draw_button(draw, 5, footer_y, 60, 25, "Trước", bg_color="#313244", icon_font=font_sm)
        self.draw_button(draw, WIDTH - 65, footer_y, 60, 25, "Sau", bg_color="#313244", icon_font=font_sm)

    def draw_chat_ui(self, draw):
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG_COLOR)
        self.draw_status_bar(draw)

        # 1. Khung hiển thị tin nhắn (Thu nhỏ hơn để nhường chỗ cho bàn phím đầy đủ)
        draw.rectangle((5, 26, WIDTH-5, 110), fill="#181825", outline="#313244")
        y_pos = 30
        display_msgs = self.messages_history + [f"Bạn: {self.current_message_text}_"]
        all_lines = []
        for msg in display_msgs:
            all_lines.extend(textwrap.wrap(msg, width=40))  # Giảm width để fit tốt hơn
        num_display_lines = 5
        self.chat_scroll_offset = max(0, min(len(all_lines) - num_display_lines, self.chat_scroll_offset))
        start_line = max(0, len(all_lines) - num_display_lines - self.chat_scroll_offset)
        for line in all_lines[start_line : start_line + num_display_lines]:
            draw.text((10, y_pos), line, fill=TEXT_COLOR, font=font_sm)
            y_pos += 14

        # 2. Vẽ Bàn phím
        curr_layout = self.layout_abc if self.kb_mode == "abc" else self.layout_123
        kb_y = 115
        key_h = 28
        gap = 2
        
        for r_idx, row in enumerate(curr_layout):
            # Tính toán độ rộng phím để dàn đều
            n_keys = len(row)
            total_gap = (n_keys + 1) * gap
            base_w = (WIDTH - total_gap) // 10 # Chia theo 10 phím chuẩn hàng 1
            
            # Căn lề giữa cho các hàng ít phím hơn (hàng 2, 3, 4)
            row_width = sum([self.get_key_width(k, base_w) for k in row]) + (n_keys-1)*gap
            start_x = (WIDTH - row_width) // 2
            
            curr_x = start_x
            for key in row:
                w = self.get_key_width(key, base_w)
                
                # Màu sắc phím
                bg = "#45475a"
                t_col = "white"
                if key in ["Shift", "Del", "123", "abc"]: bg = "#313244"
                if key == "Send": bg = SUCCESS_COLOR; t_col = "black"
                if key == "Shift" and self.is_shift: bg = ACCENT_COLOR; t_col = "black"

                # Chỉnh text hiển thị (Viết hoa nếu Shift)
                disp = key
                if self.is_shift and len(key) == 1 and self.kb_mode == "abc":
                    disp = key.upper()
                
                self.draw_button(draw, curr_x, kb_y, w, key_h, disp, bg_color=bg, text_color=t_col)
                curr_x += w + gap
            kb_y += key_h + gap

    def draw_email_ui(self, draw):
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG_COLOR)
        self.draw_status_bar(draw)

        # Hiển thị người nhận
        recipient_name = recipient_email[current_email_index].split('@')[0]
        draw.text((10, 30), f"Đến: {recipient_name}", fill=TEXT_COLOR, font=font_sm)

        # Khung hiển thị tin nhắn
        draw.rectangle((5, 50, WIDTH-5, 110), fill="#181825", outline="#313244")
        y_pos = 55
        display_text_with_cursor = self.current_message_text + "_"
        lines = textwrap.wrap(display_text_with_cursor, width=40)
        num_display_lines = 4
        start_line = max(0, len(lines) - num_display_lines)
        for line in lines[start_line : start_line + num_display_lines]:
            draw.text((10, y_pos), line, fill=TEXT_COLOR, font=font_sm)
            y_pos += 14

        # Vẽ Bàn phím (tương tự chat)
        curr_layout = self.layout_abc if self.kb_mode == "abc" else self.layout_123
        kb_y = 115
        key_h = 28
        gap = 2
        
        for r_idx, row in enumerate(curr_layout):
            n_keys = len(row)
            total_gap = (n_keys + 1) * gap
            base_w = (WIDTH - total_gap) // 10
            
            row_width = sum([self.get_key_width(k, base_w) for k in row]) + (n_keys-1)*gap
            start_x = (WIDTH - row_width) // 2
            
            curr_x = start_x
            for key in row:
                w = self.get_key_width(key, base_w)
                
                bg = "#45475a"
                t_col = "white"
                if key in ["Shift", "Del", "123", "abc"]: bg = "#313244"
                if key == "Send": bg = SUCCESS_COLOR; t_col = "black"
                if key == "Shift" and self.is_shift: bg = ACCENT_COLOR; t_col = "black"

                disp = key
                if self.is_shift and self.kb_mode == "abc" and len(key) == 1:
                    disp = key.upper()
                
                self.draw_button(draw, curr_x, kb_y, w, key_h, disp, bg_color=bg, text_color=t_col)
                curr_x += w + gap
            kb_y += key_h + gap

    def draw_web_input_ui(self, draw):
        """Giao diện nhập câu hỏi cho Wikipedia (tương tự email UI)"""
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG_COLOR)
        self.draw_status_bar(draw)

        # Hiển thị tiêu đề
        draw.text((10, 30), "Tìm trên Wikipedia:", fill=TEXT_COLOR, font=font_sm)

        # Khung hiển thị câu hỏi
        draw.rectangle((5, 50, WIDTH-5, 110), fill="#181825", outline="#313244")
        y_pos = 55
        display_text_with_cursor = self.current_message_text + "_"
        lines = textwrap.wrap(display_text_with_cursor, width=40)
        num_display_lines = 4
        start_line = max(0, len(lines) - num_display_lines)
        for line in lines[start_line : start_line + num_display_lines]:
            draw.text((10, y_pos), line, fill=TEXT_COLOR, font=font_sm)
            y_pos += 14

        # Vẽ Bàn phím (tương tự chat)
        curr_layout = self.layout_abc if self.kb_mode == "abc" else self.layout_123
        kb_y = 115
        key_h = 28
        gap = 2
        
        for r_idx, row in enumerate(curr_layout):
            n_keys = len(row)
            total_gap = (n_keys + 1) * gap
            base_w = (WIDTH - total_gap) // 10
            
            row_width = sum([self.get_key_width(k, base_w) for k in row]) + (n_keys-1)*gap
            start_x = (WIDTH - row_width) // 2
            
            curr_x = start_x
            for key in row:
                w = self.get_key_width(key, base_w)
                
                bg = "#45475a"
                t_col = "white"
                if key in ["Shift", "Del", "123", "abc"]: bg = "#313244"
                if key == "Send": bg = SUCCESS_COLOR; t_col = "black"
                if key == "Shift" and self.is_shift: bg = ACCENT_COLOR; t_col = "black"

                disp = key
                if self.is_shift and self.kb_mode == "abc" and len(key) == 1:
                    disp = key.upper()
                
                self.draw_button(draw, curr_x, kb_y, w, key_h, disp, bg_color=bg, text_color=t_col)
                curr_x += w + gap
            kb_y += key_h + gap

    def get_key_width(self, key, base_w):
        """Hàm định nghĩa độ rộng từng phím đặc biệt"""
        if key == "Space": return base_w * 4
        if key in ["Shift", "Del", "123", "abc", "Send"]: return int(base_w * 1.5)
        return base_w

    def render(self):
        """Hàm render chính, điều phối vẽ dựa trên state"""
        image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(image)
        if self.state == "WEB_INPUT":     
            self.draw_web_input_ui(draw)
        elif self.state == "MENU":
            self.draw_menu(draw)
        elif self.state == "CAMERA":
            self.enter_camera_mode()
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT", "SETTINGS", "GAMES"]:
            title_map = {"MUSIC": "Thư viện Nhạc", "VIDEO": "Thư viện Video", "PHOTO": "Thư viện Ảnh", "BOOK": "Kệ Sách", "BT": "Thiết bị Bluetooth", "SETTINGS": "Cài Đặt", "GAMES": "Thư viện Games"}
            self.draw_list(draw, title_map.get(self.state, ""))
        elif self.state == "PLAYING_MUSIC":
            self.draw_player_ui(draw)
        elif self.state == "READING":
            self.draw_reader(draw)
        elif self.state == "CHAT":
            self.draw_chat_ui(draw)
        elif self.state == "EMAIL":
            self.draw_email_ui(draw)
        elif self.state == "VIEWING_PHOTO":
            pass 
        if self.state != "PLAYING_VIDEO" and self.state != "VIEWING_PHOTO" and self.state != "PLAYING_GAME" and self.state != "CAMERA":
            device.display(image)

    # --- LOGIC XỬ LÝ (BACKEND) ---

    def load_files(self, type_key, ext):
        self.files = sorted([f for f in os.listdir(DIRS[type_key]) if f.lower().endswith(ext)])
        self.selected_idx = 0
        self.scroll_offset = 0

    def prepare_book_content(self, filename):
        """Xử lý nội dung sách: Đọc file -> Wrap text -> Chia trang"""
        self.is_web_reading = False  # Đặt là False khi đọc sách
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

    def do_connect_wifi(self):
        # Giả sử kết nối WiFi sử dụng subprocess (thay thế bằng SSID và password thực tế)
        try:
            ssid = "your_ssid"  # Thay bằng SSID thực
            password = "your_password"  # Thay bằng password thực
            subprocess.run(["nmcli", "device", "wifi", "connect", ssid, "password", password])
            return True
        except:
            return False

    def send_email(self, message):
        try:
            msg = MIMEText(message)
            msg['Subject'] = email_subject
            msg['From'] = sender_email
            msg['To'] = recipient_email[current_email_index]

            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(sender_email, sender_app_password)
            server.sendmail(sender_email, recipient_email[current_email_index], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"Email Error: {e}")
            return False

    def scan_bt(self):
        self.bt_scanning = True
        self.bt_devices = []
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        d = ImageDraw.Draw(img)
        d.text((80, 100), "Đang quét BT...", fill="lime", font=font_md)
        device.display(img)
        
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
                img = ImageOps.invert(img)  # Bỏ comment nếu màu sai
                device.display(img)

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
            img = ImageOps.invert(img)  # Bỏ comment nếu màu sai
            device.display(img)
            
            while True:
                time.sleep(0.1)
                if touch.is_touched():
                    time.sleep(0.2)
                    break
        except Exception as e:
            print(e)
        self.state = "PHOTO"
        self.render()

    def run_game(self):
        """Hàm chạy game hoàn chỉnh: Phóng đại màn hình + Nhận bàn phím"""
        if not self.files or self.selected_idx < 0: return
        path = os.path.join(DIRS["GAMES"], self.files[self.selected_idx])
        
        try:
            # 1. Khởi tạo PyBoy (tắt window mặc định để tăng tốc)
            self.pyboy = PyBoy(path, window="null")
            self.pyboy.set_emulation_speed(1)
            self.state = "PLAYING_GAME"

            # 2. Thiết lập Input bàn phím
            key_map = {
                keyboard.Key.up: WindowEvent.PRESS_ARROW_UP,
                keyboard.Key.down: WindowEvent.PRESS_ARROW_DOWN,
                keyboard.Key.left: WindowEvent.PRESS_ARROW_LEFT,
                keyboard.Key.right: WindowEvent.PRESS_ARROW_RIGHT,
                'a': WindowEvent.PRESS_BUTTON_A,
                's': WindowEvent.PRESS_BUTTON_B,
                keyboard.Key.enter: WindowEvent.PRESS_BUTTON_START,
                keyboard.Key.shift: WindowEvent.PRESS_BUTTON_SELECT
            }
            release_map = {
                keyboard.Key.up: WindowEvent.RELEASE_ARROW_UP,
                keyboard.Key.down: WindowEvent.RELEASE_ARROW_DOWN,
                keyboard.Key.left: WindowEvent.RELEASE_ARROW_LEFT,
                keyboard.Key.right: WindowEvent.RELEASE_ARROW_RIGHT,
                'a': WindowEvent.RELEASE_BUTTON_A,
                's': WindowEvent.RELEASE_BUTTON_B,
                keyboard.Key.enter: WindowEvent.RELEASE_BUTTON_START,
                keyboard.Key.shift: WindowEvent.RELEASE_BUTTON_SELECT
            }

            def on_press(key):
                if key == keyboard.Key.esc:
                    self.state = "GAMES"
                    return False
                k = key.char.lower() if hasattr(key, 'char') and key.char else key
                if k in key_map: self.pyboy.send_input(key_map[k])

            def on_release(key):
                k = key.char.lower() if hasattr(key, 'char') and key.char else key
                if k in release_map: self.pyboy.send_input(release_map[k])

            self.keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self.keyboard_listener.start()

            # 3. Cấu hình hiển thị (Phóng đại)
            frame_count = 0
            SKIP_LIMIT = 20
            # Vẽ 20 FPS để giữ game chạy mượt 100% tốc độ

            while self.state == "PLAYING_GAME":
                self.pyboy.tick()
                frame_count += 1
                
                if frame_count % SKIP_LIMIT == 0:
                    # Lấy mảng từ PyBoy
                    raw_array = self.pyboy.screen.ndarray 
                    
                    # Chuyển thành Image và phóng to (Dùng NEAREST để nhanh nhất)
                    gb_img = Image.fromarray(raw_array)
                    resized_gb = gb_img.resize((266, 240), resample=Image.NEAREST)
                    # Dán vào giữa màn hình 320x240
                    full_canvas = Image.new("RGB", (WIDTH, HEIGHT), "black")
                    full_canvas.paste(resized_gb, ((WIDTH - 266) // 2, 0))
                    full_canvas = ImageOps.invert(full_canvas)
                    # Đẩy ra màn hình ST7789
                    self.device.display(full_canvas)

        except Exception as e:
            print(f"Lỗi: {e}")
        finally:
            if self.keyboard_listener: self.keyboard_listener.stop()
            if self.pyboy: self.pyboy.stop()
            self.state = "GAMES"
            self.render()

    def fetch_wikipedia_summary(self, query):
        if not query.strip():
            return "Vui lòng nhập từ khóa tìm kiếm."

        try:
        # Thiết lập ngôn ngữ là tiếng Việt
            wikipedia.set_lang("vi")
        
        # Tìm kiếm và lấy trang đầu tiên phù hợp
            search_results = wikipedia.search(query.strip(), results=1)
            if not search_results:
                return "Không tìm thấy kết quả phù hợp."

            title = search_results[0]

            # Lấy tóm tắt (summary) – thư viện tự động lấy đoạn đầu đẹp
            summary = wikipedia.summary(title, sentences=5, auto_suggest=True)
        
            return summary.strip()
    
        except wikipedia.exceptions.DisambiguationError as e:
        # Nếu có nhiều kết quả, lấy trang đầu tiên trong danh sách gợi ý
            if e.options:
               return wikipedia.summary(e.options[0], sentences=5)
            return "Có nhiều kết quả trùng tên, thử từ khóa cụ thể hơn."
    
        except wikipedia.exceptions.PageError:
            return "Không tìm thấy trang Wikipedia phù hợp."
    
        except Exception as e:
            return f"Lỗi: {str(e)}. Kiểm tra mạng và thử lại nhé!"

    def process_wikipedia_query(self, query):
        """Xử lý query và hiển thị tóm tắt trong reader"""
        summary = self.fetch_wikipedia_summary(query)
        
        # Xử lý wrap text
        chars_per_line = 36
        self.book_lines = textwrap.wrap(summary, width=chars_per_line)
        self.book_page_lines = 9
        self.book_current_page = 0
        self.book_total_pages = math.ceil(len(self.book_lines) / self.book_page_lines)
        if self.book_total_pages == 0: self.book_total_pages = 1
        
        self.is_web_reading = True
        self.state = "READING"
        self.render()

    def reset_web_input_state(self):
        self.current_message_text = ""
        self.kb_mode = "abc"
        self.is_shift = False

    # --- Chat Bot Functions (tích hợp và điều chỉnh từ chat_bot.py) ---
    def apply_tone_mark(self, word):
        """Bổ sung dấu thanh điệu vào nguyên âm cuối cùng của từ."""
        if not word:
            return ""
        
        # Tìm nguyên âm cuối cùng trong từ
        vowel_positions = [i for i, char in enumerate(word) if char in sum(TONE_MARKERS.values(), [])]
        if not vowel_positions:
            return word
            
        vowel_index = vowel_positions[-1]
        current_vowel = word[vowel_index]
        
        # Tìm nguyên âm gốc (không dấu) tương ứng
        base_vowel = None
        for key, variants in TONE_MARKERS.items():
            if current_vowel in variants:
                base_vowel = key
                break
        
        if base_vowel:
            variants = TONE_MARKERS[base_vowel]
            try:
                current_index = variants.index(current_vowel)
                next_index = (current_index + 1) % len(variants)
                new_vowel = variants[next_index]
                new_word = word[:vowel_index] + new_vowel + word[vowel_index+1:]
                return new_word
            except ValueError:
                return word
        return word

    def apply_tone_mark_on_last_word(self):
        """Áp dụng cycle dấu cho từ cuối cùng trong tin nhắn."""
        words = self.current_message_text.split(' ')
        if words and words[-1]:
            last_word = words[-1]
            new_last_word = self.apply_tone_mark(last_word)
            words[-1] = new_last_word
            self.current_message_text = ' '.join(words)

    def process_chat_response(self, prompt):
        """Hàm này chạy trong một luồng riêng để tránh treo máy"""
        # Thêm thông báo đang chờ
        self.messages_history.append("Gemini: Đang suy nghĩ...")
        self.chat_needs_update = True  # Set flag để main thread render
        
        # Gọi API
        ans = self.call_gemini_api(prompt)
        
        # Xóa dòng "Đang suy nghĩ..." và thay bằng câu trả lời thật
        if self.messages_history and "Đang suy nghĩ..." in self.messages_history[-1]:
            self.messages_history.pop()
            
        if ans:
            # Lưu ý: Gemini thường trả về Markdown (dấu * hoặc #), 
            # chúng ta nên xóa bớt để hiển thị trên màn hình nhỏ đẹp hơn
            clean_ans = ans.replace("*", "").replace("#", "")
            self.messages_history.append(f"Gemini: {clean_ans}")
        else:
            self.messages_history.append("Gemini: Lỗi kết nối hoặc API Key sai.")
        
        self.chat_scroll_offset = 0
        self.chat_needs_update = True  # Set flag lại

    # --- 2. HÀM GỌI API GEMINI (CẬP NHẬT TIMEOUT) ---
    def call_gemini_api(self, prompt):
        headers = {'Content-Type': 'application/json'}
        prompt_with_lang = f"{prompt}\n\nHãy trả lời bằng tiếng Việt ngắn gọn, dưới 50 từ."
        payload = {"contents": [{"parts": [{"text": prompt_with_lang}]}]}
        
        try:
            # Thêm timeout=5 để không bị đợi quá lâu nếu mạng lag
            response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                return text
            else:
                print(f"Lỗi API: {response.status_code}")
                return None
        except Exception as e:
            print(f"Network Error: {e}")
            return None

    def wrap_text(self, text, max_chars_per_line):
        """Chia văn bản thành các dòng, không cắt từ giữa chừng."""
        lines = []
        if not text:
            return [""]
        
        words = text.split(' ')
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= max_chars_per_line:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines

    def reset_chat_state(self):
        self.current_message_text = ""
        self.last_physical_key_multi_tap = None
        self.multi_tap_press_count = 0
        self.last_multi_tap_time = 0
        self.chat_scroll_offset = 0
        self.needs_redraw = True
        self.ac_press_count = 0
        self.last_ac_press_time = 0
        self.messages_history = []

    def reset_email_state(self):
        self.current_message_text = ""
        self.kb_mode = "abc"
        self.is_shift = False
        global current_email_index
        self.current_email_index = 0
# --- USB CAMERA INIT ---

    def find_camera_index(self):
        """Tìm index camera USB khả dụng (thử từ 0 đến 10)"""
        for i in range(11):  # Thử tối đa 10 index
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
                if cap.get(cv2.CAP_PROP_FRAME_WIDTH) == WIDTH:  # Kiểm tra nếu mở thành công
                    print(f"Đã tìm thấy camera tại index {i}")
                    return i
                cap.release()
        return -1

    def enter_camera_mode(self):
        """Khởi tạo camera và bắt đầu luồng preview"""
        self.state = "CAMERA"
        self.is_recording_video = False
        self.video_writer = None
        self.show_flash = False  # Biến mới cho hiệu ứng flash
        
        # Tạo thư mục lưu trữ nếu chưa có
        os.makedirs(DIRS["PHOTO"], exist_ok=True)
        os.makedirs(DIRS["VIDEO"], exist_ok=True)

        try:
            # Tìm index camera khả dụng
            camera_index = self.find_camera_index()
            if camera_index == -1:
                print("Không tìm thấy camera USB nào!")
                self.state = "MENU"
                self.render()
                return
            
            # Khởi tạo OpenCV Camera với index tìm được
            self.cap = cv2.VideoCapture(camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
            
            if not self.cap.isOpened():
                print("Không thể mở Camera!")
                self.state = "MENU"
                self.render()
                return
        except Exception as e:
            print(f"Lỗi khởi tạo Camera: {e}")
            self.state = "MENU"
            self.render()
            return

        # Bắt đầu luồng cập nhật hình ảnh camera
        self.camera_thread = threading.Thread(target=self.update_camera_preview)
        self.camera_thread.daemon = True
        self.camera_thread.start()

    def exit_camera_mode(self):
        """Dọn dẹp tài nguyên khi thoát Camera"""
        self.state = "MENU" # Chuyển state để thread preview tự dừng
        
        # Dừng quay video nếu đang quay
        if self.is_recording_video:
            self.toggle_video_recording()

        # Giải phóng camera
        if hasattr(self, 'cap') and self.cap is not None:
            self.cap.release()
            self.cap = None
        
        print("Đã thoát chế độ Camera.")
        self.render() # Vẽ lại menu chính

    def update_camera_preview(self):
        """Luồng chạy ngầm để lấy hình ảnh từ camera và hiển thị"""
        flash_counter = 0 # Biến đếm để tạo hiệu ứng flash
        
        while self.state == "CAMERA" and hasattr(self, 'cap') and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                continue

            # 1. Xử lý ghi hình (Recording)
            if self.is_recording_video and self.video_writer:
                self.video_writer.write(frame)

            # 2. Xử lý hiển thị (Display)
            # OpenCV dùng BGR, màn hình/PIL dùng RGB -> Cần convert
            frame_rgb = frame.copy()
            frame_rgb = cv2.flip(frame,1)
            frame_rgb = frame_rgb[..., ::-1]
            
            # Resize nếu frame không đúng kích thước màn hình (phòng hờ)
            if frame_rgb.shape[1] != WIDTH or frame_rgb.shape[0] != HEIGHT:
                frame_rgb = cv2.resize(frame_rgb, (WIDTH, HEIGHT))

            # Tạo ảnh PIL từ frame camera
            cam_image = Image.fromarray(frame_rgb)
            draw = ImageDraw.Draw(cam_image)

            # --- VẼ GIAO DIỆN UI LÊN TRÊN CAMERA ---
            
            # Nút CHỤP (Tròn trắng bên phải)
            draw.ellipse((270, 100, 310, 140), outline="white", width=2)
            draw.ellipse((275, 105, 305, 135), fill="white") # Nút shutter

            # Nút QUAY VIDEO (Tròn đỏ bên phải dưới)
            rec_color = "red" if not self.is_recording_video else "gray"
            draw.ellipse((270, 160, 310, 200), outline="white", width=2)
            draw.ellipse((275, 165, 305, 195), fill=rec_color)

            # Nút BACK (Góc trái trên)
            draw.text((10, 10), "< BACK", font=font_sm, fill="white")

            # Chỉ báo đang quay (REC + chấm đỏ nhấp nháy)
            if self.is_recording_video:
                if int(time.time() * 2) % 2 == 0: # Nhấp nháy mỗi 0.5s
                    draw.ellipse((10, 220, 25, 235), fill="red")
                draw.text((30, 218), "REC", font=font_sm, fill="red")

            # Hiệu ứng Flash khi chụp ảnh
            if self.show_flash:
                # Vẽ đè một lớp trắng bán trong suốt hoặc trắng tinh
                draw.rectangle((0,0,WIDTH,HEIGHT), fill=(255,255,255,128))  # Bán trong suốt (nếu PIL hỗ trợ alpha)
                flash_counter += 1
                if flash_counter > 2: # Hiện flash trong khoảng 2 frame
                    self.show_flash = False
                    flash_counter = 0
            cam_image = ImageOps.invert(cam_image)
            # Cập nhật trực tiếp lên màn hình (bỏ qua hàm self.render mặc định để mượt hơn)
            self.device.display(cam_image)
            
            # Giữ framerate ổn định (~30fps)
            time.sleep(0.03)

    def take_photo(self):
        """Chụp ảnh từ frame hiện tại"""
        if hasattr(self, 'cap') and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(DIRS["PHOTO"], f"IMG_{timestamp}.jpg")
                cv2.imwrite(filename, frame)
                print(f"Đã lưu ảnh: {filename}")
                
                # Kích hoạt cờ flash để thread preview xử lý hiệu ứng
                self.show_flash = True

    def toggle_video_recording(self):
        """Bật/Tắt quay video"""
        if not self.is_recording_video:
            # BẮT ĐẦU QUAY
            if hasattr(self, 'cap') and self.cap.isOpened():
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(DIRS["VIDEO"], f"VID_{timestamp}.avi")
                
                # Cấu hình VideoWriter (MJPG thường nhẹ cho Raspberry Pi)
                fourcc = cv2.VideoWriter_fourcc(*'MJPG') 
                self.video_writer = cv2.VideoWriter(filename, fourcc, 20.0, (WIDTH, HEIGHT))
                
                self.is_recording_video = True
                print(f"Bắt đầu quay: {filename}")
        else:
            # DỪNG QUAY
            self.is_recording_video = False
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            print("Đã dừng quay video.")

    def handle_touch_camera(self, x, y):
        """Xử lý cảm ứng riêng cho màn hình Camera"""
        # 1. Nút BACK (Góc trái trên ~ 0-80x, 0-40y)
        if 0 < x < 80 and 0 < y < 40:
            self.exit_camera_mode()
            return

        # 2. Nút CHỤP ẢNH (Vùng 270->310, 100->140)
        if 260 < x < 320 and 90 < y < 150:
            self.take_photo()
            return

        # 3. Nút QUAY VIDEO (Vùng 270->310, 160->200)
        if 260 < x < 320 and 150 < y < 210:
            self.toggle_video_recording()
            return
    # --- XỬ LÝ SỰ KIỆN CẢM ỨNG ---
    def handle_touch(self, x, y):
    
        now = time.time()
        if now - self.last_touch < 0.3: return
        self.last_touch = now

        # --- MENU CHÍNH ---
        if self.state == "MENU":
            start_y = 55
            btn_w, btn_h = 140, 50
            gap = 5
            cols = 2
            start_x = (WIDTH - (btn_w * cols + gap * (cols - 1))) / 2
            
            col, row = -1, -1
            if start_y <= y <= start_y + btn_h * 3 + gap * 2:
                if start_x <= x <= start_x + btn_w: col = 0
                elif start_x + btn_w + gap <= x <= start_x + 2*btn_w + gap: col = 1
                
                if start_y <= y <= start_y + btn_h: row = 0
                elif start_y + btn_h + gap <= y <= start_y + 2*btn_h + gap: row = 1
                elif start_y + 2*(btn_h + gap) <= y <= start_y + 3*btn_h + 2*gap: row = 2
            
            if row != -1 and col != -1:
                page_idx = row * cols + col
                global_idx = self.menu_page * 6 + page_idx
                if global_idx < len(items):
                    if global_idx == 0: 
                        self.state = "MUSIC"
                        self.load_files("MUSIC", ('.mp3', '.wav'))
                    elif global_idx == 1: 
                        self.state = "VIDEO"
                        self.load_files("VIDEO", ('.mp4', '.avi'))
                    elif global_idx == 2: 
                        self.state = "PHOTO"
                        self.load_files("PHOTO", ('.jpg', '.png', '.jpeg'))
                    elif global_idx == 3: 
                        self.state = "BOOK"
                        self.load_files("BOOK", ('.txt',))
                    elif global_idx == 4: 
                        self.state = "GAMES"
                        self.load_files("GAMES", ('.gb', '.gbc'))
                    elif global_idx == 5: 
                        self.state = "CHAT"
                        self.reset_chat_state()
                    elif global_idx == 6: 
                        self.state = "WEB_INPUT"
                        self.reset_web_input_state()
                    elif global_idx == 7: 
                        self.state = "EMAIL"
                        self.reset_email_state()
                    elif global_idx == 8:  # Giả sử "Camera" là vị trí thứ 8 (đếm từ 0)
                        self.state = "CAMERA"
                        self.enter_camera_mode()
                        return
                    elif global_idx == 9: 
                        self.state = "SETTINGS"
                        self.files = self.settings_items
                        self.selected_idx = 0
                        self.scroll_offset = 0
                    self.render()
                    return

            # Xử lý nút chuyển trang
            btn_y = HEIGHT - 35
            if y > btn_y:
                if x < 80 and self.menu_page > 0:
                    self.menu_page -= 1
                elif x > WIDTH - 80 and self.menu_page < 1:  # 2 trang (0 và 1)
                    self.menu_page += 1
                self.render()

        # --- DANH SÁCH FILE (Bao gồm GAMES) ---
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT", "SETTINGS", "GAMES"]:
            # Nút BACK
            if x > WIDTH - 70 and y < 50:
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
                    
                    elif self.state == "SETTINGS":
                        if item == "Kết Nối WiFi":
                            if self.do_connect_wifi():
                                img = Image.new("RGB", (WIDTH, HEIGHT), "black")
                                d = ImageDraw.Draw(img)
                                d.text((80, 100), "Kết nối WiFi thành công!", fill="lime", font=font_md)
                                device.display(img)
                                time.sleep(2)
                            else:
                                img = Image.new("RGB", (WIDTH, HEIGHT), "black")
                                d = ImageDraw.Draw(img)
                                d.text((80, 100), "Kết nối WiFi thất bại!", fill="red", font=font_md)
                                device.display(img)
                                time.sleep(2)
                            self.render()
                        elif item == "Bluetooth":
                            threading.Thread(target=self.scan_bt).start()
                            return
                    
                    elif self.state == "GAMES":
                        threading.Thread(target=self.run_game, daemon=True).start()
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
            # Nút Thoát (sửa để phân biệt web hay sách)
            if x > WIDTH - 60 and y < 30:  # Điều chỉnh vùng chạm
                if self.is_web_reading:
                    self.state = "MENU"
                else:
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

        # --- CHAT UI (Xử lý chạm bàn phím ảo) ---
        elif self.state == "CHAT":
            # Nút BACK (Góc phải trên)
            if x > WIDTH - 60 and y < 30:
                self.state = "MENU"
                self.render()
                return

            # Xử lý cuộn chat (nếu chạm phần trên)
            if y < 120:
                if x < WIDTH / 2:
                    if self.chat_scroll_offset > 0:
                        self.chat_scroll_offset -= 1
                else:
                    self.chat_scroll_offset += 1
                self.render()
                return

            # Xử lý bàn phím QWERTY ảo (thay thế multi-tap)
            kb_y_start = 115
            key_h = 28
            gap = 2
            
            if y < kb_y_start: return
            
            row_idx = (y - kb_y_start) // (key_h + gap)
            if row_idx < 0 or row_idx > 3: return
            
            curr_layout = self.layout_abc if self.kb_mode == "abc" else self.layout_123
            row = curr_layout[int(row_idx)]
            
            # Tính lại start_x giống như lúc vẽ để xác định phím bấm
            n_keys = len(row)
            base_w = (WIDTH - (11 * gap)) // 10
            row_width = sum([self.get_key_width(k, base_w) for k in row]) + (n_keys-1)*gap
            curr_x = (WIDTH - row_width) // 2
            
            for key in row:
                w = self.get_key_width(key, base_w)
                if curr_x <= x <= curr_x + w:
                    # XỬ LÝ LOGIC PHÍM
                    if key == "Shift":
                        self.is_shift = not self.is_shift
                    elif key == "123":
                        self.kb_mode = "123"
                    elif key == "abc":
                        self.kb_mode = "abc"
                    elif key == "Del":
                        self.current_message_text = self.current_message_text[:-1]
                    elif key == "Space":
                        self.current_message_text += " "
                    elif key == "*":
                        self.apply_tone_mark_on_last_word()  # Cycle dấu cho từ cuối
                    elif key == "Send":
                        if self.current_message_text:
                            if self.current_message_text.strip():
                                user_msg = self.current_message_text
                                self.messages_history.append(f"Bạn: {user_msg}")
                                self.current_message_text = ""
                                self.render() # Vẽ ngay để hiện tin nhắn của bạn lên
                
                                # TẠO LUỒNG RIÊNG ĐỂ GỌI API
                                chat_thread = threading.Thread(target=self.process_chat_response, args=(user_msg,))
                                chat_thread.daemon = True
                                chat_thread.start()
                    else:
                        char = key
                        if self.is_shift and self.kb_mode == "abc" and len(key) == 1:
                            char = key.upper()
                        self.current_message_text += char
                        if self.is_shift: self.is_shift = False  # Tự nhả shift
                    self.render()
                    break
                curr_x += w + gap

        # --- EMAIL UI (Xử lý chạm bàn phím ảo) ---
        elif self.state == "EMAIL":
            # Nút BACK (Góc phải trên)
            if x > WIDTH - 60 and y < 30:
                self.state = "MENU"
                self.render()
                return

            # Xử lý thay đổi người nhận (ví dụ chạm vào vùng người nhận)
            if y < 50:
                current_email_index = (current_email_index + 1) % len(recipient_email)
                self.render()
                return

            # Xử lý cuộn (nếu cần, nhưng email chỉ có text input)
            if y < 120 and y > 50:
                # Có thể thêm scroll nếu text dài
                pass

            # Xử lý bàn phím
            kb_y_start = 115
            key_h = 28
            gap = 2
            
            if y < kb_y_start: return
            
            row_idx = (y - kb_y_start) // (key_h + gap)
            if row_idx < 0 or row_idx > 3: return
            
            curr_layout = self.layout_abc if self.kb_mode == "abc" else self.layout_123
            row = curr_layout[int(row_idx)]
            
            n_keys = len(row)
            base_w = (WIDTH - (11 * gap)) // 10
            row_width = sum([self.get_key_width(k, base_w) for k in row]) + (n_keys-1)*gap
            curr_x = (WIDTH - row_width) // 2
            
            for key in row:
                w = self.get_key_width(key, base_w)
                if curr_x <= x <= curr_x + w:
                    if key == "Shift":
                        self.is_shift = not self.is_shift
                    elif key == "123":
                        self.kb_mode = "123"
                    elif key == "abc":
                        self.kb_mode = "abc"
                    elif key == "Del":
                        self.current_message_text = self.current_message_text[:-1]
                    elif key == "Space":
                        self.current_message_text += " "
                    elif key == "*":
                        self.apply_tone_mark_on_last_word()
                    elif key == "Send":
                        if self.current_message_text:
                            if self.send_email(self.current_message_text):
                                img = Image.new("RGB", (WIDTH, HEIGHT), "black")
                                d = ImageDraw.Draw(img)
                                d.text((80, 100), "Gửi thư thành công!", fill="lime", font=font_md)
                                device.display(img)
                                time.sleep(2)
                            else:
                                img = Image.new("RGB", (WIDTH, HEIGHT), "black")
                                d = ImageDraw.Draw(img)
                                d.text((80, 100), "Gửi thư thất bại!", fill="red", font=font_md)
                                device.display(img)
                                time.sleep(2)
                            self.current_message_text = ""
                            self.state = "MENU"
                    else:
                        char = key
                        if self.is_shift and self.kb_mode == "abc" and len(key) == 1:
                            char = key.upper()
                        self.current_message_text += char
                        if self.is_shift: self.is_shift = False
                    self.render()
                    break
                curr_x += w + gap

        # --- WEB INPUT UI (Xử lý nhập câu hỏi cho Wikipedia) ---
        elif self.state == "WEB_INPUT":
            # Nút BACK (Góc phải trên)
            if x > WIDTH - 60 and y < 30:
                self.state = "MENU"
                self.render()
                return

            # Xử lý cuộn (nếu cần, nhưng input chỉ có text)
            if y < 120 and y > 50:
                pass

            # Xử lý bàn phím
            kb_y_start = 115
            key_h = 28
            gap = 2
            
            if y < kb_y_start: return
            
            row_idx = (y - kb_y_start) // (key_h + gap)
            if row_idx < 0 or row_idx > 3: return
            
            curr_layout = self.layout_abc if self.kb_mode == "abc" else self.layout_123
            row = curr_layout[int(row_idx)]
            
            n_keys = len(row)
            base_w = (WIDTH - (11 * gap)) // 10
            row_width = sum([self.get_key_width(k, base_w) for k in row]) + (n_keys-1)*gap
            curr_x = (WIDTH - row_width) // 2
            
            for key in row:
                w = self.get_key_width(key, base_w)
                if curr_x <= x <= curr_x + w:
                    if key == "Shift":
                        self.is_shift = not self.is_shift
                    elif key == "123":
                        self.kb_mode = "123"
                    elif key == "abc":
                        self.kb_mode = "abc"
                    elif key == "Del":
                        self.current_message_text = self.current_message_text[:-1]
                    elif key == "Space":
                        self.current_message_text += " "
                    elif key == "*":
                        self.apply_tone_mark_on_last_word()
                    elif key == "Send":
                        if self.current_message_text:
                            query = self.current_message_text.strip()
                            if query:
                                # Hiển thị thông báo đang tải
                                img = Image.new("RGB", (WIDTH, HEIGHT), "black")
                                d = ImageDraw.Draw(img)
                                d.text((80, 100), "Đang tải từ Wikipedia...", fill="lime", font=font_md)
                                device.display(img)
                                
                                # Xử lý query trong thread riêng để tránh treo
                                wiki_thread = threading.Thread(target=self.process_wikipedia_query, args=(query,))
                                wiki_thread.daemon = True
                                wiki_thread.start()
                                
                                self.current_message_text = ""
                    else:
                        char = key
                        if self.is_shift and self.kb_mode == "abc" and len(key) == 1:
                            char = key.upper()
                        self.current_message_text += char
                        if self.is_shift: self.is_shift = False
                    self.render()
                    break
                curr_x += w + gap

        elif self.state == "CAMERA":
            self.handle_touch_camera(x, y) # Gọi hàm chuyên biệt mới viết ở trên
            return

    def run(self):
        self.render()
        while self.running:
            # Liên tục cập nhật UI khi nghe nhạc để quay đĩa/chạy thanh progress
            if self.state == "PLAYING_MUSIC" and not self.is_paused:
                self.render()
            
            # Kiểm tra flag cập nhật chat từ thread
            if self.state == "CHAT" and self.chat_needs_update:
                self.chat_needs_update = False
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
    app = PiMediaCenter()
    app.run()