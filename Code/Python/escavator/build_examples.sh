# Build the image
docker build -t escavator:latest .

# Run a scan
docker run --rm -v "$(pwd):/app" escavator:latest sample.exe --disasm-filter --top 5

# Inject into the first suitable cave
docker run --rm -v "$(pwd):/app" escavator:latest sample.exe --inject shellcode.bin --redirect-ep --update-checksum

# Force a new section on ELF
docker run --rm -v "$(pwd):/app" escavator:latest hello --inject shellcode.bin --add-section --redirect-ep
