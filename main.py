import os, sys, time, subprocess, threading, signal, datetime, textwrap, math, pygame, board, busio, random
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
GAME_BG = "#181825"        # Nền game

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
        self.menu_page = 0  # Thêm cho menu tổng đa trang
        
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
        
        # Photo
        self.current_image = None
        
        # Games
        self.games = ["Snake", "Tic-Tac-Toe"]
        self.game_state = None  # "SNAKE" or "TIC_TAC_TOE"
        self.snake = []
        self.snake_dir = (1, 0)
        self.food = (0, 0)
        self.score = 0
        self.game_over = False
        self.ttt_board = [[' ' for _ in range(3)] for _ in range(3)]
        self.ttt_player = 'X'
        self.ttt_winner = None
        
        # Previous state for back navigation
        self.prev_state = None

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
        """Vẽ Menu chính - Hỗ trợ đa trang"""
        self.draw_status_bar(draw)
        title = "PI MINI APP"
        bbox = draw.textbbox((0,0), title, font=font_lg)
        draw.text(((WIDTH - (bbox[2]-bbox[0]))/2, 35), title, fill=ACCENT_COLOR, font=font_lg)

        all_items = [
            ("Music", "♫", "#f9e2af"), ("Video", "►", "#f38ba8"),
            ("Photo", "☘", "#a6e3a1"), ("Books", "☕", "#89b4fa"),
            ("Games", "🎮", "#fab387"), ("BlueTooth", "⚙", "#cba6f7")
        ]
        
        start_idx = self.menu_page * APPS_PER_PAGE
        items = all_items[start_idx : start_idx + APPS_PER_PAGE]
        
        start_y = 70
        btn_w, btn_h = 90, 70
        gap = 20
        cols = 3
        rows = math.ceil(len(items) / cols)
        start_x = (WIDTH - (btn_w * cols + gap * (cols - 1))) / 2

        for i, (label, icon, color) in enumerate(items):
            row = i // cols
            col = i % cols
            x = start_x + col * (btn_w + gap)
            y = start_y + row * (btn_h + gap)
            
            draw.rounded_rectangle((x, y, x+btn_w, y+btn_h), radius=10, fill="#313244", outline=color, width=2)
            draw.text((x + 35, y + 10), icon, fill=color, font=font_icon)
            draw.text((x + (btn_w - font_sm.getlength(label))/2, y + 45), label, fill="white", font=font_sm)
        
        # Nút chuyển trang nếu cần
        total_pages = math.ceil(len(all_items) / APPS_PER_PAGE)
        if total_pages > 1:
            btn_y = HEIGHT - 35
            if self.menu_page > 0:
                self.draw_button(draw, 10, btn_y, 50, 25, "◄", bg_color="#313244")
            draw.text((WIDTH/2 - 20, btn_y + 5), f"{self.menu_page + 1}/{total_pages}", fill="white", font=font_sm)
            if self.menu_page < total_pages - 1:
                self.draw_button(draw, WIDTH - 60, btn_y, 50, 25, "►", bg_color="#313244")

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
        draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill="#313244")
        
        # Giả lập tiến trình (dựa trên thời gian chạy, giả sử mỗi bài 3 phút)
        fake_duration = 180  # giây
        elapsed = time.time() - self.music_start_time if not self.is_paused else self.music_paused_time
        progress = min(1.0, elapsed / fake_duration)
        fill_w = bar_w * progress
        draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), fill=ACCENT_COLOR)
        
        # Thời gian giả lập
        elapsed_str = f"{int(elapsed // 60):02}:{int(elapsed % 60):02}"
        duration_str = "03:00"  # Giả
        draw.text((bar_x, bar_y + 10), elapsed_str, fill="white", font=font_sm)
        draw.text((bar_x + bar_w - 40, bar_y + 10), duration_str, fill="white", font=font_sm)

        # 4. Nút điều khiển
        btn_y = 180
        self.draw_button(draw, 20, btn_y, 50, 40, "◄", bg_color="#313244", icon_font=font_icon)  # Prev
        self.draw_button(draw, 85, btn_y, 50, 40, "▶" if self.is_paused else "⏸", bg_color="#313244", icon_font=font_icon)  # Play/Pause
        self.draw_button(draw, 150, btn_y, 50, 40, "►", bg_color="#313244", icon_font=font_icon)  # Next
        self.draw_button(draw, 215, btn_y, 50, 40, "+", bg_color="#313244", icon_font=font_icon)  # Vol up
        self.draw_button(draw, 270, btn_y, 50, 40, "-", bg_color="#313244", icon_font=font_icon)  # Vol down
        
        # Back button
        self.draw_button(draw, WIDTH - 70, 26, 60, 22, "BACK", bg_color=WARN_COLOR, text_color="black")

    def draw_book_reader(self, draw):
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=READER_BG)
        self.draw_status_bar(draw)
        
        # Số trang
        page_str = f"Page {self.book_current_page + 1}/{self.book_total_pages}"
        bbox = draw.textbbox((0, 0), page_str, font=font_sm)
        draw.text(((WIDTH - (bbox[2] - bbox[0])) / 2, 28), page_str, fill=TEXT_COLOR, font=font_sm)
        
        # Nội dung văn bản
        start_line = self.book_current_page * self.book_page_lines
        lines = self.book_lines[start_line : start_line + self.book_page_lines]
        for i, line in enumerate(lines):
            draw.text((10, 50 + i * 18), line, fill=READER_TEXT, font=font_md)
        
        # Nút điều hướng
        btn_y = HEIGHT - 40
        self.draw_button(draw, 10, btn_y, 90, 30, "◄ Prev", bg_color="#313244")
        self.draw_button(draw, WIDTH / 2 - 45, btn_y, 90, 30, "Back", bg_color=WARN_COLOR)
        self.draw_button(draw, WIDTH - 100, btn_y, 90, 30, "Next ►", bg_color="#313244")

    def draw_photo_viewer(self, image, draw):
        self.draw_status_bar(draw)
        
        if self.current_image:
            resized_img = self.current_image.resize((WIDTH, HEIGHT - 50))
            image.paste(resized_img, (0, 25))
        
        # Nút điều hướng
        btn_y = HEIGHT - 40
        self.draw_button(draw, 10, btn_y, 90, 30, "◄ Prev", bg_color="#313244")
        self.draw_button(draw, WIDTH / 2 - 45, btn_y, 90, 30, "Back", bg_color=WARN_COLOR)
        self.draw_button(draw, WIDTH - 100, btn_y, 90, 30, "Next ►", bg_color="#313244")

    def draw_bluetooth(self, draw):
        title = "Bluetooth Devices"
        self.draw_list(draw, title)  # Sử dụng draw_list chung, files = bt_devices

    def draw_games_list(self, draw):
        title = "Games"
        self.files = self.games
        self.draw_list(draw, title)

    def draw_snake_game(self, draw):
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=GAME_BG)
        self.draw_status_bar(draw)
        
        draw.text((10, 30), f"Score: {self.score}", fill="white", font=font_md)
        
        grid_size = 20
        grid_w, grid_h = WIDTH // grid_size, (HEIGHT - 50) // grid_size
        
        # Vẽ rắn
        for seg in self.snake:
            draw.rectangle((seg[0]*grid_size, seg[1]*grid_size + 50, 
                            (seg[0]+1)*grid_size - 1, (seg[1]+1)*grid_size + 49), fill=SUCCESS_COLOR)
        
        # Vẽ thức ăn
        draw.rectangle((self.food[0]*grid_size, self.food[1]*grid_size + 50, 
                        (self.food[0]+1)*grid_size - 1, (self.food[1]+1)*grid_size + 49), fill=WARN_COLOR)
        
        if self.game_over:
            draw.rectangle((WIDTH/2 - 100, HEIGHT/2 - 30, WIDTH/2 + 100, HEIGHT/2 + 30), fill="#313244")
            draw.text((WIDTH/2 - 50, HEIGHT/2 - 20), "Game Over!", fill="red", font=font_md)
            self.draw_button(draw, WIDTH/2 - 50, HEIGHT/2 + 5, 100, 25, "Restart", bg_color=ACCENT_COLOR)
        
        # Nút back
        self.draw_button(draw, WIDTH - 70, 26, 60, 22, "BACK", bg_color=WARN_COLOR, text_color="black")

    def draw_tic_tac_toe(self, draw):
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=GAME_BG)
        self.draw_status_bar(draw)
        
        draw.text((10, 30), f"Player: {self.ttt_player}", fill="white", font=font_md)
        if self.ttt_winner:
            draw.text((WIDTH/2 - 50, 30), f"Winner: {self.ttt_winner}", fill="green", font=font_md)
        
        cell_size = 80
        start_x, start_y = (WIDTH - 3*cell_size) // 2, 60
        
        # Vẽ lưới
        for i in range(1, 3):
            draw.line((start_x + i*cell_size, start_y, start_x + i*cell_size, start_y + 3*cell_size), fill="white", width=2)
            draw.line((start_x, start_y + i*cell_size, start_x + 3*cell_size, start_y + i*cell_size), fill="white", width=2)
        
        # Vẽ X/O
        for i in range(3):
            for j in range(3):
                x = start_x + j*cell_size + cell_size//2
                y = start_y + i*cell_size + cell_size//2 - 10
                draw.text((x - 10, y), self.ttt_board[i][j], fill="cyan" if self.ttt_board[i][j] == 'X' else "red", font=font_icon_lg)
        
        # Nút back và reset
        btn_y = HEIGHT - 40
        self.draw_button(draw, 10, btn_y, 90, 30, "Reset", bg_color=ACCENT_COLOR)
        self.draw_button(draw, WIDTH - 100, btn_y, 90, 30, "Back", bg_color=WARN_COLOR)

    def draw(self, image, draw):
        if self.state == "MENU":
            self.draw_menu(draw)
        elif self.state.endswith("_LIST") and self.state != "GAMES_LIST":
            title = self.state.replace("_LIST", "").capitalize()
            self.draw_list(draw, title)
        elif self.state == "MUSIC_PLAYER":
            self.draw_player_ui(draw)
        elif self.state == "BOOK_READER":
            self.draw_book_reader(draw)
        elif self.state == "PHOTO_VIEWER":
            self.draw_photo_viewer(image, draw)
        elif self.state == "BLUETOOTH":
            self.draw_bluetooth(draw)
        elif self.state == "GAMES_LIST":
            self.draw_games_list(draw)
        elif self.state == "SNAKE_GAME":
            self.draw_snake_game(draw)
        elif self.state == "TIC_TAC_TOE":
            self.draw_tic_tac_toe(draw)
        # Video không vẽ, để subprocess xử lý

    # --- HÀM TẢI FILE ---
    def load_files(self, media_type):
        dir_path = DIRS.get(media_type.upper())
        if not dir_path:
            return
        extensions = {
            "MUSIC": (".mp3", ".wav"),
            "VIDEO": (".mp4", ".avi", ".mkv"),
            "PHOTO": (".jpg", ".png", ".jpeg"),
            "BOOK": (".txt")
        }.get(media_type.upper(), ())
        self.files = [f for f in os.listdir(dir_path) if f.lower().endswith(extensions)]
        self.files.sort()
        self.selected_idx = 0
        self.scroll_offset = 0
        self.state = f"{media_type.upper()}_LIST"

    def scan_bluetooth(self):
        self.bt_scanning = True
        try:
            subprocess.run(["bluetoothctl", "scan", "on"])
            time.sleep(5)
            output = subprocess.check_output(["bluetoothctl", "devices"])
            self.bt_devices = [line.split(maxsplit=1)[1] for line in output.decode().split('\n') if line.startswith("Device")]
        except:
            self.bt_devices = []
        self.bt_scanning = False
        self.files = self.bt_devices
        self.state = "BLUETOOTH"

    # --- GAME LOGIC ---
    def init_snake(self):
        self.snake = [(5, 5), (4, 5), (3, 5)]
        self.snake_dir = (1, 0)
        self.food = (random.randint(0, 15), random.randint(0, 9))
        self.score = 0
        self.game_over = False

    def update_snake(self):
        if self.game_over:
            return
        
        head = (self.snake[0][0] + self.snake_dir[0], self.snake[0][1] + self.snake_dir[1])
        
        if (head[0] < 0 or head[0] >= 16 or head[1] < 0 or head[1] >= 10 or head in self.snake):
            self.game_over = True
            return
        
        self.snake.insert(0, head)
        
        if head == self.food:
            self.score += 1
            self.food = (random.randint(0, 15), random.randint(0, 9))
        else:
            self.snake.pop()

    def init_tic_tac_toe(self):
        self.ttt_board = [[' ' for _ in range(3)] for _ in range(3)]
        self.ttt_player = 'X'
        self.ttt_winner = None

    def check_ttt_winner(self):
        for row in self.ttt_board:
            if row[0] == row[1] == row[2] != ' ':
                return row[0]
        for col in range(3):
            if self.ttt_board[0][col] == self.ttt_board[1][col] == self.ttt_board[2][col] != ' ':
                return self.ttt_board[0][col]
        if self.ttt_board[0][0] == self.ttt_board[1][1] == self.ttt_board[2][2] != ' ':
            return self.ttt_board[0][0]
        if self.ttt_board[0][2] == self.ttt_board[1][1] == self.ttt_board[2][0] != ' ':
            return self.ttt_board[0][2]
        return None

    def ttt_ai_move(self):
        for i in range(3):
            for j in range(3):
                if self.ttt_board[i][j] == ' ':
                    self.ttt_board[i][j] = 'O'
                    return
        # Có thể thêm AI tốt hơn sau

    # --- HÀM XỬ LÝ CHẠM ---
    def handle_touch(self, x, y):
        if time.time() - self.last_touch < 0.2:
            return
        self.last_touch = time.time()

        if self.state == "VIDEO_PLAYER":
            # Chạm bất kỳ để dừng video
            self.emergency_cleanup()
            self.state = "VIDEO_LIST"
            return

        # Xử lý back chung (nếu có nút back)
        if 26 < y < 48 and WIDTH - 60 < x < WIDTH and self.state not in ["MENU", "GAMES_LIST", "SNAKE_GAME", "TIC_TAC_TOE"]:
            if self.state == "MUSIC_PLAYER":
                pygame.mixer.music.stop()
            self.state = "MENU"
            self.files = []
            return

        if self.state == "MENU":
            start_y = 70
            btn_w, btn_h, gap = 90, 70, 20
            cols = 3
            start_x = (WIDTH - (btn_w * cols + gap * (cols - 1))) / 2
            all_items = ["MUSIC", "VIDEO", "PHOTO", "BOOK", "GAMES", "BLUETOOTH"]
            start_idx = self.menu_page * APPS_PER_PAGE
            items = all_items[start_idx : start_idx + APPS_PER_PAGE]
            for i in range(len(items)):
                row = i // cols
                col = i % cols
                btn_x = start_x + col * (btn_w + gap)
                btn_y = start_y + row * (btn_h + gap)
                if btn_x < x < btn_x + btn_w and btn_y < y < btn_y + btn_h:
                    item = items[i]
                    if item == "BLUETOOTH":
                        self.scan_bluetooth()
                    elif item == "GAMES":
                        self.state = "GAMES_LIST"
                        self.selected_idx = 0
                        self.files = self.games
                    else:
                        self.load_files(item)
                    return
            
            # Chuyển trang menu
            btn_y = HEIGHT - 35
            if btn_y < y < btn_y + 25:
                if 10 < x < 60 and self.menu_page > 0:
                    self.menu_page -= 1
                elif WIDTH - 60 < x < WIDTH - 10 and self.menu_page < math.ceil(len(all_items)/APPS_PER_PAGE) - 1:
                    self.menu_page += 1

        elif "_LIST" in self.state or self.state == "BLUETOOTH" or self.state == "GAMES_LIST":
            btn_y = 205
            if btn_y < y < btn_y + 30:
                if 10 < x < 100:  # Up
                    self.selected_idx = max(0, self.selected_idx - 1)
                    self.scroll_offset = max(0, self.scroll_offset - 1 if self.selected_idx < self.scroll_offset + 2 else self.scroll_offset)
                elif 115 < x < 205:  # Select
                    self.select_item()
                elif 220 < x < 310:  # Down
                    self.selected_idx = min(len(self.files) - 1, self.selected_idx + 1)
                    self.scroll_offset = min(len(self.files) - 5, self.scroll_offset + 1 if self.selected_idx > self.scroll_offset + 2 else self.scroll_offset)
            elif 55 < y < 205:  # Touch item in list
                item_idx = (y - 55) // 30
                if 0 <= item_idx < min(5, len(self.files) - self.scroll_offset):
                    self.selected_idx = self.scroll_offset + item_idx
                    self.select_item()
            
            # Back cho games list
            if self.state == "GAMES_LIST" and 26 < y < 48 and WIDTH - 60 < x < WIDTH:
                self.state = "MENU"

        elif self.state == "MUSIC_PLAYER":
            btn_y = 180
            if btn_y < y < btn_y + 40:
                if 20 < x < 70:  # Prev
                    self.selected_idx = (self.selected_idx - 1) % len(self.files)
                    self.play_music()
                elif 85 < x < 135:  # Play/Pause
                    if self.is_paused:
                        pygame.mixer.music.unpause()
                        self.music_start_time += time.time() - self.music_paused_time
                        self.is_paused = False
                    else:
                        pygame.mixer.music.pause()
                        self.music_paused_time = time.time()
                        self.is_paused = True
                elif 150 < x < 200:  # Next
                    self.selected_idx = (self.selected_idx + 1) % len(self.files)
                    self.play_music()
                elif 215 < x < 265:  # Vol up
                    self.volume = min(1.0, self.volume + 0.1)
                    pygame.mixer.music.set_volume(self.volume)
                elif 270 < x < 320:  # Vol down
                    self.volume = max(0.0, self.volume - 0.1)
                    pygame.mixer.music.set_volume(self.volume)
            elif 26 < y < 48 and WIDTH - 70 < x < WIDTH:  # Back
                pygame.mixer.music.stop()
                self.state = "MUSIC_LIST"

        elif self.state == "BOOK_READER":
            btn_y = HEIGHT - 40
            if btn_y < y < btn_y + 30:
                if 10 < x < 100:  # Prev page
                    self.book_current_page = max(0, self.book_current_page - 1)
                elif WIDTH / 2 - 45 < x < WIDTH / 2 + 45:  # Back
                    self.state = "BOOK_LIST"
                elif WIDTH - 100 < x < WIDTH - 10:  # Next page
                    self.book_current_page = min(self.book_total_pages - 1, self.book_current_page + 1)

        elif self.state == "PHOTO_VIEWER":
            btn_y = HEIGHT - 40
            if btn_y < y < btn_y + 30:
                if 10 < x < 100:  # Prev
                    self.selected_idx = (self.selected_idx - 1) % len(self.files)
                    self.load_photo()
                elif WIDTH / 2 - 45 < x < WIDTH / 2 + 45:  # Back
                    self.state = "PHOTO_LIST"
                elif WIDTH - 100 < x < WIDTH - 10:  # Next
                    self.selected_idx = (self.selected_idx + 1) % len(self.files)
                    self.load_photo()

        elif self.state == "SNAKE_GAME":
            grid_size = 20
            if 50 < y < HEIGHT and not self.game_over:
                if x < WIDTH / 2:
                    self.snake_dir = (-1, 0) if self.snake_dir[0] == 0 else self.snake_dir  # Left nếu không ngược
                else:
                    self.snake_dir = (1, 0) if self.snake_dir[0] == 0 else self.snake_dir  # Right
                if y - 50 < (HEIGHT - 50) / 2:
                    self.snake_dir = (0, -1) if self.snake_dir[1] == 0 else self.snake_dir  # Up
                else:
                    self.snake_dir = (0, 1) if self.snake_dir[1] == 0 else self.snake_dir  # Down
            if self.game_over and HEIGHT/2 + 5 < y < HEIGHT/2 + 30 and WIDTH/2 - 50 < x < WIDTH/2 + 50:
                self.init_snake()
            if 26 < y < 48 and WIDTH - 70 < x < WIDTH:  # Back
                self.state = "GAMES_LIST"

        elif self.state == "TIC_TAC_TOE":
            cell_size = 80
            start_x, start_y = (WIDTH - 3*cell_size) // 2, 60
            if start_y < y < start_y + 3*cell_size and start_x < x < start_x + 3*cell_size and not self.ttt_winner:
                col = (x - start_x) // cell_size
                row = (y - start_y) // cell_size
                if self.ttt_board[row][col] == ' ':
                    self.ttt_board[row][col] = self.ttt_player
                    self.ttt_winner = self.check_ttt_winner()
                    if not self.ttt_winner:
                        self.ttt_player = 'O' if self.ttt_player == 'X' else 'X'
                        if self.ttt_player == 'O':
                            self.ttt_ai_move()
                            self.ttt_winner = self.check_ttt_winner()
                            self.ttt_player = 'X'
            btn_y = HEIGHT - 40
            if btn_y < y < btn_y + 30:
                if 10 < x < 100:  # Reset
                    self.init_tic_tac_toe()
                elif WIDTH - 100 < x < WIDTH - 10:  # Back
                    self.state = "GAMES_LIST"

    def select_item(self):
        if not self.files or self.selected_idx >= len(self.files):
            return
        file_name = self.files[self.selected_idx]
        
        if "MUSIC_LIST" in self.state:
            self.play_music()
        elif "VIDEO_LIST" in self.state:
            self.play_video()
        elif "PHOTO_LIST" in self.state:
            self.load_photo()
            self.state = "PHOTO_VIEWER"
        elif "BOOK_LIST" in self.state:
            self.load_book()
            self.state = "BOOK_READER"
        elif self.state == "BLUETOOTH":
            # Có thể thêm logic kết nối ở đây
            pass
        elif self.state == "GAMES_LIST":
            if file_name == "Snake":
                self.state = "SNAKE_GAME"
                self.init_snake()
            elif file_name == "Tic-Tac-Toe":
                self.state = "TIC_TAC_TOE"
                self.init_tic_tac_toe()

    def play_music(self):
        path = os.path.join(DIRS["MUSIC"], self.files[self.selected_idx])
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(self.volume)
        pygame.mixer.music.play()
        self.music_start_time = time.time()
        self.is_paused = False
        self.state = "MUSIC_PLAYER"

    def load_book(self):
        path = os.path.join(DIRS["BOOK"], self.files[self.selected_idx])
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        wrapper = textwrap.TextWrapper(width=35)  # Điều chỉnh width cho phù hợp màn hình
        self.book_lines = wrapper.wrap(text)
        self.book_total_pages = math.ceil(len(self.book_lines) / self.book_page_lines)
        self.book_current_page = 0

    def load_photo(self):
        path = os.path.join(DIRS["PHOTO"], self.files[self.selected_idx])
        self.current_image = Image.open(path)

    def play_video(self):
        self.emergency_cleanup()
        path = os.path.join(DIRS["VIDEO"], self.files[self.selected_idx])
        
        # Video stream to fbdev
        video_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", path, "-vf", "scale=320:240",
            "-f", "fbdev", "/dev/fb1"
        ]
        self.video_process = subprocess.Popen(video_cmd)
        
        # Audio stream to alsa
        audio_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", path, "-vn", "-f", "alsa", "default"
        ]
        self.audio_process = subprocess.Popen(audio_cmd)
        
        self.state = "VIDEO_PLAYER"

    def run(self):
        def signal_handler(sig, frame):
            self.emergency_cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        last_update = time.time()
        while self.running:
            if self.state == "VIDEO_PLAYER":
                if self.video_process.poll() is not None and self.audio_process.poll() is not None:
                    self.emergency_cleanup()
                    self.state = "VIDEO_LIST"
                time.sleep(0.1)
                continue
            
            if self.state == "SNAKE_GAME" and not self.game_over:
                if time.time() - last_update > 0.2:
                    self.update_snake()
                    last_update = time.time()
            
            image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
            draw = ImageDraw.Draw(image)
            self.draw(image, draw)
            device.display(image)
            time.sleep(0.05)

# ==========================================
# CHẠY ỨNG DỤNG
# ==========================================

app = DA_PHUONG_TIEN()

def touch_callback(x, y):
    app.handle_touch(x, y)

touch.set_handler(touch_callback)

while True:
    touch.poll()
    app.run()  # Chạy vòng lặp chính внутри run, nhưng để poll ngoài để touch responsive
    time.sleep(0.01)
