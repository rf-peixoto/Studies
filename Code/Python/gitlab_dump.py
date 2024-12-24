import os
import re
import requests

# Base GitLab URL, e.g., "https://gitlab.example.com"
GITLAB_URL = "https://gitlab.example.com"
# Personal Access Token (must have sufficient privileges, e.g. api scope)
PERSONAL_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
# Destination folder for downloaded archives
DOWNLOAD_FOLDER = "gitlab_archives"

def sanitize_name(name):
    """
    Replaces characters not suitable for file names with underscores.
    """
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)

def get_all_groups(base_url, token):
    """
    Retrieve all groups the user can access. The results are paginated.
    """
    groups = []
    page = 1
    while True:
        url = f"{base_url}/api/v4/groups?per_page=100&page={page}"
        response = requests.get(url, headers={"Private-Token": token})
        if response.status_code != 200:
            raise Exception(f"Error retrieving groups (HTTP {response.status_code}).")
        batch = response.json()
        if not batch:
            break
        groups.extend(batch)
        page += 1
    return groups

def get_projects_for_group(base_url, token, group_id):
    """
    Retrieve all projects within a given group. The results are paginated.
    """
    projects = []
    page = 1
    while True:
        url = f"{base_url}/api/v4/groups/{group_id}/projects?per_page=100&page={page}"
        response = requests.get(url, headers={"Private-Token": token})
        if response.status_code != 200:
            raise Exception(
                f"Error retrieving projects for group {group_id} (HTTP {response.status_code})."
            )
        batch = response.json()
        if not batch:
            break
        projects.extend(batch)
        page += 1
    return projects

def download_project_archive(base_url, token, project):
    """
    Downloads the ZIP archive of the default branch for the specified project.
    Returns True if successful, False otherwise.
    """
    project_id = project["id"]
    project_name = project["name"]
    sanitized_project_name = sanitize_name(project_name)
    
    default_branch = project.get("default_branch", None)
    if not default_branch:
        print(f"Skipping project '{project_name}' (no default branch).")
        return True  # Not a failure; just no archive to download
    
    # Ensure download folder exists
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
    archive_url = f"{base_url}/api/v4/projects/{project_id}/repository/archive?sha={default_branch}"
    response = requests.get(archive_url, headers={"Private-Token": token}, stream=True)
    
    if response.status_code != 200:
        print(
            f"Failed to download archive for '{project_name}' "
            f"(HTTP {response.status_code})."
        )
        return False
    
    filename = f"{sanitized_project_name}.zip"
    download_path = os.path.join(DOWNLOAD_FOLDER, filename)
    try:
        with open(download_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"Downloaded archive for '{project_name}'.")
        return True
    except Exception as e:
        print(f"Error writing archive for '{project_name}': {e}")
        return False

def main():
    """
    1. Retrieve all groups.
    2. For each group, list its projects.
    3. Attempt to download each project's default branch archive.
    4. Retry failed downloads until all succeed or no progress is possible.
    """
    try:
        groups = get_all_groups(GITLAB_URL, PERSONAL_ACCESS_TOKEN)
        if not groups:
            print("No groups found or no access.")
            return
    except Exception as e:
        print(f"Failed to retrieve groups: {e}")
        return
    
    # Build a list of (group_name, project) to download
    download_targets = []
    for group in groups:
        group_name = group["name"]
        group_id = group["id"]
        try:
            projects = get_projects_for_group(GITLAB_URL, PERSONAL_ACCESS_TOKEN, group_id)
            for project in projects:
                download_targets.append((group_name, project))
        except Exception as e:
            print(f"Error retrieving projects for group '{group_name}': {e}")
    
    # Now attempt to download each target's archive
    failures = []
    successes = []
    
    for group_name, project in download_targets:
        project_name = project["name"]
        if download_project_archive(GITLAB_URL, PERSONAL_ACCESS_TOKEN, project):
            successes.append((group_name, project_name))
        else:
            failures.append((group_name, project))
    
    # Retry loop for failures until none remain or no progress is made
    attempt = 1
    while failures:
        print(f"\n--- Retry Attempt {attempt} for {len(failures)} failures ---")
        new_failures = []
        progress_made = False

        for group_name, project in failures:
            project_name = project["name"]
            if download_project_archive(GITLAB_URL, PERSONAL_ACCESS_TOKEN, project):
                successes.append((group_name, project_name))
                progress_made = True
            else:
                new_failures.append((group_name, project))
        
        if not new_failures:
            # All succeeded
            failures = []
            break
        if not progress_made:
            # No progress was made in this attempt, so stop to avoid an infinite loop
            print("No progress made on retry. Stopping.")
            failures = new_failures
            break
        
        failures = new_failures
        attempt += 1
    
    # Output final lists
    print("\n--- Download Summary ---")
    print(f"Successful downloads: {len(successes)}")
    for group_name, project_name in successes:
        print(f"  {group_name} :: {project_name}")
    
    if failures:
        print(f"Failed downloads: {len(failures)}")
        for group_name, project in failures:
            print(f"  {group_name} :: {project['name']}")
    else:
        print("All downloads succeeded.")

if __name__ == "__main__":
    main()
