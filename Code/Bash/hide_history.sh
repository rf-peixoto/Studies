echo "" > /var/log/auth.log
echo "" > ~/.bash_history
rm ~/.bash_history -rf
history -c
export HISTFILESIZE=0
export HISTSIZE=0
kill -9 $$
