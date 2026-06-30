"""
GraphBot - Click Mode - ACCURATE VERSION
Click enemies, see exact coordinates, generate perfect formulas
"""

import tkinter as tk
from tkinter import ttk, messagebox
import mss
import numpy as np
import cv2
import win32api, win32gui
import pyperclip

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

def field_to_game_precise(fx, fy):
    """Convert field pixel coords to game coords - MORE PRECISE"""
    # Field dimensions
    fw = field["width"]
    fh = field["height"]
    
    # Game coordinate system: -25 to 25 (x), -15 to 15 (y)
    # Field center is at (fw/2, fh/2)
    
    # Calculate relative position from center
    rel_x = (fx - fw/2) / fw
    rel_y = (fy - fh/2) / fh
    
    # Convert to game coords (using full width for both axes)
    gx = rel_x * 50  # -25 to 25
    gy = -rel_y * 50  # -15 to 15 (inverted because Y increases downward in pixels)
    
    # Keep more precision initially
    return gx, gy

def fmt_coord(val):
    """Format coordinate to 6 decimal places"""
    return round(val, 6)

def direct_line_accurate(p1, p2):
    """Generate line formula - ACCURATE VERSION"""
    x1 = fmt_coord(p1[0])
    y1 = fmt_coord(p1[1])
    x2 = fmt_coord(p2[0])
    y2 = fmt_coord(p2[1])
    
    dx = x2 - x1
    dy = y2 - y1
    
    # Handle near-vertical lines
    if abs(dx) < 1e-6:
        dx = 0.0001
        x2 = fmt_coord(x1 + dx)
    
    # V-shaped formula: dist * (abs(x - x1) - abs(x - x2))
    # Where dist represents the steepness
    dist = fmt_coord(-((y1 - y2) / 2) / dx)
    
    x1_str = f"{x1:g}"  # Remove trailing zeros
    x2_str = f"{x2:g}"
    dist_str = f"{dist:g}"
    
    formula = f"{dist_str}*(abs(x - {x1_str}) - abs(x - {x2_str}))"
    formula = formula.replace("- -", "+ ")
    return formula

def waypoints_to_formula_accurate(waypoints):
    """Convert waypoints to formula"""
    if len(waypoints) < 2:
        return ""
    
    parts = []
    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]
        formula = direct_line_accurate(p1, p2)
        parts.append(formula)
    
    result = " + ".join(parts).replace("+ -", "- ")
    return result

def on_canvas_click(event):
    """Handle canvas click - GET EXACT POSITION"""
    global clicks
    
    # Get click position relative to canvas
    canvas_x = event.x
    canvas_y = event.y
    
    # Canvas size
    canvas_w = canvas.winfo_width()
    canvas_h = canvas.winfo_height()
    
    if canvas_x < 0 or canvas_y < 0 or canvas_x >= canvas_w or canvas_y >= canvas_h:
        return
    
    # Map to field coordinates (the canvas shows the field as-is)
    field_x = canvas_x * (field["width"] / canvas_w)
    field_y = canvas_y * (field["height"] / canvas_h)
    
    # Convert to game coordinates
    gx, gy = field_to_game_precise(field_x, field_y)
    gx = fmt_coord(gx)
    gy = fmt_coord(gy)
    
    clicks.append((gx, gy))
    
    # Update display
    status_label.config(text=f"✓ Click {len(clicks)}: ({gx:.2f}, {gy:.2f})", foreground="green")
    
    # Show clicks list
    update_clicks_list()
    
    # Auto-draw formula if 2+ clicks
    if len(clicks) >= 2:
        formula = waypoints_to_formula_accurate(clicks)
        update_formula_display(formula)

def update_clicks_list():
    """Show all clicks with coordinates"""
    clicks_list.config(state="normal")
    clicks_list.delete("1.0", tk.END)
    
    for i, (gx, gy) in enumerate(clicks, 1):
        clicks_list.insert(tk.END, f"{i}. ({gx:.4f}, {gy:.4f})\n")
    
    clicks_list.config(state="disabled")

def update_formula_display(formula):
    """Update formula display"""
    formula_text.config(state="normal")
    formula_text.delete("1.0", tk.END)
    formula_text.insert("1.0", formula)
    formula_text.config(state="disabled")

def start_clicking():
    """Prepare to click"""
    global clicks
    clicks = []
    status_label.config(text="🎯 Click enemies in order (at least 2)", foreground="blue")
    update_clicks_list()
    update_formula_display("")
    
    clear_btn.config(state="normal")
    undo_btn.config(state="normal")
    verify_btn.config(state="normal")
    done_btn.config(state="normal")
    
    # Draw screenshot
    draw_screenshot()

def draw_screenshot():
    """Display game screenshot"""
    from PIL import Image, ImageTk, ImageDraw
    
    screenshot = get_screenshot()
    if screenshot is None:
        status_label.config(text="❌ Graphwar not found", foreground="red")
        return
    
    # Convert BGR to RGB
    screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
    
    # Resize to fit canvas
    canvas_w = canvas.winfo_width()
    canvas_h = canvas.winfo_height()
    
    h, w = screenshot_rgb.shape[:2]
    screenshot_rgb = cv2.resize(screenshot_rgb, (canvas_w, canvas_h))
    
    # Draw click markers and path
    img = Image.fromarray(screenshot_rgb)
    draw = ImageDraw.Draw(img)
    
    # Draw connecting lines FIRST (so they appear behind circles)
    if len(clicks) > 1:
        for i in range(len(clicks) - 1):
            gx1, gy1 = clicks[i]
            gx2, gy2 = clicks[i + 1]
            
            fx1 = (gx1 + 25) / 50 * field["width"]
            fy1 = (15 - gy1) / 50 * field["height"]
            fx2 = (gx2 + 25) / 50 * field["width"]
            fy2 = (15 - gy2) / 50 * field["height"]
            
            cx1 = int(fx1 * canvas_w / field["width"])
            cy1 = int(fy1 * canvas_h / field["height"])
            cx2 = int(fx2 * canvas_w / field["width"])
            cy2 = int(fy2 * canvas_h / field["height"])
            
            # Draw bright red/blue line (thick for visibility)
            draw.line([(cx1, cy1), (cx2, cy2)], fill=(0, 0, 255), width=4)
    
    # Draw click markers on top
    for i, (gx, gy) in enumerate(clicks, 1):
        # Convert game coords back to field coords for display
        fx = (gx + 25) / 50 * field["width"]
        fy = (15 - gy) / 50 * field["height"]
        
        # Scale to canvas
        cx = int(fx * canvas_w / field["width"])
        cy = int(fy * canvas_h / field["height"])
        
        # Draw green crosshair
        r = 15
        draw.line([(cx-r, cy), (cx+r, cy)], fill=(0, 255, 0), width=2)
        draw.line([(cx, cy-r), (cx, cy+r)], fill=(0, 255, 0), width=2)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(0, 255, 0), width=2)
        draw.text((cx+20, cy-5), str(i), fill=(0, 255, 0))
    
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    canvas.image = photo

def clear_clicks():
    """Clear all clicks"""
    global clicks
    clicks = []
    status_label.config(text="🎯 Cleared. Click again.", foreground="blue")
    update_clicks_list()
    update_formula_display("")
    draw_screenshot()

def undo_click():
    """Undo last click"""
    global clicks
    if clicks:
        clicks.pop()
        status_label.config(text="↶ Undid last click", foreground="orange")
        update_clicks_list()
        if len(clicks) >= 2:
            formula = waypoints_to_formula_accurate(clicks)
            update_formula_display(formula)
        else:
            update_formula_display("")
        draw_screenshot()

def verify_clicks():
    """Verify all clicks are in valid range"""
    if len(clicks) < 2:
        messagebox.showwarning("Not Ready", "Need at least 2 clicks to verify!")
        return
    
    valid = True
    msg = "✅ All coordinates VALID:\n\n"
    
    for i, (gx, gy) in enumerate(clicks, 1):
        x_ok = -25 <= gx <= 25
        y_ok = -15 <= gy <= 15
        status = "✓" if (x_ok and y_ok) else "✗"
        
        msg += f"{status} Click {i}: X={gx:.4f}, Y={gy:.4f}\n"
        
        if not (x_ok and y_ok):
            valid = False
    
    if valid:
        status_label.config(text="✅ All coordinates VALID!", foreground="green")
        messagebox.showinfo("Verification", msg)
    else:
        status_label.config(text="❌ Some coordinates INVALID!", foreground="red")
        messagebox.showerror("Verification Failed", msg)

def done_clicking():
    """Generate and copy formula"""
    global clicks
    
    if len(clicks) < 2:
        messagebox.showwarning("Need More Clicks", "Click at least 2 enemies!")
        return
    
    formula = waypoints_to_formula_accurate(clicks)
    
    if not formula:
        messagebox.showerror("Error", "Could not generate formula!")
        return
    
    # Copy to clipboard
    pyperclip.copy(formula)
    
    status_label.config(text=f"✅ Formula copied! {len(clicks)} points", foreground="green")
    messagebox.showinfo("Success", "Formula copied to clipboard!\nPaste it in Graphwar now.")
    
    clicks = []
    update_clicks_list()

# GUI
root = tk.Tk()
root.title("GraphBot - Accurate Click Mode")
root.geometry("1000x800")

tk.Label(root, text="🎮 GraphBot Click Mode (ACCURATE)", font=("Arial", 16, "bold"), fg="darkblue").pack(pady=15)

status_label = tk.Label(root, text="Click 'START CLICKING' to begin", font=("Arial", 10), foreground="gray")
status_label.pack(pady=5)

# Main content frame
main_frame = tk.Frame(root)
main_frame.pack(fill="both", expand=True, padx=15, pady=10)

# Left: Canvas and buttons
left_frame = tk.Frame(main_frame)
left_frame.pack(side="left", fill="both", expand=True)

canvas = tk.Canvas(left_frame, bg="black", width=650, height=500, cursor="crosshair")
canvas.pack(pady=10)
canvas.bind("<Button-1>", on_canvas_click)

# Buttons
btn_frame = tk.Frame(left_frame)
btn_frame.pack(pady=10)

start_btn = tk.Button(btn_frame, text="▶ START", command=start_clicking,
                      font=("Arial", 11, "bold"), bg="blue", fg="white", width=12)
start_btn.pack(side="left", padx=3)

undo_btn = tk.Button(btn_frame, text="↶ UNDO", command=undo_click,
                     font=("Arial", 11, "bold"), bg="orange", fg="white", width=12, state="disabled")
undo_btn.pack(side="left", padx=3)

verify_btn = tk.Button(btn_frame, text="✓ VERIFY", command=verify_clicks,
                       font=("Arial", 11, "bold"), bg="cyan", fg="black", width=12, state="disabled")
verify_btn.pack(side="left", padx=3)

clear_btn = tk.Button(btn_frame, text="🗑️ CLEAR", command=clear_clicks,
                      font=("Arial", 11, "bold"), bg="red", fg="white", width=12, state="disabled")
clear_btn.pack(side="left", padx=3)

done_btn = tk.Button(btn_frame, text="✅ DONE", command=done_clicking,
                     font=("Arial", 11, "bold"), bg="green", fg="white", width=12, state="disabled")
done_btn.pack(side="left", padx=3)

# Right: Clicks list and formula
right_frame = tk.Frame(main_frame)
right_frame.pack(side="right", fill="both", padx=20)

tk.Label(right_frame, text="Clicks (Game Coords):", font=("Arial", 10, "bold")).pack(anchor="w")
clicks_list = tk.Text(right_frame, height=12, width=25, font=("Courier", 9), state="disabled", bg="lightyellow")
clicks_list.pack(fill="both", expand=True, pady=5)

tk.Label(right_frame, text="Formula:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
formula_text = tk.Text(right_frame, height=6, width=30, font=("Courier", 8), wrap="word",
                       state="disabled", bg="lightyellow")
formula_text.pack(fill="both", expand=True, pady=5)

root.mainloop()
