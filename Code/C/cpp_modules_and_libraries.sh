# Compile modules:
c++ -std=c++17 -c module.cpp

# Turn modules into libraries:
ar rcs libtools.a module.o # <other_modules>

# Compile main application:
c++ -std=c++17 -c main.cpp

# Link main application to the libraries:
c++ -std=c++17 main.o -L . -ltools -o main
