import os
import re
import argparse
import requests
import concurrent.futures

def sanitize_name(name):
    """
    Replace characters not suitable for file names with underscores.
    """
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)

def get_all_groups(base_url, session):
    """
    Retrieve all groups the user can access. The results are paginated.
    """
    groups = []
    page = 1
    while True:
        url = f"{base_url}/api/v4/groups?per_page=100&page={page}"
        response = session.get(url)
        if response.status_code != 200:
            raise Exception(f"Error retrieving groups (HTTP {response.status_code}).")
        batch = response.json()
        if not batch:
            break
        groups.extend(batch)
        page += 1
    return groups

def get_projects_for_group(base_url, session, group_id):
    """
    Retrieve all projects within a given group. The results are paginated.
    """
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
    return projects

def download_project_archive(base_url, session, group_name, project, output_dir):
    """
    Downloads the ZIP archive of the default branch for the specified project.
    Returns True if successful, False otherwise.
    """
    project_id = project["id"]
    project_name = project["name"]
    sanitized_project_name = sanitize_name(project_name)
    default_branch = project.get("default_branch", None)
    if not default_branch:
        # Project has no default branch; treat as a "success" (nothing to download).
        print(f"Skipping project '{project_name}' in group '{group_name}' (no default branch).")
        return True

    # Create a subfolder for this group
    sanitized_group_name = sanitize_name(group_name)
    group_folder = os.path.join(output_dir, sanitized_group_name)
    os.makedirs(group_folder, exist_ok=True)

    archive_url = f"{base_url}/api/v4/projects/{project_id}/repository/archive?sha={default_branch}"
    response = session.get(archive_url, stream=True)
    if response.status_code != 200:
        print(
            f"Failed to download archive for project '{project_name}' "
            f"in group '{group_name}' (HTTP {response.status_code})."
        )
        return False

    # Save the archive file inside the group folder
    filename = f"{sanitized_project_name}.zip"
    download_path = os.path.join(group_folder, filename)
    try:
        with open(download_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"Downloaded archive for project '{project_name}' in group '{group_name}'.")
        return True
    except Exception as e:
        print(f"Error writing archive for '{project_name}' in group '{group_name}': {e}")
        return False

def download_in_parallel(base_url, session, targets, output_dir, max_workers):
    """
    Attempts parallel downloads of all (group_name, project) in 'targets'.
    Returns a tuple (success_list, failure_list).
    """
    success_list = []
    failure_list = []

    # Parallel download with ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {
            executor.submit(download_project_archive, base_url, session, grp, prj, output_dir): (grp, prj)
            for (grp, prj) in targets
        }
        for future in concurrent.futures.as_completed(future_to_target):
            grp_name, prj_data = future_to_target[future]
            prj_name = prj_data["name"]
            try:
                result = future.result()
                if result:
                    success_list.append((grp_name, prj_name))
                else:
                    failure_list.append((grp_name, prj_data))
            except Exception as exc:
                # Unexpected error while downloading
                print(f"Exception while downloading '{prj_name}' in group '{grp_name}': {exc}")
                failure_list.append((grp_name, prj_data))
    return success_list, failure_list

def main():
    parser = argparse.ArgumentParser(description="Download GitLab project archives in parallel.")
    parser.add_argument("--gitlab-url", default='https://gitlab.com', help="Base URL for GitLab, e.g. 'https://gitlab.example.com'")
    parser.add_argument("--token", required=True, help="Personal Access Token with 'api' scope (or equivalent).")
    parser.add_argument("--output-dir", default="downloads", help="Directory to store downloaded archives.")
    parser.add_argument("--max-workers", type=int, default=4, help="Number of parallel download threads.")
    args = parser.parse_args()

    # Prepare session with keep-alive
    session = requests.Session()
    session.headers.update({
        "Private-Token": args.token,
        "Connection": "keep-alive"
    })

    # Fetch all groups
    try:
        groups = get_all_groups(args.gitlab_url, session)
        if not groups:
            print("No groups found or no access.")
            return
    except Exception as e:
        print(f"Failed to retrieve groups: {e}")
        return

    # Collect all (group_name, project) pairs
    all_targets = []
    for group in groups:
        group_name = group["name"]
        group_id = group["id"]
        try:
            projects = get_projects_for_group(args.gitlab_url, session, group_id)
            for project in projects:
                all_targets.append((group_name, project))
        except Exception as e:
            print(f"Failed to retrieve projects for group '{group_name}': {e}")

    # Initial attempt
    successes, failures = download_in_parallel(args.gitlab_url, session, all_targets, args.output_dir, args.max_workers)

    attempt = 1
    while failures:
        print(f"\n--- Retry Attempt {attempt} for {len(failures)} failures ---")
        new_successes, new_failures = download_in_parallel(
            args.gitlab_url,
            session,
            failures,
            args.output_dir,
            args.max_workers
        )

        if not new_failures:
            # All succeeded this round
            successes.extend(new_successes)
            failures = []
            break

        if len(new_failures) == len(failures):
            # No progress was made, stop to avoid infinite loops
            print("No progress made on retry. Stopping further attempts.")
            successes.extend(new_successes)
            failures = new_failures
            break

        # Update for next iteration
        successes.extend(new_successes)
        failures = new_failures
        attempt += 1

    # Summaries
    print("\n--- Download Summary ---")
    print(f"Successful downloads: {len(successes)}")
    for grp_name, prj_name in successes:
        print(f"  {grp_name} :: {prj_name}")

    if failures:
        print(f"Failed downloads: {len(failures)}")
        for grp_name, prj_data in failures:
            print(f"  {grp_name} :: {prj_data['name']}")
    else:
        print("All downloads succeeded.")

if __name__ == "__main__":
    main()
