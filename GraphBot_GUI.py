"""
GraphBot GUI - Simplified interface for automatic graph plotting in Graphwar
No calibration needed - just click START and it works!
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import cv2
import mss
import numpy as np
import win32api, win32con, win32gui
import pyperclip
import time
import sys

from window_capture import find_game_window, get_capture_field, load_capture_margins
from detection import find_all_obstacles, load_obstacles_params
from avoidance import field_obstacles_to_game, DEFAULT_CLEARANCE
from pathfinding import astar_game, build_enemy_chain_astar, draw_path_on_field

# Global variables
running = False
game_window_name = 'Graphwar'
capture_margins = load_capture_margins()
field = None
prev_text = ""

def is_key_pressed(key):
    return win32api.GetAsyncKeyState(key) & 0x8000 != 0

def detect_players(s_r):
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
        param2=10, minRadius=4, maxRadius=15)
    if detected_circles is not None:
        detected_circles = np.uint16(np.around(detected_circles))
        return detected_circles
    return None

def detect_black_circles(s_r):
    s_r = cv2.GaussianBlur(s_r, (3, 3), 0)
    lower_bound = 0
    upper_bound = 20
    mask = cv2.inRange(s_r, lower_bound, upper_bound)
    result = np.ones_like(s_r) * 255
    result[mask == 255] = 0
    result = cv2.GaussianBlur(result, (13, 13), 0)
    detected_circles = cv2.HoughCircles(result,
                    cv2.HOUGH_GRADIENT, 1, minDist=15, param1=50,
                param2=25, minRadius=1, maxRadius=200)
    if detected_circles is not None:
        detected_circles = np.uint16(np.around(detected_circles))
        return detected_circles
    return None

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

def draw_circles(circles, screenshot_r):
    for pt in circles[0,:]:
        a, b, r = pt[0], pt[1], pt[2]
        cv2.circle(screenshot_r, (a, b), r, (100, 0, 0), 2)
        cv2.circle(screenshot_r, (a, b), 1, (255, 0, 0), 3)
    return screenshot_r

def draw_obstacle_circles(screenshot_bgr, obstacles):
    for cx, cy, r in obstacles:
        cv2.circle(screenshot_bgr, (int(cx), int(cy)), int(r), (255, 0, 255), 1)
    return screenshot_bgr

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

def bot_loop():
    """Main bot loop running in background thread"""
    global prev_text, running
    
    mss_ = mss.mss()
    
    # Initial setup
    if not refresh_field():
        update_status("❌ Graphwar not found. Make sure it's open!", "red")
        running = False
        return
    
    update_status("✅ Ready! Processing...", "green")
    
    while running and not is_key_pressed(0x71):  # F2 to stop
        if not refresh_field():
            time.sleep(0.5)
            continue
        
        try:
            screenshot = np.array(mss_.grab(field))
            screenshot_r = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
            screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            
            players_cords = detect_players(screenshot_r)
            if players_cords is None:
                update_status("⚠️ No players detected. Make sure round is active.", "orange")
                time.sleep(1)
                continue
            
            obstacle_result = find_all_obstacles(screenshot_bgr, load_obstacles_params())
            obstacles_field = obstacle_result["obstacles"]
            obstacles_game = field_obstacles_to_game(obstacles_field, field["width"])
            
            good_guys, bad_guys, active_player = separate(players_cords.tolist())
            if not bad_guys:
                update_status("⚠️ No enemies detected.", "orange")
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
            update_status(f"❌ Error: {str(e)[:40]}", "red")
            time.sleep(1)

def start_bot():
    """Start the bot in background thread"""
    global running
    if not running:
        running = True
        start_btn.config(state="disabled", text="RUNNING...")
        stop_btn.config(state="normal")
        thread = threading.Thread(target=bot_loop, daemon=True)
        thread.start()

def stop_bot():
    """Stop the bot"""
    global running
    running = False
    start_btn.config(state="normal", text="▶ START")
    stop_btn.config(state="disabled")
    update_status("Stopped.", "gray")

def update_status(message, color):
    """Update status label safely"""
    root.after(0, lambda: status_label.config(text=message, foreground=color))

def update_formula(formula):
    """Update formula display safely"""
    root.after(0, lambda: formula_text.config(state="normal"))
    root.after(0, lambda: formula_text.delete("1.0", tk.END))
    root.after(0, lambda: formula_text.insert("1.0", formula))
    root.after(0, lambda: formula_text.config(state="disabled"))

# ============ GUI SETUP ============
root = tk.Tk()
root.title("GraphBot - Auto Graph Generator")
root.geometry("500x450")
root.resizable(False, False)

# Header
header = tk.Label(root, text="🎮 GraphBot Automatic", font=("Arial", 16, "bold"), fg="darkblue")
header.pack(pady=15)

# Status
status_label = tk.Label(root, text="⏸️ Ready to start", font=("Arial", 10), foreground="gray")
status_label.pack(pady=5)

# Buttons
btn_frame = tk.Frame(root)
btn_frame.pack(pady=15)

start_btn = tk.Button(btn_frame, text="▶ START", command=start_bot, 
                     font=("Arial", 12, "bold"), bg="green", fg="white", 
                     width=15, height=2, cursor="hand2")
start_btn.pack(side="left", padx=10)

stop_btn = tk.Button(btn_frame, text="⏹ STOP", command=stop_bot, 
                    font=("Arial", 12, "bold"), bg="red", fg="white", 
                    width=15, height=2, cursor="hand2", state="disabled")
stop_btn.pack(side="left", padx=10)

# Formula display
label_formula = tk.Label(root, text="Generated Formula:", font=("Arial", 9, "bold"))
label_formula.pack(anchor="w", padx=20, pady=(15, 5))

formula_text = tk.Text(root, height=8, width=58, font=("Courier", 9), 
                       wrap="word", state="disabled", bg="lightyellow")
formula_text.pack(padx=20, pady=5)

# Info
info_text = tk.Label(root, text=
    "1. Open Graphwar\n"
    "2. Start a round\n"
    "3. Click START button\n"
    "4. Formula auto-copies to clipboard\n"
    "5. Paste in Graphwar\n\n"
    "Press F2 to stop manually",
    font=("Arial", 8), justify="left", fg="darkgray")
info_text.pack(pady=10, anchor="w", padx=20)

root.mainloop()
