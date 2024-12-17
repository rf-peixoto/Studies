gpg --delete-secret-keys --yes $(gpg --list-secret-keys --with-colons | grep '^sec' | cut -d':' -f5) && gpg --delete-keys --yes $(gpg --list-keys --with-colons | grep '^pub' | cut -d':' -f5)
