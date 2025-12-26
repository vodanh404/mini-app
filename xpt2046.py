import board
import busio
import digitalio
import time

class XPT2046:
    # Lệnh điều khiển (Control bytes)
    CMD_X = 0x90
    CMD_Y = 0xD0

    def __init__(self, spi, cs_pin, irq_pin, width=240, height=320,
                 x_min=100, x_max=1962, y_min=100, y_max=1900, baudrate=1000000):
        """
        Khởi tạo driver XPT2046 với tính năng tự động hiệu chỉnh (Calibration).
        """
        self.spi = spi
        self.width = width
        self.height = height
        
        # --- Tối ưu hóa: Tính toán trước hệ số (Linear Regression) ---
        # Công thức: Pixel = (Raw * Multiplier) + Offset
        # Giúp chuyển đổi nhanh hơn mà không cần tính toán phức tạp mỗi lần chạm
        self.x_mult = width / (x_max - x_min)
        self.x_add = -x_min * self.x_mult
        
        self.y_mult = height / (y_max - y_min)
        self.y_add = -y_min * self.y_mult

        self.x_min_raw = x_min
        self.x_max_raw = x_max
        self.y_min_raw = y_min
        self.y_max_raw = y_max

        # --- Cấu hình Hardware ---
        self.cs = digitalio.DigitalInOut(cs_pin)
        self.cs.direction = digitalio.Direction.OUTPUT
        self.cs.value = True

        self.irq = digitalio.DigitalInOut(irq_pin)
        self.irq.direction = digitalio.Direction.INPUT
        self.irq.pull = digitalio.Pull.UP

        self.baudrate = baudrate
        
        # --- Tối ưu hóa: Tái sử dụng Buffer ---
        self._tx_buf = bytearray(3)
        self._rx_buf = bytearray(3)
        
        # Callback handler
        self.int_handler = None
        self.int_locked = False

    def set_handler(self, callback_func):
        """Thiết lập hàm callback sẽ được gọi khi có chạm hợp lệ."""
        self.int_handler = callback_func

    def is_touched(self):
        """Kiểm tra nhanh xem có tín hiệu vật lý không (IRQ Low)."""
        return not self.irq.value

    def _spi_transfer(self, command):
        """Gửi lệnh và nhận dữ liệu thô (Private method)."""
        self._tx_buf[0] = command
        self._tx_buf[1] = 0x00
        self._tx_buf[2] = 0x00

        # Khóa bus SPI
        while not self.spi.try_lock():
            pass
        
        try:
            self.spi.configure(baudrate=self.baudrate)
            self.cs.value = False
            self.spi.write_readinto(self._tx_buf, self._rx_buf)
            self.cs.value = True
        finally:
            self.spi.unlock()

        # Xử lý kết quả 12-bit
        return ((self._rx_buf[1] << 8) | self._rx_buf[2]) >> 4

    def _raw_touch(self):
        """Đọc cặp tọa độ thô (X, Y)."""
        x = self._spi_transfer(self.CMD_X)
        y = self._spi_transfer(self.CMD_Y)
        
        # Kiểm tra xem giá trị có nằm trong vùng hợp lý không
        # Mở rộng biên độ một chút để tránh mất nét ở mép màn hình
        if (0 < x < 4096) and (0 < y < 4096):
            return x, y
        return None

    def normalize(self, x, y):
        """Chuyển đổi Raw -> Pixel dựa trên hệ số đã tính trước."""
        val_x = int((x * self.x_mult) + self.x_add)
        val_y = int((y * self.y_mult) + self.y_add)
        
        # Kẹp giá trị (Clamp) để không văng ra khỏi màn hình
        return (
            max(0, min(val_x, self.width)),
            max(0, min(val_y, self.height))
        )

    def get_touch(self):
        """
        Lấy mẫu tọa độ chính xác.
        Sử dụng thuật toán trung bình cộng và độ lệch chuẩn để lọc nhiễu.
        """
        if not self.is_touched():
            return None

        # Cấu hình lấy mẫu
        confidence = 5  # Cần 5 mẫu tốt liên tiếp
        buff = []
        timeout_start = time.monotonic()
        timeout_sec = 0.2  # 200ms timeout là đủ cho phản ứng người dùng

        while (time.monotonic() - timeout_start) < timeout_sec:
            # Nếu nhấc tay ra giữa chừng -> Hủy
            if not self.is_touched(): 
                return None

            sample = self._raw_touch()
            if sample:
                buff.append(sample)
                
                # Khi đã đủ mẫu, kiểm tra độ ổn định
                if len(buff) >= confidence:
                    # Tính trung bình
                    mean_x = sum(p[0] for p in buff) // confidence
                    mean_y = sum(p[1] for p in buff) // confidence
                    
                    # Tính độ lệch (Variance)
                    # Công thức: tổng bình phương độ lệch so với trung bình
                    dev = sum((p[0] - mean_x)**2 + (p[1] - mean_y)**2 for p in buff) / confidence
                    
                    # Ngưỡng chấp nhận (50^2 vì tính theo bình phương khoảng cách)
                    if dev <= 150: 
                        return self.normalize(mean_x, mean_y)
                    else:
                        # Dữ liệu quá nhiễu, bỏ mẫu cũ nhất và thử lại
                        buff.pop(0) 

            # Nghỉ cực ngắn để ADC kịp hồi phục
            time.sleep(0.002) 

        return None

    def poll(self):
        """
        Hàm này cần được gọi liên tục trong vòng lặp chính (main loop).
        Nó sẽ tự động gọi 'handler' khi phát hiện chạm hợp lệ.
        """
        # Logic phát hiện cạnh xuống (Press)
        if self.is_touched() and not self.int_locked:
            coords = self.get_touch()
            if coords:
                self.int_locked = True
                if self.int_handler:
                    self.int_handler(coords[0], coords[1])
        
        # Logic phát hiện nhả tay (Release) - Debounce
        elif not self.is_touched() and self.int_locked:
            self.int_locked = False
