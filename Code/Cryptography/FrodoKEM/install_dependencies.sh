#!/usr/bin/env bash
set -e

# This script installs the Open Quantum Safe libraries and Python bindings 
# for Python  on Fedora, with FrodoKEM (and other KEMs) enabled.

# 1. Update system packages
sudo dnf -y update

# 2. Install build dependencies and Python  development files
sudo dnf install -y \
    git \
    cmake \
    ninja-build \
    gcc \
    gcc-c++ \
    openssl-devel \
    python \
    python-devel \
    make

# 3. Create a temporary build directory
mkdir -p ~/oqs_build
cd ~/oqs_build

# 4. Clone and build liboqs from source
if [ ! -d liboqs ]; then
    git clone https://github.com/open-quantum-safe/liboqs.git
fi
cd liboqs
git pull

mkdir -p build
cd build
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release ..
ninja

# (Optional) Run tests to confirm build integrity
ctest --output-on-failure

# Go back to the build workspace
cd ../..

# 5. Clone and install the Python bindings from liboqs-python
if [ ! -d liboqs-python ]; then
    git clone https://github.com/open-quantum-safe/liboqs-python.git
fi
cd liboqs-python
git pull

# Point liboqs-python to the previously built liboqs artifacts
export OQS_DIST_REL=~/oqs_build/liboqs/build

# Upgrade pip, setuptools, wheel for python
python -m pip install --upgrade pip setuptools wheel

# Install the liboqs Python bindings
python -m pip install .

# 6. Verify installation and list available KEMs (including FrodoKEM)
python -c "import oqs; print('OQS version:', oqs.__version__); print('Enabled KEMs:', oqs.KEMs.get_enabled_KEMs())"

echo
echo "=================================================================="
echo "Open Quantum Safe libraries successfully installed for Python ."
echo "FrodoKEM should be listed in the Enabled KEMs above."
echo "=================================================================="
