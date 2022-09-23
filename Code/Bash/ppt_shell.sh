# Create shell:
echo ["COMMAND"] | ppt | base64 -d

# Run:
echo [CODE] | base64 -d | ppt -d | sh
