# First File
for i in $(ls); do cd $i && ./../../pngquant.sh && cd ..;done

# pngquant.sh file:
remove="min."
for i in $(ls * | grep .png)
do
  pngquant $i --output min.$i --nofs --strip --speed=1
done;

for i in  "$remove"*;do mv "$i" "${i#"$remove"}";done
