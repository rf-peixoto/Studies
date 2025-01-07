jq '.. | select(type == "object" or type == "array") | select(tostring | contains("$1"))' file.json
