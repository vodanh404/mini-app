import os,sys,time,subprocess,threading,signal,datetime,textwrap,math,pygame,board,busio
from PIL import Image, ImageFont, ImageDraw, ImageOps
from luma.core.interface.serial import spi as luma_spi
from luma.lcd.device import st7789
from xpt2046 import XPT2046

# ==========================================
# 1. CẤU HÌNH HỆ THỐNG & PHẦN CỨNG
# ==========================================

# Cấu hình Màn hình
WIDTH, HEIGHT = 320, 240
APPS_PER_PAGE = 6
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
    "BOOK":  os.path.join(USER_HOME, "Documents")
}
for d in DIRS.values(): os.makedirs(d, exist_ok=True)

# Khởi tạo Fonts
def load_font(size):
    try: return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except: return ImageFont.load_default()

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
# 1. app đa phương tiện
class DA_PHUONG_TIEN:
    def __init__(self):
        self.state = "MENU" 
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
            ("Photo", "☘", "#a6e3a1"), ("Books", "☕", "#89b4fa"), # Đổi icon book
            ("BlueTooth", "⚙", "#cba6f7")  # Thay icon Bluetooth bằng anten để hỗ trợ tốt hơn
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
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT"]:
            title_map = {"MUSIC": "Thư viện Nhạc", "VIDEO": "Thư viện Video", "PHOTO": "Thư viện Ảnh", "BOOK": "Kệ Sách", "BT": "Thiết bị Bluetooth"}
            self.draw_list(draw, title_map.get(self.state, ""))
        elif self.state == "PLAYING_MUSIC":
            self.draw_player_ui(draw)
        elif self.state == "READING":
            self.draw_reader(draw)
        elif self.state == "VIEWING_PHOTO":
            pass 

        if self.state != "PLAYING_VIDEO" and self.state != "VIEWING_PHOTO":
            device.display(image)

    def load_files(self, type_key, ext):
        self.files = sorted([f for f in os.listdir(DIRS[type_key]) if f.lower().endswith(ext)])
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
            img = ImageOps.invert(img) # Bỏ comment nếu màu bị đảo ngược
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
                    threading.Thread(target=self.scan_bt).start()
                    return
                self.render()

        # --- DANH SÁCH FILE ---
        elif self.state in ["MUSIC", "VIDEO", "PHOTO", "BOOK", "BT"]:
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

# 2. game
class GAMES:
    # hàm gọi các game
    def __init__(self):
        self.state = "MENU"
        self.running = True
        self.block_blast = BlockBlastEngine(device, touch)
        self.flappybird = FlappyBird()
        self.snakegame = SnakeGame()
#===========================================
class BlockBlastEngine:
    """Class xử lý logic game, chạy độc lập khi được gọi"""
    GRID_SIZE = 8
    CELL_SIZE = 26  # Điều chỉnh cho vừa màn hình 240 dọc (Game xoay ngang hoặc dọc tùy thiết kế)
    # Ở đây ta giữ màn hình ngang 320x240.
    # Grid sẽ nằm bên trái (208x208), Panel điều khiển bên phải.
    
    SHAPES = [
        [[1]], [[1, 1]], [[1], [1]], [[1, 1], [1, 1]],
        [[1, 1, 1]], [[1], [1], [1]], [[1, 0], [1, 0], [1, 1]], [[0, 1, 0], [1, 1, 1]]
    ]
    COLORS = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF"]

    def __init__(self, display_device, touch_driver):
        self.device = display_device
        self.touch = touch_driver
        self.grid = [[0]*8 for _ in range(8)]
        self.score = 0
        self.running = False
        self.game_over = False
        
        self.available_shapes = []
        self.selected_shape_idx = None
        self.refill_shapes()

    def refill_shapes(self):
        self.available_shapes = []
        for _ in range(3):
            shape = random.choice(self.SHAPES)
            color = random.choice(self.COLORS)
            self.available_shapes.append({'shape': shape, 'color': color, 'active': True})
        self.selected_shape_idx = None

    def check_collision(self, start_x, start_y, shape):
        rows = len(shape)
        cols = len(shape[0])
        if start_x + cols > 8 or start_y + rows > 8: return False
        for r in range(rows):
            for c in range(cols):
                if shape[r][c] == 1 and self.grid[start_y + r][start_x + c] != 0:
                    return False
        return True

    def place_shape(self, start_x, start_y, shape_obj):
        shape = shape_obj['shape']
        color = shape_obj['color']
        rows = len(shape)
        cols = len(shape[0])
        for r in range(rows):
            for c in range(cols):
                if shape[r][c] == 1:
                    self.grid[start_y + r][start_x + c] = color
        
        shape_obj['active'] = False
        self.selected_shape_idx = None
        self.check_lines()
        
        if all(not s['active'] for s in self.available_shapes):
            self.refill_shapes()
            
        if not self.can_place_any():
            self.game_over = True

    def check_lines(self):
        lines = 0
        rows_to_clear = [r for r in range(8) if all(self.grid[r])]
        cols_to_clear = [c for c in range(8) if all(self.grid[r][c] for r in range(8))]
        
        for r in rows_to_clear:
            for c in range(8): self.grid[r][c] = 0
        for c in cols_to_clear:
            for r in range(8): self.grid[r][c] = 0
            
        if rows_to_clear or cols_to_clear:
            self.score += (len(rows_to_clear) + len(cols_to_clear)) * 10

    def can_place_any(self):
        for s in self.available_shapes:
            if not s['active']: continue
            for y in range(8):
                for x in range(8):
                    if self.check_collision(x, y, s['shape']): return True
        return False

    def render(self):
        img = Image.new("RGB", (WIDTH, HEIGHT), "#202020")
        draw = ImageDraw.Draw(img)
        
        # 1. Vẽ Grid (Bên trái)
        offset_x, offset_y = 10, 16
        cell_size = 26
        
        # Vẽ khung grid
        draw.rectangle((offset_x-2, offset_y-2, offset_x + 8*cell_size + 1, offset_y + 8*cell_size + 1), outline="white")
        
        for r in range(8):
            for c in range(8):
                x = offset_x + c * cell_size
                y = offset_y + r * cell_size
                col = self.grid[r][c]
                if col == 0:
                    draw.rectangle((x, y, x+cell_size-1, y+cell_size-1), outline="#404040")
                else:
                    draw.rectangle((x, y, x+cell_size-1, y+cell_size-1), fill=col)

        # 2. UI Bên phải (Score, Shapes, Exit)
        right_panel_x = 230
        draw.text((right_panel_x, 10), "ĐIỂM SỐ", fill="white", font=font_sm)
        draw.text((right_panel_x, 25), str(self.score), fill="yellow", font=font_lg)
        
        # Nút thoát
        draw.rounded_rectangle((right_panel_x, HEIGHT - 40, right_panel_x + 80, HEIGHT - 10), radius=5, fill="#cc3333")
        draw.text((right_panel_x + 20, HEIGHT - 35), "THOÁT", fill="white", font=font_md)

        # 3. Vẽ Shape (3 ô dọc bên phải)
        spawn_y = 60
        for idx, item in enumerate(self.available_shapes):
            if not item['active']: continue
            shape = item['shape']
            color = item['color']
            is_sel = (idx == self.selected_shape_idx)
            
            base_y = spawn_y + idx * 50
            outline = "white" if is_sel else None
            
            # Vẽ mini preview
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]:
                        sx = right_panel_x + c * 8
                        sy = base_y + r * 8
                        draw.rectangle((sx, sy, sx+7, sy+7), fill=color, outline=outline)

        if self.game_over:
            draw.rectangle((50, 80, 200, 160), fill="black", outline="red")
            draw.text((80, 100), "GAME OVER", fill="red", font=font_lg)
            draw.text((70, 130), "Chạm để reset", fill="white", font=font_sm)

        self.device.display(img)

    def run(self):
        """Vòng lặp chính của game"""
        self.running = True
        self.game_over = False
        self.grid = [[0]*8 for _ in range(8)]
        self.score = 0
        self.refill_shapes()
        
        while self.running:
            self.render()
            
            # Logic cảm ứng
            t = self.touch.get_touch()
            if t:
                tx, ty = t
                # Xử lý thoát
                if tx > 230 and ty > HEIGHT - 40:
                    self.running = False
                    return

                if self.game_over:
                    self.game_over = False
                    self.grid = [[0]*8 for _ in range(8)]
                    self.score = 0
                    self.refill_shapes()
                    time.sleep(0.5)
                    continue

                # Xử lý chọn Shape (Bên phải)
                if tx > 230 and ty < HEIGHT - 50:
                    slot = (ty - 60) // 50
                    if 0 <= slot < 3 and self.available_shapes[slot]['active']:
                        self.selected_shape_idx = slot

                # Xử lý đặt vào Grid (Bên trái)
                elif tx < 10 + 8*26 and ty < 16 + 8*26:
                    if self.selected_shape_idx is not None:
                        g_x = int((tx - 10) // 26)
                        g_y = int((ty - 16) // 26)
                        shape_obj = self.available_shapes[self.selected_shape_idx]
                        if self.check_collision(g_x, g_y, shape_obj['shape']):
                            self.place_shape(g_x, g_y, shape_obj)

            time.sleep(0.05)
# ==========================================
class FlappyBird:
    def __init__(self):
        self.bird_y = 120
        self.vel = 0
        self.pipes = [[320, random.randint(50, 150)]]
        self.score = 0

    def update(self, t):
        if t: self.vel = -5
        self.vel += 0.6
        self.bird_y += int(self.vel)
        for p in self.pipes: p[0] -= 6
        if self.pipes[0][0] < -40:
            self.pipes.pop(0)
            self.pipes.append([320, random.randint(50, 150)])
            self.score += 1
        return 0 < self.bird_y < 240

    def draw(self, draw):
        draw.ellipse([50, self.bird_y, 70, self.bird_y+20], fill=(255, 255, 0))
        for p in self.pipes:
            draw.rectangle([p[0], 0, p[0]+40, p[1]], fill=(0, 200, 0))
            draw.rectangle([p[0], p[1]+80, p[0]+40, 240], fill=(0, 200, 0))
        draw.text((5, 5), f"Score: {self.score}", fill=(255, 255, 255))
# ==========================================
class SnakeGame:
    def __init__(self):
        self.snake = [[100, 100], [90, 100], [80, 100]]
        self.dir = [10, 0]
        self.food = [random.randrange(0, 300, 10), random.randrange(0, 220, 10)]
        self.score = 0

    def update(self, t):
        if t:
            tx, ty = t
            if ty < 60: self.dir = [0, -10]
            elif ty > 180: self.dir = [0, 10]
            elif tx < 100: self.dir = [-10, 0]
            elif tx > 220: self.dir = [10, 0]
        
        new_head = [self.snake[0][0] + self.dir[0], self.snake[0][1] + self.dir[1]]
        if new_head in self.snake or not (0 <= new_head[0] < 320 and 0 <= new_head[1] < 240):
            return False
        
        self.snake.insert(0, new_head)
        if abs(new_head[0]-self.food[0]) < 10 and abs(new_head[1]-self.food[1]) < 10:
            self.food = [random.randrange(0, 300, 10), random.randrange(0, 220, 10)]
            self.score += 1
        else: self.snake.pop()
        return True

    def draw(self, draw):
        for s in self.snake: draw.rectangle([s[0], s[1], s[0]+8, s[1]+8], fill=(0, 255, 0))
        draw.rectangle([self.food[0], self.food[1], self.food[0]+8, self.food[1]+8], fill=(255, 0, 0))
#==========================================
class DinoRun:
    def __init__(self):
        self.dino_y = 180
        self.vel_y = 0
        self.cacti = [320]
        self.score = 0

    def update(self, t):
        if t and self.dino_y >= 180: self.vel_y = -12
        self.dino_y += self.vel_y
        self.vel_y += 1
        if self.dino_y > 180: self.dino_y, self.vel_y = 180, 0
        self.cacti = [c - 8 for c in self.cacti if c > -20]
        if not self.cacti or self.cacti[-1] < 150: self.cacti.append(320 + random.randint(0, 100))
        for c in self.cacti:
            if 40 < c < 70 and self.dino_y > 150: return False
        self.score += 1
        return True

    def draw(self, draw):
        draw.rectangle([0, 200, 320, 240], fill=(100, 100, 100)) # Đất
        draw.rectangle([50, self.dino_y, 70, self.dino_y+20], fill=(0, 255, 0)) # Dino
        for c in self.cacti: draw.rectangle([c, 170, c+15, 200], fill=(255, 0, 0)) # Xương rồng
#==========================================
class Snake:
    def __init__(self):
        self.snake = [[100, 100], [90, 100], [80, 100]]
        self.dir = [10, 0]
        self.food = [random.randrange(0, 300, 10), random.randrange(0, 220, 10)]

    def update(self, t):
        if t:
            if t[1] < 60: self.dir = [0, -10]
            elif t[1] > 180: self.dir = [0, 10]
            elif t[0] < 100: self.dir = [-10, 0]
            elif t[0] > 220: self.dir = [10, 0]
        head = [self.snake[0][0] + self.dir[0], self.snake[0][1] + self.dir[1]]
        if head in self.snake or not (0 <= head[0] < 320 and 0 <= head[1] < 240): return False
        self.snake.insert(0, head)
        if abs(head[0]-self.food[0]) < 10 and abs(head[1]-self.food[1]) < 10:
            self.food = [random.randrange(0, 300, 10), random.randrange(0, 220, 10)]
        else: self.snake.pop()
        return True

    def draw(self, draw):
        for s in self.snake: draw.rectangle([s[0], s[1], s[0]+9, s[1]+9], fill=(0, 255, 0))
        draw.rectangle([self.food[0], self.food[1], self.food[0]+9, self.food[1]+9], fill=(255, 0, 0))
#==========================================

# ==========================================
# 3. SMART OS
class SmartOS:
    def __init__(self):
        self.state = "MENU"
        self.page = 0
        self.running = True
        self.weather_info = "Đang tải..."
        
        # Danh sách 12 ứng dụng (Theo yêu cầu)
        self.apps = [
            {"name": "Đa phương tiện", "icon": "🎞️", "color": "#f9e2af", "cmd": self.go_media},
            {"name": "Trò chơi", "icon": "🎮", "color": "#a6e3a1", "cmd": self.go_game},
            {"name": "Thời tiết", "icon": "⛅", "color": "#89dceb", "cmd": self.go_weather},
            {"name": "Hệ thống", "icon": "🖥️", "color": "#89b4fa", "cmd": self.go_sys},
            {"name": "Dịch thuật", "icon": "🗣️", "color": "#cba6f7", "cmd": self.go_trans},
            {"name": "Wikipedia", "icon": "🌐", "color": "#fab387", "cmd": self.go_wiki},
            {"name": "Đồng hồ", "icon": "⏰", "color": "#f38ba8", "cmd": self.not_impl},
            {"name": "Ghi chú", "icon": "📝", "color": "#94e2d5", "cmd": self.not_impl},
            {"name": "Lịch", "icon": "📅", "color": "#eba0ac", "cmd": self.not_impl},
            {"name": "WiFi", "icon": "📡", "color": "#f5c2e7", "cmd": self.not_impl},
            {"name": "Cài đặt", "icon": "⚙️", "color": "#a6adc8", "cmd": self.not_impl},
            {"name": "Tắt máy", "icon": "🔌", "color": "#313244", "cmd": sys.exit}
        ]
        
        pygame.mixer.init()
    # --- Điều hướng Apps ---
    def go_media(self): self.state = "MEDIA_SELECT"
    def go_game(self): self.game = MiniGame(); self.state = "GAME"
    def go_sys(self): self.state = "SYS_INFO"
    def go_weather(self): 
        self.state = "WEATHER"
        threading.Thread(target=self.fetch_weather, daemon=True).start()
    def go_trans(self): self.state = "TRANS"
    def go_wiki(self): self.state = "WIKI"
    def not_impl(self): pass

    # --- Vẽ giao diện ---
    def draw_status_bar(self, draw):
        now = datetime.datetime.now().strftime("%H:%M")
        draw.rectangle((0, 0, WIDTH, 22), fill="#11111b")
        draw.text((WIDTH-45, 3), now, fill="white", font=font_sm)
        draw.text((10, 3), "OS v2.0", fill=ACCENT_COLOR, font=font_sm)

    def draw_menu(self):
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        self.draw_status_bar(draw)

        start = self.page * APPS_PER_PAGE
        page_apps = self.apps[start : start + APPS_PER_PAGE]

        for i, app in enumerate(page_apps):
            ix = (i % 3) * 102 + 10
            iy = (i // 3) * 95 + 32
            draw.rounded_rectangle((ix, iy, ix+95, iy+85), radius=12, fill=CARD_COLOR, outline=app['color'], width=1)
            draw.text((ix+30, iy+15), app['icon'], fill="white", font=font_icon)
            # Tự động xuống dòng tên app nếu dài
            name_label = "\n".join(textwrap.wrap(app['name'], width=12))
            draw.text((ix+10, iy+52), name_label, fill=TEXT_COLOR, font=font_sm)

        # Footer Nav
        if self.page > 0: draw.text((10, 218), "<< TRƯỚC", fill=ACCENT_COLOR, font=font_sm)
        if (self.page+1)*APPS_PER_PAGE < len(self.apps): draw.text((WIDTH-70, 218), "SAU >>", fill=ACCENT_COLOR, font=font_sm)
        
        device.display(img)

    def draw_sys_info(self):
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        self.draw_status_bar(draw)
        
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        temp = 0 # Cần thư viện hỗ trợ nhiệt độ Raspberry Pi cụ thể
        
        draw.text((20, 35), "THÔNG TIN HỆ THỐNG", fill=ACCENT_COLOR, font=font_md)
        draw.text((20, 70), f"CPU Usage: {cpu}%", fill="white", font=font_sm)
        draw.rectangle((20, 85, 20 + cpu*2.5, 95), fill=WARN_COLOR)
        
        draw.text((20, 110), f"RAM Usage: {ram}%", fill="white", font=font_sm)
        draw.rectangle((20, 125, 20 + ram*2.5, 135), fill=SUCCESS_COLOR)

        draw.rounded_rectangle((WIDTH-60, 205, WIDTH-10, 230), radius=5, fill=WARN_COLOR)
        draw.text((WIDTH-50, 210), "BACK", fill="black", font=font_sm)
        device.display(img)

    def fetch_weather(self):
        try:
            r = requests.get("http://api.openweathermap.org/data/2.5/weather?appid=383c5c635c88590b37c698bc100f6377&q=Hanoi,VN&units=metric&lang=vi")
            data = r.json()
            self.weather_info = f"{data['name']}\n{data['main']['temp']}°C\n{data['weather'][0]['description']}"
        except: self.weather_info = "Lỗi kết nối mạng!"

    # --- Xử lý cảm ứng ---
    def handle_touch(self, x, y):
        if self.state == "MENU":
            if y > 210:
                if x < 100 and self.page > 0: self.page -= 1
                elif x > 220 and (self.page+1)*APPS_PER_PAGE < len(self.apps): self.page += 1
            else:
                col, row = x // 105, (y-30) // 95
                idx = self.page * APPS_PER_PAGE + (row * 3 + col)
                if idx < len(self.apps): self.apps[idx]['cmd']()
        
        elif self.state in ["SYS_INFO", "WEATHER", "GAME", "MEDIA_SELECT"]:
            if x > 250 and y > 200: self.state = "MENU"

    def run(self):
        while self.running:
            if self.state == "MENU": self.draw_menu()
            elif self.state == "SYS_INFO": self.draw_sys_info()
            # Xử lý các state khác...
            
            p = touch.get_touch()
            if p: self.handle_touch(p[0], p[1])
            time.sleep(0.1)


# Khởi động Smart OS
if __name__ == "__main__":
