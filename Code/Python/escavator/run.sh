docker build -t escavator:latest .
docker run --rm -v "$(pwd):/app" escavator:latest [your arguments here]
