import argparse
import os
import numpy as np
import faiss
import cv2
import librosa
from PIL import Image
import torch
import torchvision.transforms as transforms
import torchvision.models as models

# Image embedding using a pre-trained ResNet50 model with a linear projection to 512 dimensions.
class ImageEmbedder:
    def __init__(self, device='cpu'):
        self.device = device
        self.model = models.resnet50(pretrained=True)
        # Remove the final classification layer.
        self.model.fc = torch.nn.Identity()
        self.model.eval()
        self.model.to(device)
        # Define a linear projection layer to reduce dimensionality from 2048 to 512.
        self.projection = torch.nn.Linear(2048, 512)
        self.projection.eval()
        self.projection.to(device)
        for param in self.projection.parameters():
            param.requires_grad = False
        
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])
        ])
    
    def embed_pil(self, image):
        if image.mode != 'RGB':
            image = image.convert('RGB')
        img_tensor = self.transform(image).unsqueeze(0).to(self.device)
        with torch.no_grad():
            features = self.model(img_tensor)
            embedding = self.projection(features)
        return embedding.cpu().numpy().flatten().astype('float32')
    
    def embed(self, image_path):
        image = Image.open(image_path)
        return self.embed_pil(image)

# Audio embedding that computes MFCC features and projects them to 512 dimensions using a fixed random projection.
class AudioEmbedder:
    def __init__(self, sr=22050):
        self.sr = sr
        # Fixed random projection parameters.
        self.W = np.random.randn(512, 40).astype('float32')
        self.b = np.random.randn(512).astype('float32')
    
    def embed(self, audio_path):
        y, sr = librosa.load(audio_path, sr=self.sr)
        # Compute 40 MFCC features.
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40)
        mfcc_avg = np.mean(mfcc, axis=1)  # Resulting shape: (40,)
        # Project the averaged MFCC vector to 512 dimensions.
        embedding = np.dot(self.W, mfcc_avg) + self.b
        return embedding.astype('float32')

# Video embedding that samples frames and averages image embeddings.
class VideoEmbedder:
    def __init__(self, image_embedder, frame_sampling_rate=30):
        self.image_embedder = image_embedder
        self.frame_sampling_rate = frame_sampling_rate
    
    def embed(self, video_path):
        cap = cv2.VideoCapture(video_path)
        embeddings = []
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % self.frame_sampling_rate == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                embedding = self.image_embedder.embed_pil(pil_image)
                embeddings.append(embedding)
            frame_count += 1
        cap.release()
        if not embeddings:
            raise ValueError("No frames extracted from video.")
        avg_embedding = np.mean(np.stack(embeddings), axis=0)
        return avg_embedding.astype('float32')

# Determines the file type and calls the appropriate embedding function.
def vectorize_file(file_path, device='cpu'):
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png', '.bmp']:
        image_embedder = ImageEmbedder(device=device)
        return image_embedder.embed(file_path)
    elif ext in ['.mp3', '.wav', '.flac', '.ogg']:
        audio_embedder = AudioEmbedder()
        return audio_embedder.embed(file_path)
    elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
        image_embedder = ImageEmbedder(device=device)
        video_embedder = VideoEmbedder(image_embedder)
        return video_embedder.embed(file_path)
    else:
        raise ValueError("Unsupported file type: " + ext)

# Creates a new FAISS index or loads an existing one.
def create_or_load_index(db_path, dimension=512):
    if os.path.exists(db_path):
        index = faiss.read_index(db_path)
    else:
        index = faiss.IndexFlatL2(dimension)
    return index

# Saves the FAISS index to disk.
def save_index(index, db_path):
    faiss.write_index(index, db_path)

# Adds a vector to the FAISS index.
def add_vector_to_index(index, vector):
    vector = np.expand_dims(vector, axis=0)
    index.add(vector)

# Searches the FAISS index for the k nearest neighbors.
def search_index(index, query_vector, k=5):
    query_vector = np.expand_dims(query_vector, axis=0)
    distances, indices = index.search(query_vector, k)
    return distances, indices

def main():
    parser = argparse.ArgumentParser(description='Multimedia Search Engine Script')
    parser.add_argument('--input', type=str, help='Path to input multimedia file.')
    parser.add_argument('--db', type=str, required=True, help='Path to the vectorial database file.')
    parser.add_argument('--search', action='store_true', help='Perform search instead of indexing the input file.')
    parser.add_argument('--device', type=str, default='cpu', help='Device for image embedding (cpu or cuda).')
    args = parser.parse_args()
    
    # Create or load the FAISS index.
    index = create_or_load_index(args.db, dimension=512)
    
    if args.input is None:
        print("No input file provided.")
        return
    
    # Convert the multimedia file into a 512-dimensional vector.
    vector = vectorize_file(args.input, device=args.device)
    
    if args.search:
        distances, indices = search_index(index, vector)
        print("Search results:")
        for dist, idx in zip(distances[0], indices[0]):
            print(f"Index: {idx}, Distance: {dist}")
    else:
        add_vector_to_index(index, vector)
        save_index(index, args.db)
        print("File indexed successfully.")

if __name__ == '__main__':
    main()
