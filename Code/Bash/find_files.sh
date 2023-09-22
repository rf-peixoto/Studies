search="Stuff"

find . -type f -name "File.txt" > file_list.txt
for f in $(cat file_list.txt)
do
  grep search $f;
done
