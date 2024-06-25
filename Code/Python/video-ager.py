# pip install numpy opencv-python moviepy pydub

import numpy as np
import cv2
import random
import sys
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip
from pydub import AudioSegment
import os
import uuid

# Function to degrade video quality to look like VHS
def degrade_video(input_path, output_path, resolution=(320, 240), fps=30):
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
        frame = cv2.GaussianBlur(frame, (3, 3), 0)
        
        # Add random noise
        noise = np.random.normal(0, 10, frame.shape).astype(np.uint8)
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
def degrade_audio(input_path, output_path):
    audio = AudioSegment.from_file(input_path)
    audio = audio.low_pass_filter(3000).high_pass_filter(100)
    
    # Generate white noise using numpy
    noise = (np.random.normal(0, 1, len(audio.get_array_of_samples())) * 50).astype(np.int16)
    noise_audio = AudioSegment(
        noise.tobytes(), 
        frame_rate=audio.frame_rate,
        sample_width=audio.sample_width, 
        channels=audio.channels
    )
    
    combined = audio.overlay(noise_audio)
    combined.export(output_path, format="wav")

# Function to combine degraded video and audio
def combine_video_audio(video_path, audio_path, output_path):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    final_clip = video.set_audio(audio)
    final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac')

# Main function to process the video
def process_video(input_video):
    unique_id = uuid.uuid4().hex
    degraded_video_path = f"degraded_video_{unique_id}.mp4"
    degraded_audio_path = f"degraded_audio_{unique_id}.wav"
    final_output_path = f"aged_video_{unique_id}.mp4"
    
    degrade_video(input_video, degraded_video_path)
    degrade_audio(input_video, degraded_audio_path)
    combine_video_audio(degraded_video_path, degraded_audio_path, final_output_path)
    
    os.remove(degraded_video_path)
    os.remove(degraded_audio_path)
    
    print(f"Processed video saved as {final_output_path}")

# Example usage
input_video = sys.argv[1]  # Replace with your input video file
process_video(input_video)
