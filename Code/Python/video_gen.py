# pip install opencv-python numpy pydub moviepy

import numpy as np
import random
from pydub import AudioSegment
from pydub.generators import Sine
import moviepy.editor as mpe
import os
import uuid

# Function to generate a random beep sound
def generate_beep(duration_ms, frequency):
    return Sine(frequency).to_audio_segment(duration=duration_ms)

# Function to generate random frames
def generate_random_frames(width, height, total_frames, color=False):
    frames = []
    for _ in range(total_frames):
        if color:
            frame = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        else:
            frame = np.random.randint(0, 256, (height, width), dtype=np.uint8)
            frame = np.stack((frame,) * 3, axis=-1)  # Convert to 3 channels
        frames.append(frame)
    return frames

# Function to generate random beeps audio
def generate_random_audio(duration_sec, beep_interval, min_freq, max_freq):
    audio = AudioSegment.silent(duration=duration_sec * 1000)
    for i in range(0, duration_sec * 1000, beep_interval):
        if random.choice([True, False]):
            beep = generate_beep(100, random.randint(min_freq, max_freq))
            audio = audio.overlay(beep, position=i)
    return audio

# Customizable parameters
frame_width = 320
frame_height = 240
frame_rate = 24
duration_sec = 10
color_video = True
beep_interval = 850  # milliseconds
min_frequency = 400
max_frequency = 2000

# Generate random frames
total_frames = frame_rate * duration_sec
frames = generate_random_frames(frame_width, frame_height, total_frames, color=color_video)

# Create a moviepy video clip
video_clip = mpe.ImageSequenceClip(frames, fps=frame_rate)

# Generate audio with random beeps
audio = generate_random_audio(duration_sec, beep_interval, min_frequency, max_frequency)

# Create unique filenames
unique_id = uuid.uuid4().hex
wav_filename = f"random_noise_audio_{unique_id}.wav"
mp4_filename = f"random_noise_video_with_audio_{unique_id}.mp4"

# Export the audio
audio.export(wav_filename, format="wav")

# Load the audio file into moviepy
audio_clip = mpe.AudioFileClip(wav_filename)

# Set the audio to the video clip
final_clip = video_clip.set_audio(audio_clip)

# Write the final video file
final_clip.write_videofile(mp4_filename, codec='libx264')

# Remove the temporary wav file
os.remove(wav_filename)

print("Video generation completed.")

