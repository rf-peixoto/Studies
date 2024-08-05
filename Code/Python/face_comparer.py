# INSTRUCTIONS:

# 1. Download dependencies:
# pip install opencv-python dlib numpy

# 2. Find and download dlib shape predictor model:
# wget http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2 && bzip2 -d shape_predictor_68_face_landmarks.dat.bz2

import cv2
import dlib
import numpy as np
import os
from scipy.spatial import distance

# Initialize dlib's face detector and facial landmark predictor
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")

def extract_facial_features(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = detector(gray)
    if len(faces) == 0:
        return None
    landmarks = predictor(gray, faces[0])
    features = []
    for n in range(0, 68):
        x = landmarks.part(n).x
        y = landmarks.part(n).y
        features.append((x, y))
    return np.array(features)

def calculate_similarity(features1, features2):
    if features1 is None or features2 is None:
        return 0
    euclidean_distances = [distance.euclidean(features1[i], features2[i]) for i in range(0, 68)]
    similarity = 100 - np.mean(euclidean_distances)
    return max(0, similarity)

def process_images(directory):
    images = []
    for file in os.listdir(directory):
        if file.endswith(".jpg") or file.endswith(".png"):
            image = cv2.imread(os.path.join(directory, file))
            if image is not None:
                images.append(image)
    return images

def main(directory):
    images = process_images(directory)
    if len(images) < 2:
        print("Please provide at least two images for comparison.")
        return
    features_list = [extract_facial_features(image) for image in images]
    scores = []
    for i in range(len(features_list)):
        for j in range(i + 1, len(features_list)):
            score = calculate_similarity(features_list[i], features_list[j])
            scores.append(score)
            print(f"Similarity score between image {i+1} and image {j+1}: {score}")
    if scores:
        avg_score = np.mean(scores)
        print(f"Average similarity score: {avg_score}")

if __name__ == "__main__":
    directory = "imgs"
    main(directory)

