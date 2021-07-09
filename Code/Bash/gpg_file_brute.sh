for i in $(cat $1):
do
  echo "Testing password: $i"
  echo "$i" | gpg --passphrase-fd 0 -q --batch --no-tty --output result.txt --decrypt file.gpg 2> /dev/null
done
