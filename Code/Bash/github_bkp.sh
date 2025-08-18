# https://github.com/settings/personal-access-tokens

curl -H "Authorization: token TOKEN" \
    "https://api.github.com/users/USERNAME/repos?type=owner&per_page=100" | \
    jq -r '.[] | select(.fork == false) | .ssh_url' > repos.txt

while read repo; do
    git clone "$repo"
done < repos.txt
