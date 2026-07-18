"""
Custom Thermal HUD Overlay with Multi-Channel Audio Systems
-----------------------------------------------------------
A transparent, click-through, always-on-top window that draws a custom
reticle + status text over the game, and mirrors live values via OCR.

Controls:
  Hold SHIFT   -> show overlay & enable audio profile
  Press N      -> toggle thermal system on/off (dot 1 goes red -> green)
  Press Y      -> toggle thermal color filter layer on/off (dot 2 goes red -> green)
  Press T      -> cycle thermal background color (WHITE, GREEN, RED, BLUE)
  Press V      -> play "Identified!" voice alert (starts a 5-second window)
  Double Tap 1 -> play "Gunner Sabot Tank!" voice line (Max Volume)
  Double Tap 2 -> play "Gunner Heat PC!" voice line (Max Volume)
  Left Click   -> execute dynamic firing sequence (Plays "Shoot 'em again!" if within 5s of V)
  Hold SPACE   -> loop MG and Echo audio (Echo sustains for 0.2s after release)
"""

import ctypes
import difflib
import json
import random
import re
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import cv2
import keyboard
import numpy as np
import pygame  # Handles multi-channel sound blending
import pytesseract
from PIL import Image, ImageColor, ImageDraw, ImageGrab, ImageTk
from pynput import mouse  # High-performance mouse velocity tracking

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CFG = json.load(f)

pytesseract.pytesseract.tesseract_cmd = CFG["tesseract_cmd"]

AMMO_REGION = tuple(CFG["ammo_region"])       
DISTANCE_REGION = tuple(CFG["distance_region"])
READY_REGION = tuple(CFG["ready_region"])
DEATH_REGION = tuple(CFG["death_region"])

HOLD_MODE = CFG.get("hold_mode", True)
POLL_MS = max(60, CFG.get("poll_interval_ms", 60)) 
DEATH_KEYWORD = CFG.get("death_keyword", "RETICLETEST3")

RETICLE_SCALE = CFG.get("reticle_scale", 0.55)
FONT_SIZE = CFG.get("font_size", 11)

VIGNETTE_ENABLED = CFG.get("vignette_enabled", True)
SCOPE_WIDTH = CFG.get("scope_width", 2000)
SCOPE_HEIGHT = CFG.get("scope_height", 760)
SCOPE_CORNER_RADIUS = CFG.get("scope_corner_radius", 280)
VIGNETTE_COLOR = CFG.get("vignette_color", "#000000")

OCR_UPSCALE = CFG.get("ocr_upscale", 2) 
FUZZY_CUTOFF = CFG.get("fuzzy_cutoff", 0.45)
KNOWN_AMMO_TYPES = [s.upper() for s in CFG.get("known_ammo_types", [])]
KNOWN_READY_STATES = [s.upper() for s in CFG.get("known_ready_states", [])]

HUD_COLOR = CFG.get("hud_color", "#5a9c6e")
DOT_RED = CFG.get("dot_red", "#e33d3d")
DOT_GREEN = CFG.get("dot_green", "#3de35a")

TRANSPARENT_KEY = "#000100" 

THERMAL_WIDTH = CFG.get("thermal_image_width", 800)
THERMAL_HEIGHT = CFG.get("thermal_image_height", 600)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

class State:
    def __init__(self):
        self.visible = False
        self.thermal_on = False
        self.filter_on = False  
        self.thermal_colors = ["WHITE", "GREEN", "RED", "BLUE"]
        self.color_index = 0
        self.dead = False
        self.ammo_text = "APFSDS"
        self.distance_text = "--M"
        self.ready_text = "READY"
        
        # Double tap timings
        self.last_press_1 = 0.0
        self.last_press_2 = 0.0
        
        # V Command Tracking for "Shoot 'em again" rule
        self.last_v_time = 0.0
        
        # Weapon firing control tracking
        self.space_is_down = False
        
        # Mouse movement speed diagnostics
        self.mouse_speed = 0.0
        self.last_mouse_pos = (0, 0)
        self.last_mouse_time = time.time()
        
        self.lock = threading.Lock()

    @property
    def current_color(self):
        return self.thermal_colors[self.color_index]


state = State()
stop_event = threading.Event()

# ---------------------------------------------------------------------------
# Audio Initialization & Controls
# ---------------------------------------------------------------------------

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

# Load sound paths safely
BASE_DIR = Path(__file__).parent
snd_idle = pygame.mixer.Sound(str(BASE_DIR / "idle.mp3"))
snd_turret = pygame.mixer.Sound(str(BASE_DIR / "turret move.mp3"))

# Gunshot sounds mixed down slightly so voice stands out
snd_fire_gun = pygame.mixer.Sound(str(BASE_DIR / "Fire.mp3"))
snd_fire_gun.set_volume(0.65)

snd_fire_vc = pygame.mixer.Sound(str(BASE_DIR / "fire!-calm-made-with-Voicemod.mp3"))
snd_fire_vc.set_volume(0.85)

snd_reload = pygame.mixer.Sound(str(BASE_DIR / "Reload.mp3"))
snd_reload.set_volume(0.65)

snd_up = pygame.mixer.Sound(str(BASE_DIR / "up!-calm-made-with-Voicemod.mp3"))
snd_up.set_volume(0.85)

# Automatic continuous secondary weapons
snd_mg = pygame.mixer.Sound(str(BASE_DIR / "MG.ogg"))
snd_mg.set_volume(0.70)
snd_echo = pygame.mixer.Sound(str(BASE_DIR / "Echo.ogg"))
snd_echo.set_volume(0.75)

# --- MAX VOICE VOLUME ALERTS ---
snd_sabot = pygame.mixer.Sound(str(BASE_DIR / "gunner-sabot-tank!-panic-made-with-Voicemod.mp3"))
snd_sabot.set_volume(1.0)  

snd_heat = pygame.mixer.Sound(str(BASE_DIR / "gunner-heat-pc!-panic-made-with-Voicemod.mp3"))
snd_heat.set_volume(1.0)   

snd_identified = pygame.mixer.Sound(str(BASE_DIR / "identified!-calm-made-with-Voicemod.mp3"))
snd_identified.set_volume(0.9)

snd_shoot_again = pygame.mixer.Sound(str(BASE_DIR / "shoot-em-again!-panic-made-with-Voicemod.mp3"))
snd_shoot_again.set_volume(1.0)

# Dedicate specialized internal channels
chan_idle = pygame.mixer.Channel(0)
chan_turret = pygame.mixer.Channel(1)
chan_effects = pygame.mixer.Channel(2)
chan_reload = pygame.mixer.Channel(4)  
chan_voice_alerts = pygame.mixer.Channel(5) 
chan_mg = pygame.mixer.Channel(6)
chan_echo = pygame.mixer.Channel(7)


def fire_sequence_worker():
    """Asynchronous timing queue for the multi-stage weapon layout."""
    with state.lock:
        v_diff = time.time() - state.last_v_time

    # Play "Shoot 'em again" voice line instead of standard fire callouts if within 5 seconds
    if v_diff <= 5.0:
        chan_voice_alerts.play(snd_shoot_again)
        chan_effects.play(snd_fire_gun)
        chan_reload.play(snd_reload)
    else:
        chan_effects.play(snd_fire_gun)
        pygame.mixer.Channel(3).play(snd_fire_vc)
        chan_reload.play(snd_reload)
        
    time.sleep(1.0)
    with state.lock:
        still_active = state.visible and not state.dead
    if still_active:
        chan_effects.play(snd_up)


def audio_manager_worker():
    """Manages loops, loops volumes smoothly, handles turret tracking wind-downs."""
    chan_idle.play(snd_idle, loops=-1)
    chan_idle.set_volume(0)
    
    chan_turret.play(snd_turret, loops=-1)
    chan_turret.set_volume(0)

    current_turret_volume = 0.0

    while not stop_event.is_set():
        with state.lock:
            active = state.visible and not state.dead
            speed = state.mouse_speed
            state.mouse_speed *= 0.80  

        if active:
            chan_idle.set_volume(0.35)
            
            if speed > 2.0:
                target_volume = min(0.7, max(0.15, speed / 140.0)) 
            else:
                target_volume = 0.0
            
            if target_volume > current_turret_volume:
                current_turret_volume += (target_volume - current_turret_volume) * 0.4
            else:
                current_turret_volume += (target_volume - current_turret_volume) * 0.08

            chan_turret.set_volume(current_turret_volume)
        else:
            current_turret_volume = 0.0
            chan_idle.set_volume(0.0)
            chan_turret.set_volume(0.0)

        time.sleep(0.02)


# ---------------------------------------------------------------------------
# Mouse Tracking
# ---------------------------------------------------------------------------

def on_mouse_move(x, y):
    """Calculates instantaneous vector magnitudes for structural adjustments."""
    t = time.time()
    with state.lock:
        if state.visible and not state.dead:
            dx = x - state.last_mouse_pos[0]
            dy = y - state.last_mouse_pos[1]
            dt = t - state.last_mouse_time
            if dt > 0:
                state.mouse_speed = np.sqrt(dx**2 + dy**2) / dt
        state.last_mouse_pos = (x, y)
        state.last_mouse_time = t


def on_mouse_click(x, y, button, pressed):
    """Monitors client actions to trigger fire pipelines."""
    if button == mouse.Button.left and pressed:
        with state.lock:
            allowed = state.visible and not state.dead
        if allowed:
            threading.Thread(target=fire_sequence_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

def _preprocess_fast(pil_img, upscale=OCR_UPSCALE):
    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
    if upscale > 1:
        cv_img = cv2.resize(cv_img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_LINEAR)
    _, thresh = cv2.threshold(cv_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def ocr_region(region, whitelist=None, psm=7):
    x, y, w, h = region
    try:
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    except Exception:
        return ""

    config = f"--psm {psm} -c tessedit_do_invert=0"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"

    processed = _preprocess_fast(img)
    try:
        txt = pytesseract.image_to_string(processed, config=config)
    except Exception:
        txt = ""
        
    return re.sub(r"[^A-Za-z0-9. ]", "", txt).strip().upper()


def fuzzy_correct(raw_text, known_values):
    raw_text = raw_text.strip()
    if not raw_text or not known_values:
        return raw_text
    scored = sorted(
        ((difflib.SequenceMatcher(None, raw_text, kv).ratio(), kv) for kv in known_values),
        reverse=True,
    )
    best_score, best_val = scored[0]
    return best_val if best_score >= FUZZY_CUTOFF else raw_text


AMMO_WHITELIST = "APFSDS", "HEAT", "HE", "HESH", "AP", "APHE", "APDS", "ATGM"
DISTANCE_WHITELIST = "0123456789M"
READY_WHITELIST = "READY", "RELOADING", "LOADING", "AIMING", "EMPTY"


def ocr_worker():
    sleep_duration = POLL_MS / 1000.0

    while not stop_event.is_set():
        with state.lock:
            is_active = state.visible and not state.dead

        if not is_active:
            time.sleep(0.1) 
            continue

        try:
            raw_ammo = ocr_region(AMMO_REGION, whitelist=AMMO_WHITELIST, psm=6)
            if raw_ammo:
                lines = [ln.strip() for ln in raw_ammo.splitlines() if ln.strip()]
                corrected = [fuzzy_correct(ln, KNOWN_AMMO_TYPES) for ln in lines]
                if corrected:
                    with state.lock:
                        state.ammo_text = " ".join(corrected)
        except Exception:
            pass

        try:
            raw_distance = ocr_region(DISTANCE_REGION, whitelist=DISTANCE_WHITELIST, psm=7)
            if raw_distance:
                m = re.search(r"\d+\s*M", raw_distance)
                if m:
                    with state.lock:
                        state.distance_text = m.group(0).replace(" ", "")
        except Exception:
            pass

        try:
            raw_ready = ocr_region(READY_REGION, whitelist=READY_WHITELIST, psm=7)
            if raw_ready:
                with state.lock:
                    state.ready_text = fuzzy_correct(raw_ready, KNOWN_READY_STATES)
        except Exception:
            pass

        try:
            death_txt = ocr_region(DEATH_REGION, psm=6)
            if DEATH_KEYWORD.lower() in death_txt.lower():
                with state.lock:
                    state.dead = True
        except Exception:
            pass

        time.sleep(sleep_duration)


# ---------------------------------------------------------------------------
# Hotkeys
# ---------------------------------------------------------------------------

def on_shift_down(_event=None):
    with state.lock:
        state.dead = False
        if HOLD_MODE:
            state.visible = True
        else:
            state.visible = not state.visible


def on_shift_up(_event=None):
    if HOLD_MODE:
        with state.lock:
            state.visible = False


def on_n_press(_event=None):
    with state.lock:
        state.thermal_on = not state.thermal_on


def on_y_press(_event=None):
    with state.lock:
        state.filter_on = not state.filter_on


def on_t_press(_event=None):
    with state.lock:
        state.color_index = (state.color_index + 1) % len(state.thermal_colors)


def on_v_press(_event=None):
    with state.lock:
        allowed = state.visible and not state.dead
        if allowed:
            state.last_v_time = time.time()  # Start the 5-second window
    if allowed:
        chan_voice_alerts.play(snd_identified)


def on_1_press(_event=None):
    t = time.time()
    with state.lock:
        allowed = state.visible and not state.dead
        diff = t - state.last_press_1
        state.last_press_1 = t
    
    if allowed and diff < 0.4:  
        chan_voice_alerts.play(snd_sabot)


def on_2_press(_event=None):
    t = time.time()
    with state.lock:
        allowed = state.visible and not state.dead
        diff = t - state.last_press_2
        state.last_press_2 = t
        
    if allowed and diff < 0.4:
        chan_voice_alerts.play(snd_heat)


def handle_echo_tail():
    """Waits for 0.2 seconds before terminating the loop, unless re-engaged."""
    time.sleep(0.2)
    with state.lock:
        still_released = not state.space_is_down
    if still_released:
        chan_echo.stop()


def on_space_down(_event=None):
    with state.lock:
        allowed = state.visible and not state.dead
        already_pressed = state.space_is_down
        if allowed and not already_pressed:
            state.space_is_down = True
            
    if allowed and not already_pressed:
        chan_mg.play(snd_mg, loops=-1)
        chan_echo.play(snd_echo, loops=-1)


def on_space_up(_event=None):
    with state.lock:
        if state.space_is_down:
            state.space_is_down = False
            chan_mg.stop()
            # Start background thread to handle the 0.2-second tail sustain
            threading.Thread(target=handle_echo_tail, daemon=True).start()


def hotkey_worker():
    keyboard.on_press_key("shift", on_shift_down, suppress=False)
    keyboard.on_release_key("shift", on_shift_up, suppress=False)
    keyboard.on_press_key("n", on_n_press, suppress=False)
    keyboard.on_press_key("y", on_y_press, suppress=False)
    keyboard.on_press_key("t", on_t_press, suppress=False)
    keyboard.on_press_key("v", on_v_press, suppress=False)
    keyboard.on_press_key("1", on_1_press, suppress=False)
    keyboard.on_press_key("2", on_2_press, suppress=False)
    
    # Handle the space machine gun / echo tracks
    keyboard.on_press_key("space", on_space_down, suppress=False)
    keyboard.on_release_key("space", on_space_up, suppress=False)
    keyboard.wait()


# ---------------------------------------------------------------------------
# Click-through window setup
# ---------------------------------------------------------------------------

def make_click_through(root):
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080

    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
    )


# ---------------------------------------------------------------------------
# Graphics drawing
# ---------------------------------------------------------------------------

def draw_reticle(canvas, cx, cy):
    s = RETICLE_SCALE
    color = HUD_COLOR

    def o(px):
        return round(px * s)

    canvas.create_oval(cx - 1, cy - 1, cx + 1, cy + 1, fill=color, outline="")
    
    ring_r = o(14)
    canvas.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r, outline=color, width=2)

    canvas.create_line(cx, cy - o(65), cx, cy - o(25), fill=color, width=2)
    canvas.create_line(cx, cy + o(25), cx, cy + o(65), fill=color, width=2)
    canvas.create_line(cx - o(55), cy, cx - o(20), cy, fill=color, width=2)
    canvas.create_line(cx + o(20), cy, cx + o(55), cy, fill=color, width=2)

    canvas.create_line(cx - o(185), cy, cx - o(130), cy, fill=color, width=2)
    canvas.create_line(cx + o(130), cy, cx + o(185), cy, fill=color, width=2)

    canvas.create_line(cx - o(105), cy - o(30), cx - o(60), cy - o(30), fill=color, width=2)
    canvas.create_line(cx - o(105), cy + o(30), cx - o(60), cy + o(30), fill=color, width=2)

    canvas.create_line(cx + o(60), cy - o(30), cx + o(105), cy - o(30), fill=color, width=2)
    canvas.create_line(cx + o(60), cy + o(30), cx + o(105), cy + o(30), fill=color, width=2)


def build_vignette_photo(sw, sh):
    img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    vig_rgb = ImageColor.getrgb(VIGNETTE_COLOR)
    draw.rectangle([0, 0, sw, sh], fill=vig_rgb + (255,))

    left = (sw - SCOPE_WIDTH) // 2
    top = (sh - SCOPE_HEIGHT) // 2
    right = left + SCOPE_WIDTH
    bottom = top + SCOPE_HEIGHT

    draw.rounded_rectangle([left, top, right, bottom], radius=SCOPE_CORNER_RADIUS, fill=(0, 0, 0, 0))
    return ImageTk.PhotoImage(img)


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", TRANSPARENT_KEY)
    root.configure(bg=TRANSPARENT_KEY)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{sw}x{sh}+0+0")

    canvas = tk.Canvas(root, width=sw, height=sh, bg=TRANSPARENT_KEY, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    root.update_idletasks()
    make_click_through(root)

    vignette_photo = build_vignette_photo(sw, sh) if VIGNETTE_ENABLED else None

    cx, cy = sw // 2, sh // 2
    font = ("Bahnschrift", FONT_SIZE, "bold")

    TOP_Y = 0.156
    BOT_Y = 0.879

    X_GUNNER = 0.164
    X_DISTANCE_LABEL = 0.306
    X_DISTANCE_VAL = 0.361
    X_PRONTO = 0.481
    X_AMMO_LABEL = 0.738
    X_AMMO_VAL = 0.787

    X_READY = 0.220
    X_AUTO = 0.330
    X_THERMAL = 0.5
    X_WHHOT = 0.62
    X_DOT1 = 0.742   
    X_DOT2 = 0.760   
    
    DOT_R = max(3, round(6 * RETICLE_SCALE))

    COLOR_MAP = {
        "WHITE": "#ffffff",
        "GREEN": "#22aa33",
        "RED":   "#cc2222",
        "BLUE":  "#2244cc"
    }

    def render():
        canvas.delete("all")
        with state.lock:
            visible = state.visible and not state.dead
            thermal_on = state.thermal_on
            filter_on = state.filter_on
            current_color = state.current_color
            ammo_text = state.ammo_text
            distance_text = state.distance_text
            ready_text = state.ready_text

        if visible:
            if thermal_on and filter_on and current_color in COLOR_MAP:
                hex_color = COLOR_MAP[current_color]
                
                jx0 = random.randint(-2, 2)
                jy0 = random.randint(-2, 2)
                jx1 = random.randint(-2, 2)
                jy1 = random.randint(-2, 2)
                
                x0 = cx - (THERMAL_WIDTH // 2) + jx0
                y0 = cy - (THERMAL_HEIGHT // 2) + jy0
                x1 = cx + (THERMAL_WIDTH // 2) + jx1
                y1 = cy + (THERMAL_HEIGHT // 2) + jy1
                
                canvas.create_rectangle(x0, y0, x1, y1, fill=hex_color, outline="", stipple="gray25")

            if vignette_photo is not None:
                canvas.create_image(0, 0, anchor="nw", image=vignette_photo)

            draw_reticle(canvas, cx, cy)

            ty = sh * TOP_Y
            by = sh * BOT_Y

            canvas.create_text(sw * X_GUNNER, ty, text="GUNNER", fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_DISTANCE_LABEL, ty, text="DISTANCE", fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_DISTANCE_VAL, ty, text=distance_text, fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_PRONTO, ty, text="PRONTO", fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_AMMO_LABEL, ty, text="AMMO", fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_AMMO_VAL, ty, text=ammo_text, fill=HUD_COLOR, font=font, anchor="w")

            canvas.create_text(sw * X_READY, by, text=ready_text, fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_AUTO, by, text="AUTO", fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_THERMAL, by, text="THERMAL", fill=HUD_COLOR, font=font, anchor="w")
            canvas.create_text(sw * X_WHHOT, by, text="ACTIVE", fill=HUD_COLOR, font=font, anchor="w")
            
            canvas.create_text(sw * X_THERMAL, by + 18, text=f"COLOR: {current_color}", fill=HUD_COLOR, font=font, anchor="w")

            dot1_color = DOT_GREEN if thermal_on else DOT_RED
            dx1 = sw * X_DOT1
            canvas.create_oval(dx1 - DOT_R, by - DOT_R, dx1 + DOT_R, by + DOT_R, fill=dot1_color, outline="")

            dot2_color = DOT_GREEN if (thermal_on and filter_on) else DOT_RED
            dx2 = sw * X_DOT2
            canvas.create_oval(dx2 - DOT_R, by - DOT_R, dx2 + DOT_R, by + DOT_R, fill=dot2_color, outline="")

        root.after(33, render)

    render()

    threading.Thread(target=audio_manager_worker, daemon=True).start()

    # Fixed NameError listener configuration
    mouse_listener = mouse.Listener(on_move=on_mouse_move, on_click=on_mouse_click)
    mouse_listener.start()

    ocr_thread = threading.Thread(target=ocr_worker, daemon=True)
    ocr_thread.start()

    hk_thread = threading.Thread(target=hotkey_worker, daemon=True)
    hk_thread.start()

    def on_close():
        stop_event.set()
        pygame.mixer.quit()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        on_close()


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Overlay requires Windows layered window architectures.")
        sys.exit(1)
    main()