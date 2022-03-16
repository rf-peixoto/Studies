# Ref: https://adamtheautomator.com/openssh-windows/

## Set network connection protocol to TLS 1.2
## Define the OpenSSH latest release url
 $url = 'https://github.com/PowerShell/Win32-OpenSSH/releases/latest/'
## Create a web request to retrieve the latest release download link
 $request = [System.Net.WebRequest]::Create($url)
 $request.AllowAutoRedirect=$false
 $response=$request.GetResponse()
 $source = $([String]$response.GetResponseHeader("Location")).Replace('tag','download') + '/OpenSSH-Win64.zip'
## Download the latest OpenSSH for Windows package to the current working directory
 $webClient = [System.Net.WebClient]::new()
 $webClient.DownloadFile($source, (Get-Location).Path + '\OpenSSH-Win64.zip')

# Extract the ZIP to a temporary location
 Expand-Archive -Path .\OpenSSH-Win64.zip -DestinationPath ($env:temp) -Force
# Move the extracted ZIP contents from the temporary location to C:\Program Files\OpenSSH\
 Move-Item "$($env:temp)\OpenSSH-Win64" -Destination "C:\Program Files\OpenSSH\" -Force
# Unblock the files in C:\Program Files\OpenSSH\
 Get-ChildItem -Path "C:\Program Files\OpenSSH\" | Unblock-File

 & 'C:\Program Files\OpenSSH\install-sshd.ps1'
 
 ## changes the sshd service's startup type from manual to automatic.
 Set-Service sshd -StartupType Automatic
 ## starts the sshd service.
 Start-Service sshd
 
 New-NetFirewallRule -Name sshd -DisplayName 'SSH' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
 
 ## Configuring the public key auth:
 #New-Item -Type File -Path C:\ProgramData\ssh\administrators_authorized_keys
 #get-acl C:\ProgramData\ssh\ssh_host_dsa_key | set-acl C:\ProgramData\ssh\administrators_authorized_keys
# Read the public key
# $public_key = Get-Content ~/.ssh/id_rsa.pub
# Append the public key to the administrators_authorized_keys on the server using ssh.
# ssh june@40.177.77.227 "'$($public_key)' | Out-File C:\ProgramData\ssh\administrators_authorized_keys -Encoding UTF8 -Append"


