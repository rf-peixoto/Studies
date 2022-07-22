# Ref: Antivirus Hacker's Handbook
# 1) Big zero-filled file:
dd if=/dev/zero bs=1024M count=1 > file
# 2) Compress as you like (7z, ZIP, etc). Here with bzip2:
dd if=/dev/zero bs=2048M count=1 | bzip2 -9 > file.bz2
# You can check the real size with wc:
LANG=C dd if=/dev/zero bs=2048M count=1 | bzip2 -9 | wc -c
# Now, using 7z:
LANG=C dd if=/dev/zero bs=2048M count=1 > 2gb_dummy
7z a -t7z -mx9 test.7z 2gb_dummy
# Now with XZ:
7z a -txz -mx9 test.xz 2gb_dummy
