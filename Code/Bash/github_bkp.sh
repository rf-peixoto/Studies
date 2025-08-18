#!/bin/bash

# === User Settings ===
USERNAME="USERNAME"           # CHANGE THIS to your GitHub username
TOKEN=""         # https://github.com/settings/personal-access-tokens

# === Script Start ===

API_URL="https://api.github.com/users/$USERNAME/repos?type=owner&per_page=100"
PAGE=1

echo "Fetching repositories for user: $USERNAME..."

while : ; do
  RESP=$(curl -s -H "Authorization: token $TOKEN" "$API_URL&page=$PAGE")
  REPO_COUNT=$(echo "$RESP" | jq length)
  if [[ "$REPO_COUNT" -eq 0 ]]; then
    break
  fi

  echo "$RESP" | jq -r '.[] | select(.fork==false) | .name' >> my_repos.txt
  ((PAGE++))
done

echo "Repository list saved to my_repos.txt"
echo "Starting download of ZIP archives..."

mkdir -p my_repos_zips

while read repo; do
  if [[ -n "$repo" ]]; then
    echo "Downloading $repo..."
    curl -L -H "Authorization: token $TOKEN" \
      -o "my_repos_zips/${repo}.zip" \
      "https://api.github.com/repos/$USERNAME/$repo/zipball"
  fi
done < my_repos.txt

echo "All repositories downloaded as ZIPs in the my_repos_zips directory."
