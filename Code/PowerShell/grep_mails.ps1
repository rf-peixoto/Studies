Get-ChildItem | Select-String -Pattern "@bancopan.com.br" | Out-File output.txt -Append
