git log --format='%aN' | sort -u

# List by email:
git log | grep Author | cut -d " " -f 3
