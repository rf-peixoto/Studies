# Clone liboqs
git clone https://github.com/open-quantum-safe/liboqs.git
cd liboqs

# Create a build directory
mkdir build
cd build

# Configure the build with FrodoKEM enabled
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DOQS_ENABLE_KEM_FRODOKEM_1344=ON ..

# Build the library
ninja
echo $(pwd)

cd ../..
# Clone liboqs-python
git clone https://github.com/open-quantum-safe/liboqs-python.git
cd liboqs-python

# Set the path to the built liboqs library
export OQS_DIST_REL=/home/User/Code/Tests/liboqs/build

# Install the Python bindings
pip install .
