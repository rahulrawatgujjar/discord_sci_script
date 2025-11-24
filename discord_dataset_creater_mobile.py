import os
import time
import json
import random
import subprocess
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from dotenv import load_dotenv
from plyer import notification

load_dotenv()

# ---------- CONFIG ----------
UPLOAD_BASE = os.getenv("UPLOAD_BASE")
DOWNLOAD_BASE = os.getenv("DOWNLOAD_BASE")
PHONE_UPLOAD_DIR = "/sdcard/create_dataset"
PHONE_DOWNLOAD_DIR = "/sdcard/Download"
PROGRESS_FILE = "test_progress_discord.json"
MAX_RETRIES = 100

# Tap coordinates (adjust for your device)
COORD_PLUS = (95, 2253)
COORD_ATTACH = (780, 1555)
COORD_IMAGE = (500, 750)
COORD_SEND = (985, 1365)
COORD_PHOTO = (600, 900)
COORD_DOTS = (1011, 161)
COORD_SAVE = (720, 320)

# ---------- HELPERS ----------
def adb(cmd):
    """Run adb command safely."""
    result = subprocess.run(["adb"] + cmd.split(), capture_output=True, text=True)
    if result.stderr.strip():
        print(result.stderr.strip())
    return result.stdout.strip()

def notify(title, msg):
    """Timestamped logging."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔔 {title}: {msg}")
    # try:
    #     notification.notify(title=title, message=msg, timeout=5)
    # except Exception:
    #     pass

def sleep_random(base, var=1.5):
    """Sleep with small random offset."""
    time.sleep(base + random.uniform(0, var))

def check_device():
    out = adb("devices")
    if "device" not in out.splitlines()[-1]:
        notify("ADB", "❌ No connected Android device found!")
        raise RuntimeError("No Android device connected")
    notify("ADB", "✅ Device connected successfully")

def ensure_phone_dirs():
    adb("shell mkdir -p /sdcard/create_dataset")
    notify("ADB", "📁 Ensured /sdcard/create_dataset exists")

def start_discord():
    adb("shell am start -n com.discord/.main.MainActivity")
    sleep_random(5, 2)

def pull_image(phone_path, local_path):
    res = subprocess.run(["adb", "pull", phone_path, str(local_path)], capture_output=True)
    return res.returncode == 0 and Path(local_path).exists()

# ---------- PROGRESS HANDLER ----------
def load_progress():
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

def mark_completed(progress, camera_model, img_name):
    if camera_model not in progress:
        progress[camera_model] = []
    if img_name not in progress[camera_model]:
        progress[camera_model].append(img_name)
        save_progress(progress)

def is_completed(progress, camera_model, img_name):
    return camera_model in progress and img_name in progress[camera_model]

# ---------- CORE ----------
def upload_and_download_one(image_path: Path) -> bool:
    img_name = image_path.name
    camera_model = image_path.parent.name
    phone_upload_path = f"{PHONE_UPLOAD_DIR}/{img_name}"
    local_download_path = Path(DOWNLOAD_BASE) / camera_model / img_name
    phone_download_path = f"{PHONE_DOWNLOAD_DIR}/{img_name}"

    local_download_path.parent.mkdir(parents=True, exist_ok=True)

    notify("ADB", f"Processing {camera_model}/{img_name}")
    adb(f'push {str(image_path)} {phone_upload_path}')
    sleep_random(1, 0.5)

    # start_discord()

    try:
        notify("ADB", "Clicking plus button" )
        adb(f"shell input tap {COORD_PLUS[0]} {COORD_PLUS[1]}")
        sleep_random(2)

        notify("ADB", "Clicking attach button")
        adb(f"shell input tap {COORD_ATTACH[0]} {COORD_ATTACH[1]}")
        sleep_random(2)

        notify("ADB", "Selecting image")
        adb(f"shell input tap {COORD_IMAGE[0]} {COORD_IMAGE[1]}")
        sleep_random(2)

        notify("ADB", "Sending image")
        adb(f"shell input tap {COORD_SEND[0]} {COORD_SEND[1]}")
        sleep_random(10, 2)


        # Save uploaded image to phone
        notify("ADB", "Click to open uploaded image")
        adb(f"shell input tap {COORD_PHOTO[0]} {COORD_PHOTO[1]}")
        sleep_random(7, 1)

        notify("ADB", "Opening options menu")
        adb(f"shell input tap {COORD_DOTS[0]} {COORD_DOTS[1]}")
        sleep_random(2)

        notify("ADB", "Clicking save option")
        adb(f"shell input tap {COORD_SAVE[0]} {COORD_SAVE[1]}")
        sleep_random(3)

        notify("ADB", "Going back to chat")
        adb("shell input keyevent KEYCODE_BACK")
        sleep_random(2)

        # Pull image back
        notify("ADB", f"📥 Pulling compressed {img_name}")
        if pull_image(phone_download_path, local_download_path):
            notify("ADB", f"✅ Downloaded successfully: {img_name}")
            adb(f"shell rm '{phone_upload_path}'")
            adb(f"shell rm '{phone_download_path}'")
            return True
        else:
            notify("ADB", f"⚠️ Failed to pull {img_name}")
            adb(f"shell rm '{phone_upload_path}'")
            return False

    except Exception as e:
        notify("Error", f"Exception during {img_name}: {e}")
        return False

# ---------- PROCESSING ----------
def process_folder(folder_path: Path, progress):
    camera_model = folder_path.name
    images = sorted([f for f in folder_path.glob("*.JPG") if f.is_file()])

    if not images:
        notify("Folder", f"⚠️ No images in {camera_model}")
        return

    notify("Folder", f"📂 Processing {len(images)} images in '{camera_model}' ...")
    progress_bar = tqdm(images, desc=f"{camera_model}", unit="img")

    for img in progress_bar:
        if is_completed(progress, camera_model, img.name):
            continue  # already done

        success = False
        attempts = 0
        while not success and attempts < MAX_RETRIES:
            attempts += 1
            success = upload_and_download_one(img)
            if not success:
                notify("Retry", f"🔁 Retrying {img.name} (Attempt {attempts}/{MAX_RETRIES})")
                sleep_random(5, 3)

        if success:
            mark_completed(progress, camera_model, img.name)
        else:
            notify("Error", f"❌ Gave up on {img.name} after {MAX_RETRIES} retries.")

        sleep_random(1, 2)

# ---------- MAIN ----------
def main():
    Path(DOWNLOAD_BASE).mkdir(parents=True, exist_ok=True)
    check_device()
    ensure_phone_dirs()

    progress = load_progress()

    subfolders = sorted([f for f in Path(UPLOAD_BASE).iterdir() if f.is_dir()])
    if not subfolders:
        notify("Setup", "⚠️ No camera model folders found.")
        return

    total_images = sum(len(list(f.glob('*.JPG'))) for f in subfolders)
    notify("Main", f"🎯 Found {len(subfolders)} folders with {total_images} total images.")

    for folder in subfolders:
        process_folder(folder, progress)

    notify("All Done", "✅ All folders processed successfully!")

# ---------- ENTRY ----------
if __name__ == "__main__":
    main()
