"""
GraphBot - Simple Automatic Version
Dead simple. No complex setup. Just works.
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
import numpy as np
import cv2

from window_capture import find_game_window, get_capture_field, load_capture_margins
from avoidance import field_obstacles_to_game, DEFAULT_CLEARANCE
from pathfinding import build_enemy_chain_astar

# Global state
running = False
setup_done = False
game_window_name = 'Graphwar'
capture_margins = load_capture_margins()
field = None
prev_text = ""

CONFIG_FILE = "graphbot_settings.json"

def save_setup():
    """Mark setup as complete"""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"setup_done": True}, f)
    except:
        pass

def load_setup():
    """Load setup status"""
    global setup_done
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                setup_done = data.get("setup_done", False)
    except:
        setup_done = False

def is_key_pressed(key):
    return win32api.GetAsyncKeyState(key) & 0x8000 != 0

def detect_players(img):
    """Detect player circles"""
    try:
        lower, upper = 50, 250
        mask1 = cv2.inRange(img, lower, 169)
        mask2 = cv2.inRange(img, 171, upper)
        mask = cv2.bitwise_or(mask1, mask2)
        result = np.ones_like(img) * 255
        result[mask == 255] = 0
        result = cv2.GaussianBlur(result, (23, 23), 0)
        circles = cv2.HoughCircles(result, cv2.HOUGH_GRADIENT, 1, minDist=10, 
                                   param1=150, param2=10, minRadius=4, maxRadius=15)
        return np.uint16(np.around(circles)) if circles is not None else None
    except:
        return None

def detect_obstacles(img):
    """Detect black circles"""
    try:
        img = cv2.GaussianBlur(img, (3, 3), 0)
        mask = cv2.inRange(img, 0, 20)
        result = np.ones_like(img) * 255
        result[mask == 255] = 0
        result = cv2.GaussianBlur(result, (13, 13), 0)
        circles = cv2.HoughCircles(result, cv2.HOUGH_GRADIENT, 1, minDist=15,
                                   param1=50, param2=25, minRadius=1, maxRadius=200)
        return np.uint16(np.around(circles)) if circles is not None else None
    except:
        return None

def grayscale_from_rgb(img):
    """Convert RGB to grayscale"""
    r, g, b = img[:,:,0], img[:,:,1], img[:,:,2]
    return (r.astype(float)*0.299 + g.astype(float)*0.587 + b.astype(float)*0.114).astype(np.uint8)

def separate_players(players):
    """Separate good/bad/active players"""
    active = players[0][0]
    good, bad = [], []
    for p in players[0]:
        if p[2] > active[2]:
            active = p
        if p[0] > field['width'] / 2:
            bad.append(p[:2])
        else:
            if p[2] > active[2]:
                active = p
            good.append(p[:2])
    return good, bad, active[:2]

def field_to_game(fx, fy):
    """Convert field coords to game coords"""
    gx = -25 + fx * 50 / field["width"]
    gy = 15 - fy * 50 / field["width"]
    return round(gx, 5), round(gy, 5)

def to_game_coords(coords):
    """Convert list of field coords to game coords"""
    return [list(field_to_game(c[0], c[1])) for c in coords]

def direct_line(p1, p2):
    """Generate line formula"""
    x1, y1 = round(p1[0], 5), round(p1[1], 5)
    x2, y2 = round(p2[0], 5), round(p2[1], 5)
    dx = x2 - x1
    if abs(dx) < 1e-12:
        dx = 0.001 if y1 != y2 else 0.001
        x2 = x1 + dx
    dist = round(-((y1 - y2) / 2) / dx, 5)
    return f"{dist}*(abs(x - {x1}) - abs(x - {x2}))".replace("- -", "+ ")

def waypoints_to_formula(waypoints):
    """Convert waypoints to formula"""
    parts = [direct_line(waypoints[i], waypoints[i+1]) for i in range(len(waypoints)-1)]
    return " + ".join(parts).replace("+ -", "- ")

def refresh_field():
    """Refresh field capture region"""
    global field
    hwnd = find_game_window(game_window_name)
    if hwnd is None:
        return False
    field = get_capture_field(hwnd, capture_margins)
    return True

def update_status(msg, color):
    """Update status label"""
    root.after(0, lambda: status_label.config(text=msg, foreground=color))

def update_formula(formula):
    """Update formula display"""
    root.after(0, lambda: formula_text.config(state="normal"))
    root.after(0, lambda: formula_text.delete("1.0", tk.END))
    root.after(0, lambda: formula_text.insert("1.0", formula))
    root.after(0, lambda: formula_text.config(state="disabled"))

def show_setup():
    """Show setup dialog"""
    global setup_done
    
    setup_win = tk.Toplevel(root)
    setup_win.title("Setup")
    setup_win.geometry("400x300")
    setup_win.resizable(False, False)
    
    tk.Label(setup_win, text="✅ GraphBot Setup", font=("Arial", 14, "bold")).pack(pady=20)
    
    info = tk.Label(setup_win, text=
        "Instructions:\n\n"
        "1. Make sure Graphwar is OPEN\n"
        "2. Start a game round\n"
        "3. Click 'Confirm Setup' below\n\n"
        "GraphBot will auto-detect everything.\n"
        "You only do this ONCE.",
        font=("Arial", 10), justify="left", wraplength=350)
    info.pack(padx=20, pady=10)
    
    def confirm():
        global setup_done
        if not refresh_field():
            messagebox.showerror("Error", "Graphwar not found!")
            return
        setup_done = True
        save_setup()
        setup_win.destroy()
        setup_btn.config(state="disabled", text="✅ Setup Done")
        messagebox.showinfo("Success", "Setup complete!")
    
    tk.Button(setup_win, text="✅ Confirm Setup", command=confirm,
              font=("Arial", 12, "bold"), bg="green", fg="white", width=25, height=2).pack(pady=20)
    
    setup_win.grab_set()
    root.wait_window(setup_win)

def bot_loop():
    """Main bot loop"""
    global prev_text, running
    
    if not setup_done:
        update_status("❌ Setup not done!", "red")
        running = False
        return
    
    mss_ = mss.mss()
    if not refresh_field():
        update_status("❌ Graphwar not found!", "red")
        running = False
        return
    
    update_status("✅ Running...", "green")
    
    while running and not is_key_pressed(0x71):  # F2 to stop
        if not refresh_field():
            time.sleep(0.5)
            continue
        
        try:
            screenshot = np.array(mss_.grab(field))
            gray = grayscale_from_rgb(screenshot)
            
            players = detect_players(gray)
            if players is None:
                update_status("⚠️ No players detected", "orange")
                time.sleep(1)
                continue
            
            obstacles_data = detect_obstacles(gray)
            obstacles = [(o[0], o[1], o[2]) for o in obstacles_data[0]] if obstacles_data is not None else []
            obstacles_game = field_obstacles_to_game(obstacles, field["width"])
            
            good, bad, active = separate_players(players.tolist())
            if not bad:
                update_status("⚠️ No enemies", "orange")
                time.sleep(1)
                continue
            
            bad_norm = sorted(to_game_coords(bad), key=lambda x: x[0])
            active_norm = field_to_game(active[0], active[1])
            
            waypoints, hit, skipped = build_enemy_chain_astar(bad_norm, obstacles_game, clearance=0.5)
            
            if len(waypoints) < 2 and bad_norm:
                waypoints = [list(p) for p in bad_norm]
            
            formula = waypoints_to_formula(waypoints)
            
            if formula and formula != prev_text:
                pyperclip.copy(formula)
                prev_text = formula
                update_status(f"✅ Copied! ({len(bad_norm)} enemies)", "green")
                update_formula(formula)
            
            time.sleep(1)
            
        except Exception as e:
            update_status(f"⚠️ Error: {str(e)[:30]}", "orange")
            time.sleep(1)

def start():
    """Start bot"""
    global running, setup_done
    if not setup_done:
        messagebox.showwarning("Setup Required", "Click SETUP first!")
        return
    if not running:
        running = True
        start_btn.config(state="disabled", text="RUNNING...")
        stop_btn.config(state="normal")
        thread = threading.Thread(target=bot_loop, daemon=True)
        thread.start()

def stop():
    """Stop bot"""
    global running
    running = False
    start_btn.config(state="normal", text="▶ START")
    stop_btn.config(state="disabled")
    update_status("Stopped", "gray")

# Load config at startup
load_setup()

# GUI
root = tk.Tk()
root.title("GraphBot")
root.geometry("500x450")
root.resizable(False, False)

tk.Label(root, text="🎮 GraphBot", font=("Arial", 16, "bold"), fg="darkblue").pack(pady=15)

status_label = tk.Label(root, text="Ready", font=("Arial", 10), foreground="gray")
status_label.pack(pady=5)

# Buttons
btn_frame = tk.Frame(root)
btn_frame.pack(pady=15)

setup_btn = tk.Button(btn_frame, text="⚙️ SETUP", command=show_setup,
                      font=("Arial", 11, "bold"), bg="purple", fg="white", width=12)
setup_btn.pack(side="left", padx=5)
if setup_done:
    setup_btn.config(state="disabled", text="✅ Setup Done")

start_btn = tk.Button(btn_frame, text="▶ START", command=start,
                      font=("Arial", 11, "bold"), bg="green", fg="white", width=12)
start_btn.pack(side="left", padx=5)

stop_btn = tk.Button(btn_frame, text="⏹ STOP", command=stop,
                     font=("Arial", 11, "bold"), bg="red", fg="white", width=12, state="disabled")
stop_btn.pack(side="left", padx=5)

tk.Label(root, text="Formula:", font=("Arial", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 5))

formula_text = tk.Text(root, height=7, width=62, font=("Courier", 8), wrap="word",
                       state="disabled", bg="lightyellow")
formula_text.pack(padx=20, pady=5)

info_label = tk.Label(root, text="1. Click SETUP once\n2. Click START when in game\n3. Formula auto-copies",
                      font=("Arial", 8), fg="gray")
info_label.pack(pady=10)

root.mainloop()
