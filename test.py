import cv2
from PIL import Image
import ST7789  # From https://github.com/pimoroni/st7789-python
import time
import sys
import os

def check_video_format(video_path):
    """Check video format and provide conversion suggestions."""
    if not os.path.exists(video_path):
        print(f"Error: Video file '{video_path}' not found.")
        return False
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video '{video_path}'.")
        return False
    
    # Get video properties
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Decode fourcc to codec name
    codec = ''.join([chr((int(fourcc) >> 8 * i) & 0xFF) for i in range(4)])
    
    print(f"Video Info:")
    print(f"  Path: {video_path}")
    print(f"  Codec: {codec}")
    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {fps}")
    
    if 'av01' in codec.lower() or 'av1' in codec.lower():
        print("\nWARNING: AV1 codec detected! OpenCV may not support this on your platform.")
        print("Recommendation: Convert video to H.264 (mp4) or H.265 (hevc) format.")
        print("Use ffmpeg: ffmpeg -i input.av1 -c:v libx264 -preset fast output.mp4")
        return False
    
    cap.release()
    return True

def convert_av1_to_mp4(input_path, output_path):
    """Convert AV1 video to MP4 using ffmpeg (if available)."""
    try:
        import subprocess
        cmd = [
            'ffmpeg', '-y',  # -y to overwrite output
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',  # Quality setting
            '-c:a', 'aac',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Successfully converted {input_path} to {output_path}")
            return True
        else:
            print(f"FFmpeg conversion failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("FFmpeg not found. Please install ffmpeg and try again.")
        return False
    except Exception as e:
        print(f"Conversion error: {e}")
        return False

# Configure the display for Raspberry Pi 4
disp = ST7789.ST7789(
    height=240,
    width=320,
    rotation=0,  # Adjust as needed
    port=0,
    cs=0,  # device=0
    dc=24,  # gpio_DC=24
    rst=25,  # gpio_RST=25
    backlight=13,  # Adjust if needed
    spi_speed_hz=80000000,  # baudrate=80000000
    offset_left=0,
    offset_top=0
)

# Initialize display
try:
    disp.begin()
    print("Display initialized successfully.")
except Exception as e:
    print(f"Error initializing display: {e}")
    sys.exit(1)

# Video configuration
video_path = 'your_video.mp4'  # Replace with your actual video path
converted_path = 'converted_video.mp4'  # Temporary converted file

# Check and handle video format
print("Checking video format...")
if not check_video_format(video_path):
    # Try to auto-convert if it's AV1
    print(f"\nAttempting to convert {video_path} to MP4...")
    if convert_av1_to_mp4(video_path, converted_path):
        video_path = converted_path
        print(f"Using converted video: {video_path}")
    else:
        print("\nPlease convert your video manually using:")
        print("ffmpeg -i input.av1 -c:v libx264 -preset fast output.mp4")
        print("Then update video_path in the script and try again.")
        sys.exit(1)

# Open video with better error handling
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print(f"Error: Could not open video '{video_path}' even after conversion.")
    print("Try a different video format (MP4 with H.264 codec).")
    sys.exit(1)

# Get video properties
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"\nStarting playback:")
print(f"  FPS: {fps}")
print(f"  Total frames: {total_frames}")
print(f"  Frame size: {frame_width}x{frame_height}")
print(f"  Display size: {disp.width}x{disp.height}")

frame_delay = 1 / fps if fps > 0 else 0.033  # ~30 FPS default
frame_count = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("\nEnd of video reached.")
            break
        
        frame_count += 1
        if frame_count % 30 == 0:  # Progress update every 30 frames
            print(f"Processed {frame_count}/{total_frames} frames...")
        
        # Skip if frame is empty (common with codec issues)
        if frame is None or frame.size == 0:
            print(f"Warning: Empty frame at {frame_count}, skipping...")
            continue
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Create PIL Image
        img = Image.fromarray(frame_rgb)
        
        # Resize to display dimensions (you can adjust aspect ratio handling)
        img_resized = img.resize((disp.width, disp.height), Image.LANCZOS)
        
        # Display the frame
        try:
            disp.display(img_resized)
        except Exception as e:
            print(f"Display error at frame {frame_count}: {e}")
            continue
        
        # Frame delay
        time.sleep(frame_delay)

except KeyboardInterrupt:
    print(f"\nPlayback interrupted by user at frame {frame_count}.")

finally:
    # Cleanup
    cap.release()
    # Clean up converted file if it exists
    if os.path.exists(converted_path):
        try:
            os.remove(converted_path)
            print("Cleaned up temporary converted file.")
        except:
            pass
    
    print("Video playback completed.")
    print(f"Total frames processed: {frame_count}")
