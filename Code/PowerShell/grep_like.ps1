Get-ChildItem -Path . -Filter *.txt -Recurse | Select-String -Pattern "string"
