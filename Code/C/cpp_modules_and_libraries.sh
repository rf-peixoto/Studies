# tools.cpp : example module
# Compile modules:
c++ -std=c++17 -c tools.cpp

# Turn modules into libraries:
ar rcs libtools.a tools.o # <other_modules>

# Compile main application:
c++ -std=c++17 -c main.cpp

# Link main application to the libraries:
c++ -std=c++17 main.o -L . -ltools -o main
