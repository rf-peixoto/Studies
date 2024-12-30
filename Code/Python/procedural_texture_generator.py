import tkinter as tk
from tkinter import ttk
from tkinter.colorchooser import askcolor
from tkinter import filedialog
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageEnhance, ImageChops
import random
import math

# Try optional GPU support via PyTorch
try:
    import torch
    GPU_ACCELERATION_AVAILABLE = torch.cuda.is_available()
except ImportError:
    GPU_ACCELERATION_AVAILABLE = False

# Attempt to import the 'noise' library for Perlin/Simplex noise
try:
    from noise import pnoise2
    NOISE_LIB_AVAILABLE = True
except ImportError:
    NOISE_LIB_AVAILABLE = False


# ------------------------------------------------------------------------------------
# Example: Worley (cellular) Noise
# ------------------------------------------------------------------------------------
def worley_noise(width, height, num_cells=5, seed=0, seamless=True):
    """
    Basic Worley noise (cellular noise).
    If 'seamless' is True, the distance calculation considers wrap-around.
    """
    random.seed(seed)
    cell_centers = []
    for _ in range(num_cells):
        cx = random.randint(0, width - 1)
        cy = random.randint(0, height - 1)
        cell_centers.append((cx, cy))

    distances = []
    for y in range(height):
        row_vals = []
        for x in range(width):
            min_dist = float("inf")
            for cx, cy in cell_centers:
                dx = x - cx
                dy = y - cy
                dist_sq = dx * dx + dy * dy

                if seamless:
                    # Check wrap-around possibilities
                    dx_wrapped = (width - abs(dx)) ** 2
                    dy_wrapped = (height - abs(dy)) ** 2
                    dist_sq = min(dist_sq, dx_wrapped + dy_wrapped)

                if dist_sq < min_dist:
                    min_dist = dist_sq
            row_vals.append(math.sqrt(min_dist))
        distances.append(row_vals)

    max_dist = max(max(row) for row in distances)
    if max_dist == 0:
        max_dist = 1

    img = Image.new("L", (width, height))
    for y in range(height):
        for x in range(width):
            val = int((distances[y][x] / max_dist) * 255)
            img.putpixel((x, y), val)

    return img.convert("RGB")


# ------------------------------------------------------------------------------------
# Example: Fractal Brownian Motion (naïve approach)
# ------------------------------------------------------------------------------------
def fractal_brownian_motion(x, y, octaves=4, persistence=0.5, seed=0):
    """
    Illustrates fractal Brownian motion with a basic random approach.
    For better quality, consider a real Perlin or simplex-based fBm.
    """
    total = 0.0
    frequency = 1.0
    amplitude = 1.0
    max_val = 0.0
    for _ in range(octaves):
        random.seed(seed + int(x * frequency) + 1013 * int(y * frequency))
        total += random.random() * amplitude
        max_val += amplitude
        amplitude *= persistence
        frequency *= 2
    return total / max_val


# ------------------------------------------------------------------------------------
# Data structure for each layer
# ------------------------------------------------------------------------------------
class Layer:
    """
    Stores all parameters relevant to generating and modifying a single layer.
    """
    def __init__(
        self,
        pattern_name="Basic Noise",
        alpha=1.0,
        seed=None,
        seamless=True,
        blur_amount=0.0,
        distortion_amount=0.0,
        distortion_type="Sinusoidal",
        brightness=1.0,
        contrast=1.0,
        sharpen=0.0,
        color_shift=0.0,
        overlay_color=(255, 255, 255),
        overlay_alpha=0.0,
        rotate=0.0,
        flip_horizontal=False,
        flip_vertical=False,
        invert_colors=False
    ):
        self.pattern_name = pattern_name
        self.alpha = alpha
        self.seed = seed
        self.seamless = seamless

        self.blur_amount = blur_amount
        self.distortion_amount = distortion_amount
        self.distortion_type = distortion_type
        self.brightness = brightness
        self.contrast = contrast
        self.sharpen = sharpen
        self.color_shift = color_shift
        self.overlay_color = overlay_color
        self.overlay_alpha = overlay_alpha

        self.rotate = rotate
        self.flip_horizontal = flip_horizontal
        self.flip_vertical = flip_vertical
        self.invert_colors = invert_colors


# ------------------------------------------------------------------------------------
# Layer Editor Window (for editing an existing layer) with live preview
# ------------------------------------------------------------------------------------
class LayerEditorWindow(tk.Toplevel):
    """
    A popup window to edit an existing layer's parameters and update preview in real time.
    """
    def __init__(self, parent, layer, layer_index, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.original_layer = layer  # reference to the layer in parent's self.layers
        self.layer_index = layer_index
        self.title("Edit Layer")

        # Make a copy of the layer for live editing
        self.temp_layer = Layer(
            pattern_name=layer.pattern_name,
            alpha=layer.alpha,
            seed=layer.seed,
            seamless=layer.seamless,
            blur_amount=layer.blur_amount,
            distortion_amount=layer.distortion_amount,
            distortion_type=layer.distortion_type,
            brightness=layer.brightness,
            contrast=layer.contrast,
            sharpen=layer.sharpen,
            color_shift=layer.color_shift,
            overlay_color=layer.overlay_color,
            overlay_alpha=layer.overlay_alpha,
            rotate=layer.rotate,
            flip_horizontal=layer.flip_horizontal,
            flip_vertical=layer.flip_vertical,
            invert_colors=layer.invert_colors
        )

        # Patterns and Distortion types (same as in main)
        self.pattern_options = parent.pattern_options
        self.distortion_options = parent.distortion_types

        # Build the editor UI
        self.create_widgets()
        # Make the window modal
        self.grab_set()

        # Update preview right after creation
        self.update_parent_preview()

    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Pattern
        ttk.Label(main_frame, text="Pattern:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.pattern_var = tk.StringVar(value=self.temp_layer.pattern_name)
        pattern_menu = ttk.OptionMenu(main_frame, self.pattern_var, self.pattern_var.get(), *self.pattern_options, 
                                      command=self.on_param_change)
        pattern_menu.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Seamless
        self.seamless_var = tk.BooleanVar(value=self.temp_layer.seamless)
        seamless_check = ttk.Checkbutton(main_frame, text="Seamless", variable=self.seamless_var, command=self.on_param_change)
        seamless_check.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        # Seed
        self.use_seed_var = tk.BooleanVar(value=(self.temp_layer.seed is not None))
        seed_check = ttk.Checkbutton(main_frame, text="Use Seed", variable=self.use_seed_var, command=self.on_param_change)
        seed_check.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.seed_var = tk.IntVar(value=self.temp_layer.seed if self.temp_layer.seed is not None else 0)
        seed_entry = ttk.Entry(main_frame, textvariable=self.seed_var, width=8)
        seed_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        seed_entry.bind("<KeyRelease>", self.on_param_change)  # Live updates on seed change

        # Alpha
        ttk.Label(main_frame, text="Layer α:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.alpha_var = tk.DoubleVar(value=self.temp_layer.alpha)
        alpha_slider = ttk.Scale(main_frame, from_=0.0, to=1.0, variable=self.alpha_var, command=self.on_param_change)
        alpha_slider.grid(row=3, column=1, padx=5, pady=5, sticky="we")

        # Blur
        ttk.Label(main_frame, text="Blur:").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.blur_var = tk.DoubleVar(value=self.temp_layer.blur_amount)
        blur_slider = ttk.Scale(main_frame, from_=0.0, to=10.0, variable=self.blur_var, command=self.on_param_change)
        blur_slider.grid(row=4, column=1, padx=5, pady=5, sticky="we")

        # Distortion
        ttk.Label(main_frame, text="Distortion:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
        self.distortion_var = tk.DoubleVar(value=self.temp_layer.distortion_amount)
        dist_slider = ttk.Scale(main_frame, from_=0.0, to=1.0, variable=self.distortion_var, command=self.on_param_change)
        dist_slider.grid(row=5, column=1, padx=5, pady=5, sticky="we")

        ttk.Label(main_frame, text="Dist. Type:").grid(row=5, column=2, padx=5, pady=5, sticky="e")
        self.distortion_type_var = tk.StringVar(value=self.temp_layer.distortion_type)
        dist_type_menu = ttk.OptionMenu(main_frame, self.distortion_type_var, self.distortion_type_var.get(), 
                                        *self.distortion_options, command=self.on_param_change)
        dist_type_menu.grid(row=5, column=3, padx=5, pady=5, sticky="w")

        # Brightness
        ttk.Label(main_frame, text="Brightness:").grid(row=6, column=0, padx=5, pady=5, sticky="e")
        self.brightness_var = tk.DoubleVar(value=self.temp_layer.brightness)
        brightness_slider = ttk.Scale(main_frame, from_=0.1, to=2.0, variable=self.brightness_var, command=self.on_param_change)
        brightness_slider.grid(row=6, column=1, padx=5, pady=5, sticky="we")

        # Contrast
        ttk.Label(main_frame, text="Contrast:").grid(row=7, column=0, padx=5, pady=5, sticky="e")
        self.contrast_var = tk.DoubleVar(value=self.temp_layer.contrast)
        contrast_slider = ttk.Scale(main_frame, from_=0.1, to=2.0, variable=self.contrast_var, command=self.on_param_change)
        contrast_slider.grid(row=7, column=1, padx=5, pady=5, sticky="we")

        # Sharpen
        ttk.Label(main_frame, text="Sharpen:").grid(row=8, column=0, padx=5, pady=5, sticky="e")
        self.sharpen_var = tk.DoubleVar(value=self.temp_layer.sharpen)
        sharpen_slider = ttk.Scale(main_frame, from_=0.0, to=5.0, variable=self.sharpen_var, command=self.on_param_change)
        sharpen_slider.grid(row=8, column=1, padx=5, pady=5, sticky="we")

        # Color shift
        ttk.Label(main_frame, text="Color Shift:").grid(row=9, column=0, padx=5, pady=5, sticky="e")
        self.color_shift_var = tk.DoubleVar(value=self.temp_layer.color_shift)
        color_shift_slider = ttk.Scale(main_frame, from_=-128.0, to=128.0, variable=self.color_shift_var, command=self.on_param_change)
        color_shift_slider.grid(row=9, column=1, padx=5, pady=5, sticky="we")

        # Overlay alpha + color
        ttk.Label(main_frame, text="Overlay α:").grid(row=10, column=0, padx=5, pady=5, sticky="e")
        self.overlay_alpha_var = tk.DoubleVar(value=self.temp_layer.overlay_alpha)
        overlay_alpha_slider = ttk.Scale(main_frame, from_=0.0, to=1.0, variable=self.overlay_alpha_var, command=self.on_param_change)
        overlay_alpha_slider.grid(row=10, column=1, padx=5, pady=5, sticky="we")

        pick_color_btn = ttk.Button(main_frame, text="Overlay Color", command=self.pick_overlay_color)
        pick_color_btn.grid(row=10, column=2, padx=5, pady=5, sticky="w")

        # Rotate
        ttk.Label(main_frame, text="Rotate:").grid(row=11, column=0, padx=5, pady=5, sticky="e")
        self.rotate_var = tk.DoubleVar(value=self.temp_layer.rotate)
        rotate_slider = ttk.Scale(main_frame, from_=0.0, to=359.0, variable=self.rotate_var, command=self.on_param_change)
        rotate_slider.grid(row=11, column=1, padx=5, pady=5, sticky="we")

        # Flips / Invert
        self.flip_h_var = tk.BooleanVar(value=self.temp_layer.flip_horizontal)
        flip_h_check = ttk.Checkbutton(main_frame, text="Flip H", variable=self.flip_h_var, command=self.on_param_change)
        flip_h_check.grid(row=12, column=0, padx=5, pady=5, sticky="w")

        self.flip_v_var = tk.BooleanVar(value=self.temp_layer.flip_vertical)
        flip_v_check = ttk.Checkbutton(main_frame, text="Flip V", variable=self.flip_v_var, command=self.on_param_change)
        flip_v_check.grid(row=12, column=1, padx=5, pady=5, sticky="w")

        self.invert_var = tk.BooleanVar(value=self.temp_layer.invert_colors)
        invert_check = ttk.Checkbutton(main_frame, text="Invert Colors", variable=self.invert_var, command=self.on_param_change)
        invert_check.grid(row=13, column=0, padx=5, pady=5, sticky="w")

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=14, column=0, columnspan=4, pady=10, sticky="e")

        apply_btn = ttk.Button(button_frame, text="Apply Changes", command=self.apply_changes)
        apply_btn.pack(side=tk.RIGHT, padx=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.on_cancel)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

        # Column expansions
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(3, weight=1)

    def pick_overlay_color(self):
        color_code = askcolor(color=self.temp_layer.overlay_color, parent=self)
        if color_code[0] is not None:
            self.temp_layer.overlay_color = tuple(int(c) for c in color_code[0])
        self.on_param_change()  # update preview

    def on_param_change(self, *_):
        """Callback whenever a parameter changes; update self.temp_layer + parent's preview."""
        self.temp_layer.pattern_name = self.pattern_var.get()
        self.temp_layer.seamless = self.seamless_var.get()
        self.temp_layer.seed = self.seed_var.get() if self.use_seed_var.get() else None
        self.temp_layer.alpha = self.alpha_var.get()

        self.temp_layer.blur_amount = self.blur_var.get()
        self.temp_layer.distortion_amount = self.distortion_var.get()
        self.temp_layer.distortion_type = self.distortion_type_var.get()
        self.temp_layer.brightness = self.brightness_var.get()
        self.temp_layer.contrast = self.contrast_var.get()
        self.temp_layer.sharpen = self.sharpen_var.get()
        self.temp_layer.color_shift = self.color_shift_var.get()
        self.temp_layer.overlay_alpha = self.overlay_alpha_var.get()
        # self.temp_layer.overlay_color is updated in pick_overlay_color
        self.temp_layer.rotate = self.rotate_var.get()
        self.temp_layer.flip_horizontal = self.flip_h_var.get()
        self.temp_layer.flip_vertical = self.flip_v_var.get()
        self.temp_layer.invert_colors = self.invert_var.get()

        self.update_parent_preview()

    def update_parent_preview(self):
        """Temporarily replace the actual layer with self.temp_layer and refresh preview."""
        # Backup the original
        old_layer = self.parent.layers[self.layer_index]
        self.parent.layers[self.layer_index] = self.temp_layer
        self.parent.update_preview()
        # Restore the old so we do not permanently alter it yet
        self.parent.layers[self.layer_index] = old_layer

    def apply_changes(self):
        # Commit: copy the temp layer’s final values to the actual layer
        self.original_layer.pattern_name = self.temp_layer.pattern_name
        self.original_layer.alpha = self.temp_layer.alpha
        self.original_layer.seed = self.temp_layer.seed
        self.original_layer.seamless = self.temp_layer.seamless

        self.original_layer.blur_amount = self.temp_layer.blur_amount
        self.original_layer.distortion_amount = self.temp_layer.distortion_amount
        self.original_layer.distortion_type = self.temp_layer.distortion_type
        self.original_layer.brightness = self.temp_layer.brightness
        self.original_layer.contrast = self.temp_layer.contrast
        self.original_layer.sharpen = self.temp_layer.sharpen
        self.original_layer.color_shift = self.temp_layer.color_shift
        self.original_layer.overlay_color = self.temp_layer.overlay_color
        self.original_layer.overlay_alpha = self.temp_layer.overlay_alpha

        self.original_layer.rotate = self.temp_layer.rotate
        self.original_layer.flip_horizontal = self.temp_layer.flip_horizontal
        self.original_layer.flip_vertical = self.temp_layer.flip_vertical
        self.original_layer.invert_colors = self.temp_layer.invert_colors

        # Update listbox text
        self.parent.layer_listbox.delete(self.layer_index)
        self.parent.layer_listbox.insert(self.layer_index, f"{self.original_layer.pattern_name} (α={self.original_layer.alpha:.2f})")
        # Actually refresh
        self.parent.update_preview()
        self.destroy()

    def on_cancel(self):
        # Do not commit changes; simply close
        self.destroy()


# ------------------------------------------------------------------------------------
# Main GUI
# ------------------------------------------------------------------------------------
class TextureGeneratorGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Procedural Texture Generator")

        # Patterns
        self.pattern_options = [
            "Basic Noise",
            "Checkerboard",
            "Marble",
            "Wood",
            "Plasma",
            "Worley Noise",
            "Perlin (if available)",
            "FractalBrownian",
        ]

        # Distortion types
        self.distortion_types = ["Sinusoidal", "Wave", "Twirl"]

        # Common sizes
        self.size_options = ["8x8", "16x16", "32x32", "64x64", "128x128", "256x256"]

        # Gradient colors (start/end)
        self.gradient_colors = [(0, 0, 0), (255, 255, 255)]

        # Store layers
        self.layers = []

        # A "temp layer" for live preview while creating a new layer
        self.temp_new_layer = None

        # Final image
        self.generated_image = None

        # Main controlling variables for new layer creation
        self.selected_pattern = tk.StringVar(value=self.pattern_options[0])
        self.selected_size = tk.StringVar(value=self.size_options[3])
        self.new_layer_alpha = tk.DoubleVar(value=1.0)
        self.new_seed_value = tk.IntVar(value=0)
        self.new_use_seed = tk.BooleanVar(value=False)
        self.new_seamless = tk.BooleanVar(value=True)

        self.new_blur_amount = tk.DoubleVar(value=0.0)
        self.new_distortion_amount = tk.DoubleVar(value=0.0)
        self.new_distortion_type = tk.StringVar(value=self.distortion_types[0])
        self.new_brightness = tk.DoubleVar(value=1.0)
        self.new_contrast = tk.DoubleVar(value=1.0)
        self.new_sharpen = tk.DoubleVar(value=0.0)
        self.new_color_shift = tk.DoubleVar(value=0.0)
        self.new_overlay_color = (255, 255, 255)
        self.new_overlay_alpha = tk.DoubleVar(value=0.0)
        self.new_rotate = tk.DoubleVar(value=0.0)
        self.new_flip_horizontal = tk.BooleanVar(value=False)
        self.new_flip_vertical = tk.BooleanVar(value=False)
        self.new_invert_colors = tk.BooleanVar(value=False)

        # Automated exploration
        self.explore_count = tk.IntVar(value=4)

        self.create_widgets()
        self.bind_new_layer_events()  # to get live preview
        self.update_preview()

    # --------------------------------------------------------------------------------
    # UI Construction
    # --------------------------------------------------------------------------------
    def create_widgets(self):
        # Frame: Basic pattern + size
        pattern_frame = ttk.LabelFrame(self.master, text="New Layer Generation")
        pattern_frame.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        # Pattern
        ttk.Label(pattern_frame, text="Pattern:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        pattern_menu = ttk.OptionMenu(
            pattern_frame,
            self.selected_pattern,
            self.pattern_options[0],
            *self.pattern_options,
            command=self.on_new_layer_param_change
        )
        pattern_menu.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Size
        ttk.Label(pattern_frame, text="Size:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        size_menu = ttk.OptionMenu(
            pattern_frame,
            self.selected_size,
            self.size_options[3],
            *self.size_options,
            command=self.on_new_layer_param_change
        )
        size_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Seamless
        ttk.Checkbutton(pattern_frame, text="Seamless", variable=self.new_seamless, command=self.on_new_layer_param_change).grid(
            row=2, column=0, columnspan=2, padx=5, pady=5, sticky="w"
        )

        # Seed
        seed_frame = ttk.LabelFrame(pattern_frame, text="Seed")
        seed_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(seed_frame, text="Use Seed", variable=self.new_use_seed, command=self.on_new_layer_param_change).grid(
            row=0, column=0, padx=5, pady=5, sticky="w"
        )
        seed_entry = ttk.Entry(seed_frame, textvariable=self.new_seed_value, width=8)
        seed_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        seed_entry.bind("<KeyRelease>", lambda e: self.on_new_layer_param_change())

        # Effects (blur, distortion, brightness, etc.)
        effects_frame = ttk.LabelFrame(self.master, text="Effects (for new layer)")
        effects_frame.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        # Blur
        ttk.Label(effects_frame, text="Blur:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        blur_slider = ttk.Scale(effects_frame, from_=0.0, to=10.0, variable=self.new_blur_amount, command=self.on_new_layer_param_change)
        blur_slider.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # Distortion
        ttk.Label(effects_frame, text="Distortion:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        dist_slider = ttk.Scale(effects_frame, from_=0.0, to=1.0, variable=self.new_distortion_amount, command=self.on_new_layer_param_change)
        dist_slider.grid(row=1, column=1, padx=5, pady=5, sticky="we")

        ttk.Label(effects_frame, text="Type:").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        dist_type_menu = ttk.OptionMenu(effects_frame, self.new_distortion_type, self.distortion_types[0], *self.distortion_types,
                                        command=self.on_new_layer_param_change)
        dist_type_menu.grid(row=1, column=3, padx=5, pady=5, sticky="w")

        # Brightness
        ttk.Label(effects_frame, text="Brightness:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        bright_slider = ttk.Scale(effects_frame, from_=0.1, to=2.0, variable=self.new_brightness, command=self.on_new_layer_param_change)
        bright_slider.grid(row=2, column=1, padx=5, pady=5, sticky="we")

        # Contrast
        ttk.Label(effects_frame, text="Contrast:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        contrast_slider = ttk.Scale(effects_frame, from_=0.1, to=2.0, variable=self.new_contrast, command=self.on_new_layer_param_change)
        contrast_slider.grid(row=3, column=1, padx=5, pady=5, sticky="we")

        # Sharpen
        ttk.Label(effects_frame, text="Sharpen:").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        sharpen_slider = ttk.Scale(effects_frame, from_=0.0, to=5.0, variable=self.new_sharpen, command=self.on_new_layer_param_change)
        sharpen_slider.grid(row=4, column=1, padx=5, pady=5, sticky="we")

        # Color shift
        ttk.Label(effects_frame, text="Color Shift:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
        color_shift_slider = ttk.Scale(effects_frame, from_=-128.0, to=128.0, variable=self.new_color_shift, command=self.on_new_layer_param_change)
        color_shift_slider.grid(row=5, column=1, padx=5, pady=5, sticky="we")

        # Overlay alpha + color
        ttk.Label(effects_frame, text="Overlay α:").grid(row=6, column=0, padx=5, pady=5, sticky="e")
        overlay_alpha_slider = ttk.Scale(effects_frame, from_=0.0, to=1.0, variable=self.new_overlay_alpha, command=self.on_new_layer_param_change)
        overlay_alpha_slider.grid(row=6, column=1, padx=5, pady=5, sticky="we")

        pick_overlay_color_btn = ttk.Button(effects_frame, text="Overlay Color", command=self.pick_new_overlay_color)
        pick_overlay_color_btn.grid(row=6, column=2, padx=5, pady=5, sticky="w")

        # Transform
        transform_frame = ttk.LabelFrame(self.master, text="Transform (for new layer)")
        transform_frame.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        # Rotate
        ttk.Label(transform_frame, text="Rotate:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        rotate_slider = ttk.Scale(transform_frame, from_=0.0, to=359.0, variable=self.new_rotate, command=self.on_new_layer_param_change)
        rotate_slider.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        # Flips
        flip_h_check = ttk.Checkbutton(transform_frame, text="Flip H", variable=self.new_flip_horizontal, command=self.on_new_layer_param_change)
        flip_h_check.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        flip_v_check = ttk.Checkbutton(transform_frame, text="Flip V", variable=self.new_flip_vertical, command=self.on_new_layer_param_change)
        flip_v_check.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        invert_check = ttk.Checkbutton(transform_frame, text="Invert Colors", variable=self.new_invert_colors, command=self.on_new_layer_param_change)
        invert_check.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        # Layer alpha
        ttk.Label(transform_frame, text="Layer α:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        alpha_slider = ttk.Scale(transform_frame, from_=0.0, to=1.0, variable=self.new_layer_alpha, command=self.on_new_layer_param_change)
        alpha_slider.grid(row=3, column=1, padx=5, pady=5, sticky="we")

        # Add layer
        add_layer_btn = ttk.Button(transform_frame, text="Add Layer", command=self.add_layer)
        add_layer_btn.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="we")

        # Existing layers list
        layer_list_frame = ttk.LabelFrame(self.master, text="Layers")
        layer_list_frame.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")

        self.layer_listbox = tk.Listbox(layer_list_frame, height=8)
        self.layer_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(layer_list_frame, orient=tk.VERTICAL, command=self.layer_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.layer_listbox.config(yscrollcommand=scrollbar.set)

        # Buttons for layer management
        buttons_frame = ttk.Frame(layer_list_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        remove_btn = ttk.Button(buttons_frame, text="Remove Selected", command=self.remove_selected_layer)
        remove_btn.pack(side=tk.RIGHT, padx=5)

        edit_btn = ttk.Button(buttons_frame, text="Edit Selected", command=self.edit_selected_layer)
        edit_btn.pack(side=tk.RIGHT, padx=5)

        # Gradient
        gradient_frame = ttk.LabelFrame(self.master, text="Final Gradient Mapping")
        gradient_frame.grid(row=4, column=0, padx=5, pady=5, sticky="w")

        pick_start_color_btn = ttk.Button(gradient_frame, text="Pick Start Color", command=lambda: self.pick_gradient_color(0))
        pick_start_color_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        pick_end_color_btn = ttk.Button(gradient_frame, text="Pick End Color", command=lambda: self.pick_gradient_color(1))
        pick_end_color_btn.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Automated exploration
        explore_frame = ttk.LabelFrame(self.master, text="Automated Exploration")
        explore_frame.grid(row=5, column=0, padx=5, pady=5, sticky="w")

        ttk.Label(explore_frame, text="Count:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        count_entry = ttk.Entry(explore_frame, textvariable=self.explore_count, width=4)
        count_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        explore_btn = ttk.Button(explore_frame, text="Generate Batch", command=self.explore_random)
        explore_btn.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        # Preview
        preview_frame = ttk.LabelFrame(self.master, text="Preview")
        preview_frame.grid(row=0, column=1, rowspan=6, padx=5, pady=5, sticky="nsew")

        self.preview_label = ttk.Label(preview_frame)
        self.preview_label.pack(padx=5, pady=5)

        # Export
        export_btn = ttk.Button(self.master, text="Export Texture", command=self.export_texture)
        export_btn.grid(row=6, column=1, padx=5, pady=5, sticky="e")

        # Make the second column expandable
        self.master.columnconfigure(1, weight=1)
        self.master.rowconfigure(0, weight=1)

    def bind_new_layer_events(self):
        """
        Establish event binding so that any change to new-layer parameters
        triggers a re-computation of the preview using a 'temporary' new layer.
        """
        # The majority of them are done via `command=self.on_new_layer_param_change`
        # or `bind("<KeyRelease>")` above. This method can be used for more if needed.
        pass

    # --------------------------------------------------------------------------------
    # New Layer Live Preview
    # --------------------------------------------------------------------------------
    def on_new_layer_param_change(self, *_):
        """Construct a temp layer from current input, re-generate preview."""
        self.temp_new_layer = self.build_temp_new_layer()
        self.update_preview(use_temp_layer=True)

    def build_temp_new_layer(self):
        seed_val = self.new_seed_value.get() if self.new_use_seed.get() else None
        layer = Layer(
            pattern_name=self.selected_pattern.get(),
            alpha=self.new_layer_alpha.get(),
            seed=seed_val,
            seamless=self.new_seamless.get(),
            blur_amount=self.new_blur_amount.get(),
            distortion_amount=self.new_distortion_amount.get(),
            distortion_type=self.new_distortion_type.get(),
            brightness=self.new_brightness.get(),
            contrast=self.new_contrast.get(),
            sharpen=self.new_sharpen.get(),
            color_shift=self.new_color_shift.get(),
            overlay_color=self.new_overlay_color,
            overlay_alpha=self.new_overlay_alpha.get(),
            rotate=self.new_rotate.get(),
            flip_horizontal=self.new_flip_horizontal.get(),
            flip_vertical=self.new_flip_vertical.get(),
            invert_colors=self.new_invert_colors.get()
        )
        return layer

    # --------------------------------------------------------------------------------
    # Layer Editing
    # --------------------------------------------------------------------------------
    def edit_selected_layer(self):
        selection = self.layer_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        layer = self.layers[index]

        editor = LayerEditorWindow(self, layer, index)

    # --------------------------------------------------------------------------------
    # Actions: Add/Remove Layers
    # --------------------------------------------------------------------------------
    def add_layer(self):
        """
        Finalize the temporary new layer (if any) by actually appending it to self.layers.
        """
        if not self.temp_new_layer:
            # If user never changed any controls, build one from scratch
            self.temp_new_layer = self.build_temp_new_layer()
        # Add to layers
        self.layers.append(self.temp_new_layer)
        self.layer_listbox.insert(tk.END, f"{self.temp_new_layer.pattern_name} (α={self.temp_new_layer.alpha:.2f})")
        # Clear the temp layer reference
        self.temp_new_layer = None
        # Re-generate final preview
        self.update_preview()

    def remove_selected_layer(self):
        selection = self.layer_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.layer_listbox.delete(index)
        del self.layers[index]
        self.update_preview()

    # --------------------------------------------------------------------------------
    # Color pickers
    # --------------------------------------------------------------------------------
    def pick_new_overlay_color(self):
        color_code = askcolor()
        if color_code[0] is not None:
            self.new_overlay_color = tuple(int(c) for c in color_code[0])
        # Then re-generate
        self.on_new_layer_param_change()

    def pick_gradient_color(self, index):
        color_code = askcolor()
        if color_code[0] is not None:
            self.gradient_colors[index] = tuple(int(c) for c in color_code[0])
        self.update_preview()

    # --------------------------------------------------------------------------------
    # Main generation flow
    # --------------------------------------------------------------------------------
    def update_preview(self, use_temp_layer=False):
        """
        Generates the composite of all permanent layers (self.layers)
        plus optionally the self.temp_new_layer if use_temp_layer == True.
        Then applies the final gradient and updates the preview widget.
        """
        final_img = self.generate_texture(use_temp_layer)
        if final_img is None:
            return

        preview_size = 256
        preview_img = final_img.resize((preview_size, preview_size), Image.NEAREST)
        tk_preview = ImageTk.PhotoImage(preview_img)
        self.preview_label.config(image=tk_preview)
        self.preview_label.image = tk_preview

    def generate_texture(self, use_temp_layer=False):
        # Parse final size
        size_str = self.selected_size.get()
        width, height = map(int, size_str.split("x"))

        # Start with a blank base
        final_img = Image.new("RGB", (width, height), (0, 0, 0))

        # Composite permanent layers
        for layer in self.layers:
            layer_img = self.generate_layer_image(layer, width, height)
            if layer.alpha < 1.0:
                final_img = Image.blend(final_img, layer_img, layer.alpha)
            else:
                final_img = ImageChops.add(final_img, layer_img)

        # If there's a temp layer, incorporate it as well
        if use_temp_layer and self.temp_new_layer:
            layer_img = self.generate_layer_image(self.temp_new_layer, width, height)
            if self.temp_new_layer.alpha < 1.0:
                final_img = Image.blend(final_img, layer_img, self.temp_new_layer.alpha)
            else:
                final_img = ImageChops.add(final_img, layer_img)

        # Apply final gradient
        final_img = self.apply_gradient(final_img)
        self.generated_image = final_img
        return final_img

    def generate_layer_image(self, layer, width, height):
        if layer.seed is not None:
            random.seed(layer.seed)
        else:
            random.seed()

        # 1) Base pattern
        img = self.create_base_pattern(layer.pattern_name, width, height, layer.seamless, layer.seed)

        # 2) Blur
        if layer.blur_amount > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=layer.blur_amount))

        # 3) Distortion
        if layer.distortion_amount > 0:
            img = self.distort_image(img, layer.distortion_amount, layer.distortion_type)

        # 4) Enhance (brightness, contrast, sharpen)
        img = self.enhance_image(img, layer.brightness, layer.contrast, layer.sharpen)

        # 5) Color shift
        if abs(layer.color_shift) > 0:
            img = self.apply_color_shift(img, layer.color_shift)

        # 6) Overlay color
        if layer.overlay_alpha > 0:
            img = self.apply_color_overlay(img, layer.overlay_color, layer.overlay_alpha)

        # 7) Transforms (rotate, flip, invert)
        img = self.apply_transforms(img, layer.rotate, layer.flip_horizontal, layer.flip_vertical, layer.invert_colors)

        return img

    # --------------------------------------------------------------------------------
    # Base Patterns
    # --------------------------------------------------------------------------------
    def create_base_pattern(self, pattern_name, width, height, seamless, seed):
        if pattern_name == "Basic Noise":
            return self.basic_noise(width, height, seamless)

        elif pattern_name == "Checkerboard":
            return self.checkerboard(width, height, seamless)

        elif pattern_name == "Marble":
            return self.marble(width, height, seamless)

        elif pattern_name == "Wood":
            return self.wood(width, height, seamless)

        elif pattern_name == "Plasma":
            return self.plasma(width, height, seamless)

        elif pattern_name == "Worley Noise":
            return worley_noise(width, height, num_cells=8, seed=seed if seed else 0, seamless=seamless)

        elif pattern_name == "Perlin (if available)" and NOISE_LIB_AVAILABLE:
            return self.perlin_noise(width, height, seed if seed else 0, seamless)

        elif pattern_name == "FractalBrownian":
            return self.fractal_brownian(width, height, seed, seamless)

        # Fallback
        return Image.new("RGB", (width, height), (128, 128, 128))

    def basic_noise(self, width, height, seamless):
        img = Image.new("L", (width, height))
        for y in range(height):
            for x in range(width):
                val = random.randint(0, 255)
                img.putpixel((x, y), val)
        return img.convert("RGB")

    def checkerboard(self, width, height, seamless):
        img = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        square_size = max(width, height) // 8
        for y in range(height):
            for x in range(width):
                if ((x // square_size) + (y // square_size)) % 2 == 0:
                    draw.point((x, y), fill=(255, 255, 255))
        return img

    def marble(self, width, height, seamless):
        img = Image.new("L", (width, height))
        for y in range(height):
            for x in range(width):
                xx = x if not seamless else (x % width)
                yy = y if not seamless else (y % height)
                val = int((math.sin(xx * 0.05 + yy * 0.05) + 1) * 127.5)
                img.putpixel((x, y), val)
        return img.convert("RGB")

    def wood(self, width, height, seamless):
        center_x, center_y = width // 2, height // 2
        img = Image.new("L", (width, height))
        for y in range(height):
            for x in range(width):
                dx = x - center_x
                dy = y - center_y
                if seamless:
                    dx_mod = min(abs(dx), abs(width - abs(dx)))
                    dy_mod = min(abs(dy), abs(height - abs(dy)))
                    dist = math.sqrt(dx_mod * dx_mod + dy_mod * dy_mod)
                else:
                    dist = math.sqrt(dx * dx + dy * dy)
                val = int((math.sin(dist * 0.1) + 1) * 127.5)
                img.putpixel((x, y), val)

        rgb_img = Image.new("RGB", (width, height))
        for y in range(height):
            for x in range(width):
                v = img.getpixel((x, y))
                rgb_img.putpixel((x, y), (v, int(v * 0.7), int(v * 0.4)))
        return rgb_img

    def plasma(self, width, height, seamless):
        img = Image.new("RGB", (width, height))
        for y in range(height):
            for x in range(width):
                xx = x if not seamless else (x % width)
                yy = y if not seamless else (y % height)
                r = int((128.0 + 128.0 * math.sin(xx / 16.0)) + (128.0 + 128.0 * math.sin(yy / 8.0)) / 2) % 256
                g = int((128.0 + 128.0 * math.sin(yy / 16.0)) + (128.0 + 128.0 * math.sin(xx / 8.0)) / 2) % 256
                b = int((r + g) / 2) % 256
                img.putpixel((x, y), (r, g, b))
        return img

    def perlin_noise(self, width, height, seed, seamless):
        # pnoise2 from 'noise' library
        scale = 0.1
        octaves = 4
        img = Image.new("L", (width, height))
        for y in range(height):
            for x in range(width):
                if seamless:
                    val = pnoise2(
                        x * scale, y * scale,
                        octaves=octaves,
                        base=seed,
                        repeatx=width,
                        repeaty=height
                    )
                else:
                    val = pnoise2(x * scale, y * scale, octaves=octaves, base=seed)
                gray = int((val + 1) * 127.5)
                img.putpixel((x, y), gray)
        return img.convert("RGB")

    def fractal_brownian(self, width, height, seed, seamless):
        img = Image.new("L", (width, height))
        for y in range(height):
            for x in range(width):
                xx = x if not seamless else (x % width)
                yy = y if not seamless else (y % height)
                val = fractal_brownian_motion(xx, yy, octaves=4, persistence=0.5, seed=seed if seed else 0)
                gray = int(val * 255)
                img.putpixel((x, y), gray)
        return img.convert("RGB")

    # --------------------------------------------------------------------------------
    # Distortions
    # --------------------------------------------------------------------------------
    def distort_image(self, img, amount, distortion_type):
        if distortion_type == "Sinusoidal":
            return self.sinusoidal_distort(img, amount)
        elif distortion_type == "Wave":
            return self.wave_distort(img, amount)
        elif distortion_type == "Twirl":
            return self.twirl_distort(img, amount)
        return img

    def sinusoidal_distort(self, img, strength):
        width, height = img.size
        src = img.load()
        out = Image.new("RGB", (width, height))
        dst = out.load()

        for y in range(height):
            for x in range(width):
                offset_x = int(strength * math.sin(2 * math.pi * y / 32.0))
                offset_y = int(strength * math.sin(2 * math.pi * x / 32.0))
                nx = (x + offset_x) % width
                ny = (y + offset_y) % height
                dst[x, y] = src[nx, ny]
        return out

    def wave_distort(self, img, strength):
        width, height = img.size
        src = img.load()
        out = Image.new("RGB", (width, height))
        dst = out.load()

        for y in range(height):
            wave_offset = int(strength * math.sin(2 * math.pi * y / 32.0) * 10)
            for x in range(width):
                nx = (x + wave_offset) % width
                dst[x, y] = src[nx, y]
        return out

    def twirl_distort(self, img, strength):
        width, height = img.size
        src = img.load()
        out = Image.new("RGB", (width, height))
        dst = out.load()

        center_x, center_y = width // 2, height // 2
        max_radius = math.sqrt(center_x**2 + center_y**2)
        for y in range(height):
            for x in range(width):
                dx = x - center_x
                dy = y - center_y
                radius = math.sqrt(dx*dx + dy*dy)
                if radius < max_radius:
                    twist = strength * (1 - radius / max_radius)
                    current_angle = math.atan2(dy, dx)
                    new_angle = current_angle + twist
                    nx = int(center_x + radius * math.cos(new_angle))
                    ny = int(center_y + radius * math.sin(new_angle))
                    if 0 <= nx < width and 0 <= ny < height:
                        dst[x, y] = src[nx, ny]
                    else:
                        dst[x, y] = (0, 0, 0)
                else:
                    dst[x, y] = src[x, y]
        return out

    # --------------------------------------------------------------------------------
    # Enhancements
    # --------------------------------------------------------------------------------
    def enhance_image(self, img, brightness, contrast, sharpen):
        # Brightness
        enhancer_brightness = ImageEnhance.Brightness(img)
        img = enhancer_brightness.enhance(brightness)

        # Contrast
        enhancer_contrast = ImageEnhance.Contrast(img)
        img = enhancer_contrast.enhance(contrast)

        # Sharpen (applied multiple times if >1)
        for _ in range(int(sharpen)):
            img = img.filter(ImageFilter.SHARPEN)

        return img

    def apply_color_shift(self, img, shift):
        pixels = img.load()
        width, height = img.size
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                r = max(min(r + int(shift), 255), 0)
                g = max(min(g + int(shift), 255), 0)
                b = max(min(b + int(shift), 255), 0)
                pixels[x, y] = (r, g, b)
        return img

    def apply_color_overlay(self, img, color, alpha):
        overlay = Image.new("RGB", img.size, color)
        return Image.blend(img, overlay, alpha=alpha)

    # --------------------------------------------------------------------------------
    # Transformations
    # --------------------------------------------------------------------------------
    def apply_transforms(self, img, angle, flip_h, flip_v, invert):
        # Rotate
        if angle != 0:
            img = img.rotate(angle, expand=True)

        # Flip horizontal
        if flip_h:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        # Flip vertical
        if flip_v:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)

        # Invert
        if invert:
            inv = Image.new("RGB", img.size)
            src_pix = img.load()
            inv_pix = inv.load()
            width, height = img.size
            for y in range(height):
                for x in range(width):
                    r, g, b = src_pix[x, y]
                    inv_pix[x, y] = (255 - r, 255 - g, 255 - b)
            img = inv

        return img

    # --------------------------------------------------------------------------------
    # Gradient Mapping
    # --------------------------------------------------------------------------------
    def apply_gradient(self, img):
        """
        Remaps grayscale intensity to a linear blend of gradient_colors[0] -> [1].
        """
        grayscale = img.convert("L")
        w, h = img.size
        out_img = Image.new("RGB", (w, h))
        c1 = self.gradient_colors[0]
        c2 = self.gradient_colors[1]

        for y in range(h):
            for x in range(w):
                val = grayscale.getpixel((x, y))
                t = val / 255.0
                r = int((1 - t) * c1[0] + t * c2[0])
                g = int((1 - t) * c1[1] + t * c2[1])
                b = int((1 - t) * c1[2] + t * c2[2])
                out_img.putpixel((x, y), (r, g, b))

        return out_img

    # --------------------------------------------------------------------------------
    # Automated Random Exploration
    # --------------------------------------------------------------------------------
    def explore_random(self):
        """
        Generates multiple random textures in a grid. It ignores the current layer stack
        and simply picks random pattern & seed for demonstration.
        """
        count = max(1, min(16, self.explore_count.get()))
        explore_window = tk.Toplevel(self.master)
        explore_window.title("Exploration Results")

        size_str = self.selected_size.get()
        w, h = map(int, size_str.split("x"))

        grid_size = int(math.ceil(math.sqrt(count)))

        for i in range(count):
            random_pattern = random.choice(self.pattern_options)
            random_seed = random.randint(0, 99999)

            temp_layer = Layer(pattern_name=random_pattern, seed=random_seed)
            result_img = self.generate_layer_image(temp_layer, w, h)
            # Apply the final gradient mapping for consistency
            result_img = self.apply_gradient(result_img)

            # Show in 128×128
            preview_img = result_img.resize((128, 128), Image.NEAREST)
            tk_img = ImageTk.PhotoImage(preview_img)
            label = ttk.Label(explore_window, image=tk_img)
            label.image = tk_img
            row_pos = i // grid_size
            col_pos = i % grid_size
            label.grid(row=row_pos, column=col_pos, padx=3, pady=3)

    # --------------------------------------------------------------------------------
    # Export
    # --------------------------------------------------------------------------------
    def export_texture(self):
        if self.generated_image is None:
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg"),
                ("BMP files", "*.bmp"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            self.generated_image.save(file_path)


# ------------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = TextureGeneratorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
