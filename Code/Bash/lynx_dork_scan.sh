!#/bin/bash

search="firefox"
target="$1"
google="https://google.com/search?q="
sites="pastebin.com" "trello.com"

echo "Teste"

for ste in ${$sites};
do
    $search $google+$site+$target 2> /dev/null;
done

