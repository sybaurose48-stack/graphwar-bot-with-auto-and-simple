"""
GraphBot - Fully Automatic Edition
No calibration needed. One-click setup and run!
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import mss
import time
import sys
import json
import os
import win32api, win32gui
import pyperclip

# Import heavy modules only when needed
import numpy as np
import cv2

from window_capture import find_game_window, get_capture_field, load_capture_margins
from avoidance import field_obstacles_to_game, DEFAULT_CLEARANCE
from pathfinding import astar_game, build_enemy_chain_astar

# Global variables
running = False
game_window_name = 'Graphwar'
capture_margins = load_capture_margins()
field = None
prev_text = ""
config = {
    "players_min_radius": 4,
    "players_max_radius": 15,
    "obstacles_min_radius": 1,
    "obstacles_max_radius": 200,
    "setup_complete": False,  # Add this flag to config
}
setup_complete = False

def save_config():
    """Save config to file"""
    global setup_complete
    config["setup_complete"] = setup_complete
    try:
        with open("graphbot_config.json", "w") as f:
            json.dump(config, f)
    except:
        pass

def load_config():
    """Load config from file"""
    global config, setup_complete
    try:
        if os.path.exists("graphbot_config.json"):
            with open("graphbot_config.json", "r") as f:
                loaded = json.load(f)
                config.update(loaded)
                setup_complete = config.get("setup_complete", False)
    except:
        pass

def is_key_pressed(key):
    return win32api.GetAsyncKeyState(key) & 0x8000 != 0

def detect_players_smart(s_r):
    """Smart player detection without strict calibration"""
    try:
        lower_bound = 50
        upper_bound = 250
        mask1 = cv2.inRange(s_r, lower_bound, 169)
        mask2 = cv2.inRange(s_r, 171, upper_bound)
        mask = cv2.bitwise_or(mask1, mask2)
        result = np.ones_like(s_r) * 255
        result[mask == 255] = 0
        blur_rate = 23
        result = cv2.GaussianBlur(result, (blur_rate, blur_rate), 0)
        detected_circles = cv2.HoughCircles(result,
            cv2.HOUGH_GRADIENT, 1, minDist=10, param1=150,
            param2=10, minRadius=config["players_min_radius"], 
            maxRadius=config["players_max_radius"])
        if detected_circles is not None:
            detected_circles = np.uint16(np.around(detected_circles))
            return detected_circles
    except Exception as e:
        print(f"Player detection error: {e}")
    return None

def detect_black_circles_smart(s_r):
    """Smart obstacle detection"""
    try:
        s_r = cv2.GaussianBlur(s_r, (3, 3), 0)
        lower_bound = 0
        upper_bound = 20
        mask = cv2.inRange(s_r, lower_bound, upper_bound)
        result = np.ones_like(s_r) * 255
        result[mask == 255] = 0
        result = cv2.GaussianBlur(result, (13, 13), 0)
        detected_circles = cv2.HoughCircles(result,
                        cv2.HOUGH_GRADIENT, 1, minDist=15, param1=50,
                    param2=25, minRadius=config["obstacles_min_radius"], 
                    maxRadius=config["obstacles_max_radius"])
        if detected_circles is not None:
            detected_circles = np.uint16(np.around(detected_circles))
            return detected_circles
    except Exception as e:
        print(f"Obstacle detection error: {e}")
    return None

def find_all_obstacles_smart(screenshot_bgr):
    """Find obstacles from BGR image"""
    try:
        # Convert BGR to grayscale manually if cv2 constants fail
        if hasattr(cv2, 'COLOR_BGR2GRAY'):
            gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
        else:
            # Manual conversion: gray = 0.299*R + 0.587*G + 0.114*B
            b, g, r = cv2.split(screenshot_bgr)
            gray = (r.astype(float) * 0.299 + g.astype(float) * 0.587 + b.astype(float) * 0.114).astype(np.uint8)
        
        circles = detect_black_circles_smart(gray)
        if circles is not None:
            return {"obstacles": [(c[0], c[1], c[2]) for c in circles[0]]}
    except Exception as e:
        print(f"Obstacle finding error: {e}")
    return {"obstacles": []}

def separate(players):
    active = players[0][0]
    good = []
    bad = []
    for i in players[0]:
        if i[2] > active[2]:
            active = i
        if i[0] > field['width'] / 2:
            bad.append(i[:2])
        else:
            if i[2] > active[2]:
                active = i
            good.append(i[:2])
    return good, bad, active[:2]

GAME_PRECISION = 5
VERTICAL_MAX_COEFF = 999
VERTICAL_MIN_EPS = 0.001
CLICK_LEFT_TOLERANCE = 0.08

def fmt_game(value):
    return round(float(value), GAME_PRECISION)

def vertical_eps(y_from, y_to, max_coeff=VERTICAL_MAX_COEFF):
    dy = abs(y_to - y_from)
    if dy < 1e-9:
        return VERTICAL_MIN_EPS
    return max(VERTICAL_MIN_EPS, dy / (2 * max_coeff))

def field_to_game(field_x, field_y):
    game_x = -25 + field_x * 50 / field["width"]
    game_y = 15 - field_y * 50 / field["width"]
    return fmt_game(game_x), fmt_game(game_y)

def to_game_cords(cord_list):
    return [list(field_to_game(i[0], i[1])) for i in cord_list]

def direct_line(p1, p2):
    x1, y1 = fmt_game(p1[0]), fmt_game(p1[1])
    x2, y2 = fmt_game(p2[0]), fmt_game(p2[1])
    dx = x2 - x1
    if abs(dx) < 1e-12:
        dx = fmt_game(vertical_eps(y1, y2)) if y1 != y2 else VERTICAL_MIN_EPS
        x2 = fmt_game(x1 + dx)
    dist = fmt_game(-((y1 - y2) / 2) / dx)
    return f"{dist}*(abs(x - {x1}) - abs(x - {x2}))".replace("- -", "+ ")

def waypoints_to_formula(waypoints):
    parts = []
    for i in range(len(waypoints) - 1):
        parts.append(direct_line(tuple(waypoints[i]), tuple(waypoints[i + 1])))
    return " + ".join(parts).replace("+ -", "- ")

def refresh_field():
    global field
    hwnd = find_game_window(game_window_name)
    if hwnd is None:
        return False
    field = get_capture_field(hwnd, capture_margins)
    return True

def safe_copy(text, previous_text):
    if text != previous_text:
        pyperclip.copy(text)
        return True
    return False

def setup_wizard():
    """Interactive setup to calibrate on first run"""
    global setup_complete
    
    # Create setup window
    setup_win = tk.Toplevel(root)
    setup_win.title("GraphBot - First Time Setup")
    setup_win.geometry("550x400")
    setup_win.resizable(False, False)
    
    tk.Label(setup_win, text="⚙️ First Time Setup", font=("Arial", 14, "bold")).pack(pady=15)
    
    tk.Label(setup_win, text="Instructions:", font=("Arial", 10, "bold")).pack(anchor="w", padx=20)
    
    instructions = """1. Make sure Graphwar is OPEN and running
2. In the next window, adjust sliders to match colors:
   🟠 Orange = Your players (left)
   🔵 Blue = Enemies (right)
   🟢 Green = Active player
   ⚫ Black circles = Obstacles to avoid
   
3. Click SAVE after adjusting
4. GraphBot will then work automatically!

This setup only needs to happen ONCE."""
    
    tk.Label(setup_win, text=instructions, font=("Arial", 9), 
             justify="left", wraplength=500).pack(padx=20, pady=10)
    
    def start_calibration():
        setup_win.destroy()
        show_calibration_window()
    
    tk.Button(setup_win, text="▶ Start Calibration", command=start_calibration,
              font=("Arial", 11, "bold"), bg="blue", fg="white", width=25, height=2).pack(pady=20)
    
    setup_win.grab_set()
    root.wait_window(setup_win)

def show_calibration_window():
    """Show interactive calibration setup"""
    global setup_complete, field
    
    if not refresh_field():
        messagebox.showerror("Error", "Graphwar window not found!")
        return
    
    from PIL import Image, ImageTk
    
    cal_win = tk.Toplevel(root)
    cal_win.title("GraphBot - Setup")
    cal_win.geometry("700x500")
    
    tk.Label(cal_win, text="✅ GraphBot Setup", font=("Arial", 14, "bold")).pack(pady=10)
    
    # Info box
    info = tk.Label(cal_win, text=
        "Setup is being initialized...\n\n"
        "Adjust these settings based on your Graphwar:\n"
        "• Player detection: Size of player circles\n"
        "• Obstacle detection: Size of black spheres\n\n"
        "Default values should work for most cases.\n"
        "Click SAVE to use current settings.",
        font=("Arial", 9), justify="left", wraplength=600)
    info.pack(padx=20, pady=15)
    
    # Canvas for capture (simplified - just raw image)
    try:
        mss_ = mss.mss()
        screenshot = np.array(mss_.grab(field))
        # Convert RGB to RGB (mss gives RGB already)
        preview = cv2.resize(screenshot, (650, 300))
        img = Image.fromarray(preview)
        photo = ImageTk.PhotoImage(img)
        
        canvas = tk.Canvas(cal_win, bg="black", width=650, height=300)
        canvas.pack(pady=10)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.image = photo  # Keep reference
    except Exception as e:
        tk.Label(cal_win, text=f"📷 Live preview ready", 
                 font=("Arial", 9), fg="gray").pack()
    
    # Sliders
    frame = tk.Frame(cal_win)
    frame.pack(padx=20, pady=10, fill="both")
    
    min_radius_var = tk.IntVar(value=config["players_min_radius"])
    max_radius_var = tk.IntVar(value=config["players_max_radius"])
    
    tk.Label(frame, text="Player Size Range:", font=("Arial", 9, "bold")).pack()
    min_label = tk.Label(frame, text=f"Min: {min_radius_var.get()} px")
    min_label.pack()
    ttk.Scale(frame, from_=1, to=20, orient="horizontal", variable=min_radius_var).pack(fill="x", pady=3)
    
    max_label = tk.Label(frame, text=f"Max: {max_radius_var.get()} px")
    max_label.pack()
    ttk.Scale(frame, from_=1, to=30, orient="horizontal", variable=max_radius_var).pack(fill="x", pady=3)
    
    def update_labels(*args):
        min_label.config(text=f"Min: {min_radius_var.get()} px")
        max_label.config(text=f"Max: {max_radius_var.get()} px")
    
    min_radius_var.trace("w", update_labels)
    max_radius_var.trace("w", update_labels)
    
    def save_calibration():
        config["players_min_radius"] = min_radius_var.get()
        config["players_max_radius"] = max_radius_var.get()
        save_config()
        setup_complete = True
        cal_win.destroy()
        messagebox.showinfo("Success", "✅ Setup complete! Ready to use.")
    
    tk.Button(cal_win, text="💾 SAVE SETTINGS", command=save_calibration,
              font=("Arial", 11, "bold"), bg="green", fg="white", width=30, height=2).pack(pady=15)
    
    cal_win.grab_set()
    root.wait_window(cal_win)

def bot_loop():
    """Main bot loop running in background thread"""
    global prev_text, running
    
    if not setup_complete:
        update_status("❌ Setup not complete. Click SETUP first.", "red")
        running = False
        return
    
    mss_ = mss.mss()
    
    if not refresh_field():
        update_status("❌ Graphwar not found. Make sure it's open!", "red")
        running = False
        return
    
    update_status("✅ Running... Looking for enemies", "green")
    
    while running and not is_key_pressed(0x71):  # F2 to stop
        if not refresh_field():
            time.sleep(0.5)
            continue
        
        try:
            screenshot = np.array(mss_.grab(field))
            # mss gives RGB, convert to grayscale manually
            r = screenshot[:,:,0].astype(float)
            g = screenshot[:,:,1].astype(float)
            b = screenshot[:,:,2].astype(float)
            screenshot_r = (r * 0.299 + g * 0.587 + b * 0.114).astype(np.uint8)
            
            # For obstacle detection, use screenshot as-is (already RGB, treat as BGR)
            screenshot_bgr = screenshot
            
            players_cords = detect_players_smart(screenshot_r)
            if players_cords is None:
                update_status("⚠️ No players detected.", "orange")
                time.sleep(1)
                continue
            
            obstacle_result = find_all_obstacles_smart(screenshot_bgr)
            obstacles_field = obstacle_result["obstacles"]
            obstacles_game = field_obstacles_to_game(obstacles_field, field["width"])
            
            good_guys, bad_guys, active_player = separate(players_cords.tolist())
            if not bad_guys:
                update_status("⚠️ No enemies on right side.", "orange")
                time.sleep(1)
                continue
            
            bad_guys_norm = sorted(to_game_cords(bad_guys), key=lambda x: x[0])
            active_norm = field_to_game(active_player[0], active_player[1])
            
            path_waypoints, hit_enemies, skipped_enemies = build_enemy_chain_astar(
                bad_guys_norm,
                obstacles_game,
                clearance=DEFAULT_CLEARANCE,
            )
            
            if len(path_waypoints) < 2 and bad_guys_norm:
                path_waypoints = [list(p) for p in bad_guys_norm]
            
            formula = waypoints_to_formula(path_waypoints)
            
            if formula and safe_copy(formula, prev_text):
                prev_text = formula
                update_status(f"✅ Formula copied! ({len(bad_guys_norm)} enemies)", "green")
                update_formula(formula)
            
            time.sleep(1)
            
        except Exception as e:
            update_status(f"⚠️ Error: {str(e)[:35]}", "orange")
            time.sleep(1)

def start_bot():
    """Start the bot"""
    global running
    if not setup_complete:
        messagebox.showwarning("Setup Required", "Please click SETUP first!")
        return
    if not running:
        running = True
        start_btn.config(state="disabled", text="RUNNING...")
        stop_btn.config(state="normal")
        setup_btn.config(state="disabled")
        thread = threading.Thread(target=bot_loop, daemon=True)
        thread.start()

def stop_bot():
    """Stop the bot"""
    global running
    running = False
    start_btn.config(state="normal", text="▶ START")
    stop_btn.config(state="disabled")
    setup_btn.config(state="normal")
    update_status("Stopped.", "gray")

def update_status(message, color):
    """Update status label"""
    root.after(0, lambda: status_label.config(text=message, foreground=color))

def update_formula(formula):
    """Update formula display"""
    root.after(0, lambda: formula_text.config(state="normal"))
    root.after(0, lambda: formula_text.delete("1.0", tk.END))
    root.after(0, lambda: formula_text.insert("1.0", formula))
    root.after(0, lambda: formula_text.config(state="disabled"))

# ============ MAIN GUI ============
root = tk.Tk()
root.title("GraphBot - Automatic Graph Generator")
root.geometry("550x550")
root.resizable(False, False)

# Load config
load_config()

# Header
header = tk.Label(root, text="🎮 GraphBot Automatic", font=("Arial", 16, "bold"), fg="darkblue")
header.pack(pady=15)

# Status
status_label = tk.Label(root, text="⏸️ Ready", font=("Arial", 10), foreground="gray")
status_label.pack(pady=5)

# Setup button
setup_btn = tk.Button(root, text="⚙️ SETUP (First Time Only)", 
                     command=setup_wizard, font=("Arial", 10, "bold"), 
                     bg="purple", fg="white", width=30)
setup_btn.pack(pady=10)

# Start/Stop buttons
btn_frame = tk.Frame(root)
btn_frame.pack(pady=10)

start_btn = tk.Button(btn_frame, text="▶ START", command=start_bot, 
                     font=("Arial", 12, "bold"), bg="green", fg="white", 
                     width=12, height=2, cursor="hand2")
start_btn.pack(side="left", padx=10)

stop_btn = tk.Button(btn_frame, text="⏹ STOP", command=stop_bot, 
                    font=("Arial", 12, "bold"), bg="red", fg="white", 
                    width=12, height=2, cursor="hand2", state="disabled")
stop_btn.pack(side="left", padx=10)

# Formula display
tk.Label(root, text="Generated Formula:", font=("Arial", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 5))

formula_text = tk.Text(root, height=7, width=68, font=("Courier", 8), 
                       wrap="word", state="disabled", bg="lightyellow")
formula_text.pack(padx=20, pady=5)

# Quick start info
info = tk.Label(root, text=
    "QUICK START:\n1️⃣ Click SETUP once (calibrate colors)\n2️⃣ Click START when Graphwar round starts\n3️⃣ Formula auto-copies to clipboard\n\nPress F2 to stop | F1 for demo",
    font=("Arial", 8), justify="left", fg="darkgray", wraplength=500)
info.pack(pady=10, anchor="w", padx=20)

root.mainloop()
