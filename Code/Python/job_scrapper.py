import requests, json

# API stuff
keys = ['date', 'company', 'position', 'tags', 'location', 'url']

# Filter keys
wanted_tags = ['python', 'pentest', 'phishing']

# Get data:
def get_jobs():
    response = requests.get("https://remoteok.io/api")
    jobs_found = response.json()
    options = []
    for job in jobs_found:
        # Filter:
        j = {k: v for k, v in job.items() if k in keys}
        if j:
            tags = job.get('tags')
            tags = {tag.lower() for tag in tags}
            # Add job as a option:
            if tags.intersection(wanted_tags):
                options.append(job)
    return options

for opt in get_jobs():
    print("===================================")
    print("Company: {0}".format(opt['company']))
    print("Position: {0}".format(opt['position']))
    print("Salary: ${0}~${1}".format(opt['salary_min'], opt['salary_max']))
    print("URL {0}: ".format(opt['apply_url']))
