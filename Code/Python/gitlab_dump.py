import os
import re
import argparse
import requests
import concurrent.futures
import time
import hashlib

# ANSI color codes
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def sanitize_name(name):
    """
    Replace characters not suitable for file names with underscores.
    """
    return re.sub(r"[^a-zA-Z0-9_\\-]", "_", name)

def get_top_level_groups(base_url, session):
    """
    Retrieve all top-level groups the user can access, paginated.
    """
    print(f"{BLUE}Retrieving top-level groups from '{base_url}'...{RESET}")
    groups = []
    page = 1
    while True:
        url = f"{base_url}/api/v4/groups?per_page=100&page={page}"
        response = session.get(url)
        if response.status_code != 200:
            raise Exception(f"Error retrieving top-level groups (HTTP {response.status_code}).")
        batch = response.json()
        if not batch:
            break
        groups.extend(batch)
        page += 1
    print(f"{GREEN}Found {len(groups)} top-level groups.{RESET}")
    return groups

def get_subgroups_for_group(base_url, session, group_id):
    """
    Retrieve subgroups for a given group, paginated.
    """
    subgroups = []
    page = 1
    while True:
        url = f"{base_url}/api/v4/groups/{group_id}/subgroups?per_page=100&page={page}"
        response = session.get(url)
        if response.status_code != 200:
            raise Exception(f"Error retrieving subgroups for group {group_id} (HTTP {response.status_code}).")
        batch = response.json()
        if not batch:
            break
        subgroups.extend(batch)
        page += 1
    return subgroups

def get_all_groups_and_subgroups(base_url, session):
    """
    Retrieve all groups (top-level) plus nested subgroups using a breadth-first approach.
    """
    all_groups = get_top_level_groups(base_url, session)
    i = 0
    while i < len(all_groups):
        group = all_groups[i]
        group_id = group["id"]
        group_name = group["name"]
        try:
            subs = get_subgroups_for_group(base_url, session, group_id)
        except Exception as e:
            print(f"{RED}Error retrieving subgroups for '{group_name}': {e}{RESET}")
            i += 1
            continue

        for sub in subs:
            sub_id = sub["id"]
            # Avoid duplicates by checking if sub_id is already in all_groups
            if not any(g["id"] == sub_id for g in all_groups):
                all_groups.append(sub)

        i += 1

    print(f"{GREEN}Total groups (including subgroups): {len(all_groups)}{RESET}")
    return all_groups

def get_projects_for_group(base_url, session, group_id, group_name):
    """
    Retrieve all projects within a given group or subgroup, paginated.
    """
    print(f"{BLUE}Retrieving projects for group '{group_name}' (ID: {group_id})...{RESET}")
    projects = []
    page = 1
    while True:
        url = f"{base_url}/api/v4/groups/{group_id}/projects?per_page=100&page={page}"
        response = session.get(url)
        if response.status_code != 200:
            raise Exception(
                f"Error retrieving projects for group {group_id} (HTTP {response.status_code})."
            )
        batch = response.json()
        if not batch:
            break
        projects.extend(batch)
        page += 1
    print(f"{GREEN}Found {len(projects)} projects in group '{group_name}'.{RESET}")
    return projects

def download_project_archive(base_url, session, group_name, project, output_dir):
    """
    Downloads the ZIP archive of the default branch for the specified project.
    Key points:
      - Never skips existing files.
      - Incorporates a short hash of the archive URL to ensure uniqueness if names would collide.
      - Uses local retry logic for network issues.
    Returns True if successful, False otherwise.
    """
    project_id = project["id"]
    project_name = project["name"]
    sanitized_project_name = sanitize_name(project_name)
    default_branch = project.get("default_branch", None)

    if not default_branch:
        # Project has no default branch; treat as a "success" since there's nothing to download.
        print(f"{YELLOW}Skipping project '{project_name}' in group '{group_name}' (no default branch).{RESET}")
        return True

    # Create a subfolder for this group
    sanitized_group_name = sanitize_name(group_name)
    group_folder = os.path.join(output_dir, sanitized_group_name)
    os.makedirs(group_folder, exist_ok=True)

    # Construct the archive URL
    archive_url = f"{base_url}/api/v4/projects/{project_id}/repository/archive?sha={default_branch}"

    # Create a short hash from the archive_url to ensure unique file names
    hasher = hashlib.md5(archive_url.encode("utf-8"))
    short_hash = hasher.hexdigest()[:8]
    filename = f"{sanitized_project_name}_{short_hash}.zip"
    download_path = os.path.join(group_folder, filename)

    # Local retry logic
    max_attempts = 3
    response = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(archive_url, stream=True, timeout=15)
            if response.status_code == 200:
                break  # Successfully fetched
            else:
                print(f"{RED}HTTP {response.status_code} for '{project_name}' (Attempt {attempt}/{max_attempts}).{RESET}")
        except requests.exceptions.RequestException as e:
            print(f"{RED}Network error for '{project_name}' (Attempt {attempt}/{max_attempts}): {e}{RESET}")
        # Optional short pause before retry
        if attempt < max_attempts:
            time.sleep(3)

    if not response or response.status_code != 200:
        print(f"{RED}Failed to download archive for project '{project_name}' in group '{group_name}' after retries.{RESET}")
        return False

    # Write the archive file
    try:
        with open(download_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"{GREEN}Downloaded archive for project '{project_name}' in group '{group_name}' to '{filename}'.{RESET}")
        return True
    except Exception as e:
        print(f"{RED}Error writing archive for '{project_name}' in group '{group_name}': {e}{RESET}")
        return False

def download_in_parallel(base_url, session, targets, output_dir, max_workers):
    """
    Attempts parallel downloads of all (group_name, project) in 'targets'.
    Returns a tuple (success_list, failure_list).
    """
    success_list = []
    failure_list = []

    total = len(targets)
    completed = 0

    print(f"{BLUE}Starting parallel downloads for {total} repositories...{RESET}")

    # Parallel download with ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {
            executor.submit(download_project_archive, base_url, session, grp, prj, output_dir): (grp, prj)
            for (grp, prj) in targets
        }
        for future in concurrent.futures.as_completed(future_to_target):
            grp_name, prj_data = future_to_target[future]
            prj_name = prj_data["name"]
            completed += 1
            try:
                result = future.result()
                if result:
                    success_list.append((grp_name, prj_name))
                else:
                    failure_list.append((grp_name, prj_data))
            except Exception as exc:
                # Unexpected error while downloading
                print(f"{RED}Exception while downloading '{prj_name}' in group '{grp_name}': {exc}{RESET}")
                failure_list.append((grp_name, prj_data))
            
            # Manual progress counter
            print(f"{YELLOW}Progress: {completed} / {total}{RESET}")

    return success_list, failure_list

def main():
    parser = argparse.ArgumentParser(description="Download GitLab project archives in parallel, including subgroups.")
    parser.add_argument("--gitlab-url", default="https://gitlab.com", help="Base URL for GitLab, e.g. 'https://gitlab.example.com'. Default: 'https://gitlab.com'")
    parser.add_argument("--token", required=False, help="Personal Access Token with 'api' scope (or equivalent).")
    parser.add_argument("--output-dir", default="gitlab_archives", help="Directory to store downloaded archives (default: 'gitlab_archives').")
    parser.add_argument("--max-workers", type=int, default=4, help="Number of parallel download threads (default: 4).")
    args = parser.parse_args()

    # Basic validations for better UX
    if not args.token or not args.token.strip():
        print(f"{RED}Error: --token cannot be empty or missing.{RESET}")
        return
    if not args.gitlab_url.startswith("http"):
        print(f"{RED}Error: --gitlab-url must start with 'http' or 'https'. You provided: {args.gitlab_url}{RESET}")
        return

    # Prepare session with keep-alive
    session = requests.Session()
    session.headers.update({
        "Private-Token": args.token.strip(),
        "Connection": "keep-alive"
    })

    # 1. Fetch all groups (including subgroups)
    try:
        groups = get_all_groups_and_subgroups(args.gitlab_url, session)
        if not groups:
            print(f"{YELLOW}No groups found or no access.{RESET}")
            return
    except Exception as e:
        print(f"{RED}Failed to retrieve groups: {e}{RESET}")
        return

    # 2. Collect all (group_name, project) pairs
    all_targets = []
    for group in groups:
        group_name = group["name"]
        group_id = group["id"]
        try:
            projects = get_projects_for_group(args.gitlab_url, session, group_id, group_name)
            for project in projects:
                all_targets.append((group_name, project))
        except Exception as e:
            print(f"{RED}Failed to retrieve projects for group '{group_name}': {e}{RESET}")

    # 3. Initial attempt
    successes, failures = download_in_parallel(
        args.gitlab_url, session, all_targets, args.output_dir, args.max_workers
    )

    # 4. Retry loop for failures
    attempt = 1
    while failures:
        print(f"\n{YELLOW}--- Retry Attempt {attempt} for {len(failures)} failures ---{RESET}")
        new_successes, new_failures = download_in_parallel(
            args.gitlab_url, session, failures, args.output_dir, args.max_workers
        )

        if not new_failures:
            # All succeeded on this retry
            successes.extend(new_successes)
            failures = []
            break

        # If no progress was made (no fewer failures after retry), stop
        if len(new_failures) == len(failures):
            print(f"{RED}No progress made on retry. Stopping further attempts.{RESET}")
            successes.extend(new_successes)
            failures = new_failures
            break

        successes.extend(new_successes)
        failures = new_failures
        attempt += 1

    # 5. Summaries (color-coded and structured)
    print(f"\n{BLUE}--- Download Summary ---{RESET}")
    print(f"{GREEN}Successful downloads: {len(successes)}{RESET}")
    for grp_name, prj_name in successes:
        print(f"  - {grp_name} :: {prj_name}")

    if failures:
        print(f"{RED}Failed downloads: {len(failures)}{RESET}")
        for grp_name, prj_data in failures:
            print(f"  - {grp_name} :: {prj_data['name']}")
    else:
        print(f"{GREEN}All downloads succeeded.{RESET}")

if __name__ == "__main__":
    main()
