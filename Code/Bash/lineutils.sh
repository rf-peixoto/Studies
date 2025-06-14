# Remove lines greater than N
sed '/^.\{N\}./d' input.txt > output.txt
