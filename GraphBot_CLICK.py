"""
GraphBot - Click Mode
Click on enemies to create graphs manually
"""

import tkinter as tk
from tkinter import ttk, messagebox
import mss
import numpy as np
import cv2
import win32api, win32gui
import pyperclip
import threading
import time

from window_capture import find_game_window, get_capture_field, load_capture_margins

game_window_name = 'Graphwar'
capture_margins = load_capture_margins()
field = None
clicks = []
mss_ = mss.mss()

def refresh_field():
    global field
    hwnd = find_game_window(game_window_name)
    if hwnd is None:
        return False
    field = get_capture_field(hwnd, capture_margins)
    return True

def get_screenshot():
    """Get current game screenshot"""
    if not refresh_field():
        return None
    screenshot = np.array(mss_.grab(field))
    return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

def field_to_game(fx, fy):
    """Convert field coords to game coords"""
    gx = -25 + fx * 50 / field["width"]
    gy = 15 - fy * 50 / field["width"]
    return round(gx, 5), round(gy, 5)

def direct_line(p1, p2):
    """Generate line formula - simple straight line"""
    x1, y1 = round(p1[0], 5), round(p1[1], 5)
    x2, y2 = round(p2[0], 5), round(p2[1], 5)
    
    # Handle vertical lines
    dx = x2 - x1
    if abs(dx) < 1e-12:
        dx = 0.001
        x2 = x1 + dx
    
    # Formula: dist * (abs(x - x1) - abs(x - x2))
    dist = round(-((y1 - y2) / 2) / dx, 5)
    formula = f"{dist}*(abs(x - {x1}) - abs(x - {x2}))".replace("- -", "+ ")
    return formula

def waypoints_to_formula(waypoints):
    """Convert waypoints to formula - just straight lines, no obstacles"""
    if len(waypoints) < 2:
        return ""
    
    parts = []
    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]
        formula = direct_line(p1, p2)
        parts.append(formula)
    
    # Combine all parts
    result = " + ".join(parts).replace("+ -", "- ")
    return result

def on_canvas_click(event):
    """Handle canvas click"""
    global clicks
    
    # Get click position relative to canvas
    x = event.x
    y = event.y
    
    # Canvas size
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()
    
    if x < 0 or y < 0 or x >= canvas_width or y >= canvas_height:
        return
    
    # Map to field coordinates
    scale_x = field["width"] / canvas_width
    scale_y = field["height"] / canvas_height
    
    field_x = x * scale_x
    field_y = y * scale_y
    
    clicks.append((field_x, field_y))
    
    # Convert to game coords
    gx, gy = field_to_game(field_x, field_y)
    
    status_label.config(text=f"Clicked {len(clicks)}: Game ({gx}, {gy})")
    
    # Redraw with click marker
    draw_screenshot()

def draw_screenshot():
    """Draw screenshot with click markers"""
    from PIL import Image, ImageTk, ImageDraw
    
    screenshot = get_screenshot()
    if screenshot is None:
        return
    
    # Convert BGR to RGB
    screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
    
    # Resize to fit canvas
    h, w = screenshot_rgb.shape[:2]
    scale = min(canvas.winfo_width() / w, canvas.winfo_height() / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    screenshot_rgb = cv2.resize(screenshot_rgb, (new_w, new_h))
    
    # Draw circles on clicks
    img = Image.fromarray(screenshot_rgb)
    draw = ImageDraw.Draw(img)
    
    for i, (fx, fy) in enumerate(clicks):
        # Scale click position to resized image
        cx = int(fx * scale)
        cy = int(fy * scale)
        
        # Draw circle
        r = 10
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(255, 0, 0), width=2)
        draw.text((cx+15, cy-5), str(i+1), fill=(255, 0, 0))
    
    # Convert back to PhotoImage
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    canvas.image = photo

def start_clicking():
    """Prepare to click on screen"""
    global clicks
    clicks = []
    status_label.config(text="🎯 Click on enemies in game window (numbered)", foreground="blue")
    
    clear_btn.config(state="normal")
    done_btn.config(state="normal")
    
    # Draw initial screenshot
    draw_screenshot()

def clear_clicks():
    """Clear all clicks"""
    global clicks
    clicks = []
    status_label.config(text="🎯 Cleared. Click enemies again.", foreground="blue")
    draw_screenshot()

def done_clicking():
    """Generate formula from clicks"""
    global clicks
    
    if len(clicks) < 2:
        messagebox.showwarning("Need More Clicks", "Click at least 2 enemies!")
        return
    
    # Convert to game coords
    game_waypoints = [field_to_game(fx, fy) for fx, fy in clicks]
    
    formula = waypoints_to_formula(game_waypoints)
    
    if not formula:
        messagebox.showerror("Error", "Could not generate formula!")
        return
    
    # Display formula
    formula_text.config(state="normal")
    formula_text.delete("1.0", tk.END)
    formula_text.insert("1.0", formula)
    formula_text.config(state="disabled")
    
    # Copy to clipboard
    pyperclip.copy(formula)
    
    status_label.config(text=f"✅ Formula copied! {len(clicks)} points", foreground="green")
    messagebox.showinfo("Success", "Formula copied to clipboard!\nPaste it in Graphwar.")
    
    clicks = []

# GUI
root = tk.Tk()
root.title("GraphBot - Click Mode")
root.geometry("800x700")

tk.Label(root, text="🎮 GraphBot Click Mode", font=("Arial", 16, "bold"), fg="darkblue").pack(pady=15)

status_label = tk.Label(root, text="Ready", font=("Arial", 10), foreground="gray")
status_label.pack(pady=5)

# Instructions
info_label = tk.Label(root, text=
    "1. Open Graphwar and start a round\n"
    "2. Click 'START CLICKING' below\n"
    "3. Click enemies in order - draws DIRECT LINES (ignores obstacles)\n"
    "4. Click 'DONE' to generate formula\n"
    "5. Formula auto-copies to clipboard",
    font=("Arial", 9), justify="left", wraplength=700)
info_label.pack(padx=20, pady=10)

# Canvas for game preview
canvas = tk.Canvas(root, bg="black", width=750, height=400, cursor="crosshair")
canvas.pack(pady=10, padx=20)
canvas.bind("<Button-1>", on_canvas_click)

# Buttons
btn_frame = tk.Frame(root)
btn_frame.pack(pady=10)

start_btn = tk.Button(btn_frame, text="▶ START CLICKING", command=start_clicking,
                      font=("Arial", 11, "bold"), bg="blue", fg="white", width=15)
start_btn.pack(side="left", padx=5)

clear_btn = tk.Button(btn_frame, text="🗑️ CLEAR", command=clear_clicks,
                      font=("Arial", 11, "bold"), bg="orange", fg="white", width=12, state="disabled")
clear_btn.pack(side="left", padx=5)

done_btn = tk.Button(btn_frame, text="✅ DONE", command=done_clicking,
                     font=("Arial", 11, "bold"), bg="green", fg="white", width=12, state="disabled")
done_btn.pack(side="left", padx=5)

# Formula display
tk.Label(root, text="Generated Formula:", font=("Arial", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 5))

formula_text = tk.Text(root, height=4, width=95, font=("Courier", 9), wrap="word",
                       state="disabled", bg="lightyellow")
formula_text.pack(padx=20, pady=5)

root.mainloop()
