# Generate secure seed (run once)
export MESH_C2_SECRET=$(openssl rand -base64 24)

# Configure allowed nodes
export ALLOWED_NODES="123456,789012"
