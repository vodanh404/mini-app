import os
from pyboy import PyBoy

# Cấu hình đường dẫn
ROM_ROOT = r"E:\roms" # Đảm bảo thư mục này tồn tại
SYSTEM = "gb"         # Chỉ tập trung vào GameBoy
PAGE_SIZE = 10

# ===================== SCAN =====================
def scan_games():
    """Quét các file .gb và .gbc trong thư mục ROM_ROOT/gb"""
    games = []
    path = os.path.join(ROM_ROOT, SYSTEM)

    if not os.path.isdir(path):
        print(f"❌ Thư mục không tồn tại: {path}")
        return []

    for f in os.listdir(path):
        if f.lower().endswith((".gb", ".gbc")):
            games.append(f)

    return sorted(games)

# ===================== UI =====================
def clear():
    os.system("cls" if os.name == "nt" else "clear")

def show_page(games, page):
    total_pages = max(1, (len(games) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE

    clear()
    print(f"🎮 GAMEBOY (PYBOY) LIST - Trang {page + 1}/{total_pages}")
    print("=" * 45)

    if not games:
        print(" (Không tìm thấy game nào trong thư mục gb)")
    else:
        for i, game in enumerate(games[start:end], start + 1):
            print(f"{i:3}. {game}")

    print("=" * 45)
    print("[SỐ] Chơi | [N] Trang sau | [P] Trang trước | [Q] Thoát")

# ===================== RUNNER =====================
def run_gb(path):
    print(f"🚀 Đang khởi động: {os.path.basename(path)}")
    # PyBoy hỗ trợ cửa sổ SDL2 mặc định
    pyboy = PyBoy(path, window="SDL2")
    
    # Thiết lập tốc độ tối đa (tùy chọn)
    pyboy.set_emulation_speed(1) 

    while pyboy.tick():
        # Vòng lặp chính của emulator
        pass
    
    pyboy.stop()

# ===================== MAIN =====================
def main():
    games = scan_games()
    page = 0

    while True:
        show_page(games, page)
        cmd = input("👉 ").strip().lower()

        if cmd == "q":
            break
        
        # Xử lý chọn số game
        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(games):
                path = os.path.join(ROM_ROOT, SYSTEM, games[idx])
                clear()
                run_gb(path)
            else:
                input("❌ Số không hợp lệ! Nhấn Enter để thử lại...")

        # Chuyển trang
        elif cmd == "n" and (page + 1) * PAGE_SIZE < len(games):
            page += 1
        elif cmd == "p" and page > 0:
            page -= 1

if __name__ == "__main__":
    main()
