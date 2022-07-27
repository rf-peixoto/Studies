dd if=/dev/zero bs=1024M count=1 > $1
7z a -t7z -mx9 $1.7z $1
rm $1
