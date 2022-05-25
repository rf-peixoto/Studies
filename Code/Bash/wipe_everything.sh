# CAUTION!

for f in $(find * /):
do
  shred -f -n 16 -u -z $f;
done;
