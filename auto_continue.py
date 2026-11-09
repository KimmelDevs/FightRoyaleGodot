"""
Auto-Continue for ChatGPT (Windows) - NO HOTKEYS, everything is done with on-screen buttons.

Install:   pip install pyautogui pillow numpy
Run:       python auto_continue.py

Setup:
  1. Clear the ChatGPT input box so the blue button shows the WAVEFORM icon (not the up arrow).
  2. Click "1. Set button" on the little overlay, then within 4 seconds
     move your mouse over the blue circle and leave it there.
  3. Click "2. Set input box", then within 4 seconds move your mouse over the text box.
  4. Click "Start". It will type "continue" each time ChatGPT finishes generating.
  Mouse to the top-left corner of the screen = emergency stop.

It triggers only on the change: "generating (stop square)" -> "idle (waveform)".
"""
import time
import tkinter as tk

import numpy as np
import pyautogui

# ---------------- settings ----------------
MESSAGE = "continue"
MAX_SENDS = 25            # stops after this many sends
CHECK_EVERY_MS = 700      # how often to look at the button
CONFIRM_CHECKS = 2        # idle must be seen this many times in a row
COOLDOWN_SEC = 5          # minimum gap between sends
MATCH_THRESHOLD = 20      # lower = stricter icon match
CROP = 15                 # half-size of the captured square around the button
COUNTDOWN_SEC = 4         # time you get to move the mouse during setup
SEND_IMMEDIATELY = False  # True = if ChatGPT is idle when you press Start, send right away
# ------------------------------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

state = {
    "button": None,       # (x, y)
    "input": None,        # (x, y)
    "template": None,     # numpy array of the idle icon
    "running": False,
    "armed": False,       # becomes True once we've seen "generating"
    "idle_hits": 0,
    "sent": 0,
    "last_send": 0.0,
    "diff": -1.0,
    "countdown": None,    # (what, seconds_left) while setting up
}


def grab(x, y):
    img = pyautogui.screenshot(region=(x - CROP, y - CROP, CROP * 2, CROP * 2))
    return np.asarray(img.convert("L"), dtype=np.int16)


# ---------------- setup with countdown ----------------
def begin_setup(what):
    state["running"] = False
    state["countdown"] = (what, COUNTDOWN_SEC)
    root.after(1000, countdown_step)


def countdown_step():
    c = state["countdown"]
    if not c:
        return
    what, left = c
    left -= 1
    if left > 0:
        state["countdown"] = (what, left)
        root.after(1000, countdown_step)
        return
    state["countdown"] = None
    x, y = pyautogui.position()
    if what == "button":
        state["button"] = (x, y)
        # move the mouse away so the hover colour isn't baked into the template
        pyautogui.moveTo(max(x - 250, 5), max(y - 120, 5))
        time.sleep(0.5)
        state["template"] = grab(x, y)   # assumes ChatGPT is idle right now
        pyautogui.moveTo(x, y)
        state["armed"] = False
    else:
        state["input"] = (x, y)


def toggle():
    if not (state["button"] and state["input"]) or state["countdown"]:
        return
    state["running"] = not state["running"]
    state["idle_hits"] = 0
    state["armed"] = state["running"] and SEND_IMMEDIATELY
    if state["running"] and state["sent"] >= MAX_SENDS:
        state["sent"] = 0


def quit_app():
    root.destroy()


def is_idle():
    x, y = state["button"]
    diff = float(np.abs(grab(x, y) - state["template"]).mean())
    state["diff"] = diff
    return diff < MATCH_THRESHOLD


def send_continue():
    old = pyautogui.position()
    ix, iy = state["input"]
    pyautogui.click(ix, iy)
    time.sleep(0.15)
    pyautogui.write(MESSAGE, interval=0.02)
    time.sleep(0.1)
    pyautogui.press("enter")
    pyautogui.moveTo(old.x, old.y)
    state["sent"] += 1
    state["last_send"] = time.time()
    state["armed"] = False
    state["idle_hits"] = 0


# ---------------- overlay ----------------
root = tk.Tk()
root.title("Auto-Continue")
root.attributes("-topmost", True)
root.overrideredirect(True)
root.geometry("+20+20")
root.configure(bg="#111")

label = tk.Label(root, text="", fg="white", bg="#111", font=("Segoe UI", 10),
                 justify="left", padx=10, pady=6)
label.pack()

btn_row = tk.Frame(root, bg="#111")
btn_row.pack(padx=6, pady=(0, 6))


def mkbtn(text, cmd):
    b = tk.Button(btn_row, text=text, command=cmd, font=("Segoe UI", 9),
                  bg="#333", fg="white", activebackground="#555",
                  activeforeground="white", relief="flat", padx=8, pady=3)
    b.pack(side="left", padx=2)
    return b


mkbtn("1. Set button", lambda: begin_setup("button"))
mkbtn("2. Set input box", lambda: begin_setup("input"))
start_btn = mkbtn("Start", toggle)
mkbtn("Quit", quit_app)


# drag the overlay around by its text
def _start(e): root._dx, root._dy = e.x, e.y
def _drag(e): root.geometry(f"+{root.winfo_x()+e.x-root._dx}+{root.winfo_y()+e.y-root._dy}")
label.bind("<Button-1>", _start)
label.bind("<B1-Motion>", _drag)


def status_text():
    c = state["countdown"]
    if c:
        what, left = c
        target = "the blue button" if what == "button" else "the text input box"
        return f"Move mouse over {target} and\nleave it there...  {left}"
    if not state["button"]:
        return "Click '1. Set button' (waveform icon must be showing)"
    if not state["input"]:
        return "Button set ✔\nClick '2. Set input box'"
    if not state["running"]:
        return (f"Paused  ({state['sent']}/{MAX_SENDS})\nClick Start\n"
                f"match diff: {state['diff']:.1f} (idle if < {MATCH_THRESHOLD})")
    return (f"● Watching  ({state['sent']}/{MAX_SENDS})\n"
            + ("waiting for finish…" if state["armed"] else "waiting for generation…")
            + f"\nmatch diff: {state['diff']:.1f} (idle if < {MATCH_THRESHOLD})")


def tick():
    if state["running"]:
        try:
            idle = is_idle()
            if not idle:
                state["armed"] = True
                state["idle_hits"] = 0
            elif state["armed"]:
                state["idle_hits"] += 1
                cooled = time.time() - state["last_send"] > COOLDOWN_SEC
                if state["idle_hits"] >= CONFIRM_CHECKS and cooled:
                    send_continue()
                    if state["sent"] >= MAX_SENDS:
                        state["running"] = False
        except pyautogui.FailSafeException:
            state["running"] = False

    if state["button"] and state["template"] is not None and not state["running"]:
        try:
            is_idle()
        except Exception:
            pass
    start_btn.config(text="Pause" if state["running"] else "Start")
    label.config(text=status_text())
    root.after(CHECK_EVERY_MS, tick)


tick()
root.mainloop()
