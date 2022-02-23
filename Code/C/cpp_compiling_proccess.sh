# $1 must be a valid file.cpp
mkdir Main
# 1. Preprocess:
c++ -E $1 > Main/main.i
# 2. Compilation:
cd Main
c++ -S main.i # Assembly code
# 3. Assembly:
c++ -c main.s
# 4. Linking:
c++ main.o -o output
