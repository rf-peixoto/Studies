# pip install numpy opencv-python moviepy pydub tkfilebrowser

import numpy as np
import cv2
import random
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment
import os
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox
from tkfilebrowser import askopenfilename

# Function to degrade video quality to look like VHS
def degrade_video(input_path, output_path, resolution=(320, 240), fps=30, blur_amount=3, noise_amount=10):
    cap = cv2.VideoCapture(input_path)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, resolution, isColor=True)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Resize frame
        frame = cv2.resize(frame, resolution)
        
        # Apply Gaussian blur
        frame = cv2.GaussianBlur(frame, (blur_amount, blur_amount), 0)
        
        # Add random noise
        noise = np.random.normal(0, noise_amount, frame.shape).astype(np.uint8)
        frame = cv2.addWeighted(frame, 0.9, noise, 0.1, 0)
        
        # Add VHS scan lines
        for i in range(0, resolution[1], 2):
            frame[i:i+1, :] = frame[i:i+1, :] // 2
        
        # Reduce color saturation
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hsv[:, :, 1] = hsv[:, :, 1] * 0.5
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        
        out.write(frame)
    
    cap.release()
    out.release()

# Function to degrade audio quality
def degrade_audio(input_path, output_path, low_pass=4000, high_pass=300, frame_rate=22050, volume_reduction=5):
    audio = AudioSegment.from_file(input_path)
    audio = audio.low_pass_filter(low_pass).high_pass_filter(high_pass)
    
    # Reduce sample rate to degrade quality slightly
    audio = audio.set_frame_rate(frame_rate)
    
    combined = audio - volume_reduction  # Reduce volume slightly to simulate old microphone
    combined.export(output_path, format="wav")

# Function to combine degraded video and audio
def combine_video_audio(video_path, audio_path, output_path):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path).set_duration(video.duration)
    final_clip = video.set_audio(audio)
    final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac')
    video.reader.close()
    video.audio.reader.close_proc()

# Function to process the video
def process_video(input_video, resolution, fps, blur_amount, noise_amount, low_pass, high_pass, frame_rate, volume_reduction):
    unique_id = uuid.uuid4().hex
    degraded_video_path = f"degraded_video_{unique_id}.mp4"
    degraded_audio_path = f"degraded_audio_{unique_id}.wav"
    final_output_path = f"aged_video_{unique_id}.mp4"
    
    degrade_video(input_video, degraded_video_path, resolution, fps, blur_amount, noise_amount)
    degrade_audio(input_video, degraded_audio_path, low_pass, high_pass, frame_rate, volume_reduction)
    combine_video_audio(degraded_video_path, degraded_audio_path, final_output_path)
    
    os.remove(degraded_video_path)
    os.remove(degraded_audio_path)
    
    messagebox.showinfo("Success", f"Processed video saved as {final_output_path}")

# GUI for user interaction
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("VHS Video Degrader")
        self.root.geometry("400x600")

        self.create_widgets()

    def create_widgets(self):
        tk.Label(self.root, text="VHS Video Degrader", font=("Arial", 16)).pack(pady=10)

        tk.Button(self.root, text="Select Video", command=self.select_video).pack(pady=5)
        self.input_path = tk.StringVar()
        tk.Entry(self.root, textvariable=self.input_path, width=50).pack(pady=5)

        tk.Label(self.root, text="Resolution (Width x Height)").pack(pady=5)
        self.resolution = tk.StringVar(value="320x240")
        tk.Entry(self.root, textvariable=self.resolution, width=20).pack(pady=5)

        tk.Label(self.root, text="Frame Rate (fps)").pack(pady=5)
        self.fps = tk.IntVar(value=30)
        tk.Entry(self.root, textvariable=self.fps, width=10).pack(pady=5)

        tk.Label(self.root, text="Blur Amount").pack(pady=5)
        self.blur_amount = tk.IntVar(value=3)
        tk.Entry(self.root, textvariable=self.blur_amount, width=10).pack(pady=5)

        tk.Label(self.root, text="Noise Amount").pack(pady=5)
        self.noise_amount = tk.IntVar(value=10)
        tk.Entry(self.root, textvariable=self.noise_amount, width=10).pack(pady=5)

        tk.Label(self.root, text="Audio Low Pass Filter (Hz)").pack(pady=5)
        self.low_pass = tk.IntVar(value=4000)
        tk.Entry(self.root, textvariable=self.low_pass, width=10).pack(pady=5)

        tk.Label(self.root, text="Audio High Pass Filter (Hz)").pack(pady=5)
        self.high_pass = tk.IntVar(value=300)
        tk.Entry(self.root, textvariable=self.high_pass, width=10).pack(pady=5)

        tk.Label(self.root, text="Audio Frame Rate").pack(pady=5)
        self.frame_rate = tk.IntVar(value=22050)
        tk.Entry(self.root, textvariable=self.frame_rate, width=10).pack(pady=5)

        tk.Label(self.root, text="Volume Reduction (dB)").pack(pady=5)
        self.volume_reduction = tk.IntVar(value=5)
        tk.Entry(self.root, textvariable=self.volume_reduction, width=10).pack(pady=5)

        tk.Button(self.root, text="Process Video", command=self.process_video).pack(pady=20)

    def select_video(self):
        file_path = askopenfilename(filetypes=[("MP4 files", "*.mp4")])
        if file_path:
            self.input_path.set(file_path)

    def process_video(self):
        input_video = self.input_path.get()
        resolution = tuple(map(int, self.resolution.get().split('x')))
        fps = self.fps.get()
        blur_amount = self.blur_amount.get()
        noise_amount = self.noise_amount.get()
        low_pass = self.low_pass.get()
        high_pass = self.high_pass.get()
        frame_rate = self.frame_rate.get()
        volume_reduction = self.volume_reduction.get()

        process_video(input_video, resolution, fps, blur_amount, noise_amount, low_pass, high_pass, frame_rate, volume_reduction)

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
