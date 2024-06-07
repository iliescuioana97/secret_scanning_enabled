import requests
import argparse
import os

from utils import deep_get
from utils import get_token
from utils import print_rate_limit
from utils import retrieve_etag_value
from utils import update_etag_value
from utils import output_to_file
from utils import get_org_list
from utils import check_rate_limits

from multiprocessing import Pool
from time import sleep

MAX_RETRIES = 10


def parse_args():
    parser = argparse.ArgumentParser(
        prog="Scan utility for GH repository metadata",
        description="""Retrieves the status of the secret_scanning 
        GH feature for org repos""",
    )

    parser.add_argument(
        "org",
        help="Organization to scan or file path to organizations list.",
        type=str,
    )

    parser.add_argument(
        "-t",
        "--token",
        help="Github token for Github API Auth",
        type=str,
    )

    parser.add_argument(
        "-o",
        "--output",
        default=os.getcwd(),
        help="Path where results json should be stored.",
        type=str,
    )

    parser.add_argument(
        "-d",
        "--diff-timeframe",
        help="""Check if data has changed in this amount of hours.
        This only works for endpoints that return a last-modified header.""",
        type=int,
    )

    parser.add_argument(
        "-e",
        "--etag",
        help="""Check if data has changed through etags.
        This only works for endpoints that return an etag header.""",
        type=str,
    )

    args = parser.parse_args()
    return args


def get_repositories(org_name, headers, etag):
    endpoint = f"https://api.github.com/orgs/{org_name}/repos"
    results_per_page = 100  # max
    params = {"per_page": results_per_page, "page": 1}

    # Add ETag if exists to request headers to optimise request counts
    if etag:
        headers["If-None-Match"] = etag

    repos = []
    needs_update = True
    retries = 0

    while True:
        response = requests.get(endpoint, headers=headers, params=params)

        # Data has not been updated
        if response.status_code == 304:
            print(f"Data for org: {org_name} has not changed since the last request.")
            needs_update = False
            # https://stackoverflow.com/questions/18489441/github-api-conditional-requests-with-paging
            # If data changes, results for EVERY requested page contains
            # different ETag value compared to previous. As such, it should
            # be sufficient to store only the first page etag value and
            # break out of pagination request loop when the values match.
            break

        # Check if rate limits exceeded (Forbidden/Too many requests)
        if response.status_code in [403, 429]:
            # https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2022-11-28#exceeding-the-rate-limit
            exp_backoff, sleep_time = check_rate_limits(response.headers, retries)

            # Check if onto exponential backoff stage
            if exp_backoff:
                retries += 1
                if retries == MAX_RETRIES:
                    raise "Maximum limit of exp backoff retries exceeded."

            sleep(sleep_time)
            continue

        response.raise_for_status()

        # Update ETag value for organization in etag storage
        if params["page"] == 1:
            update_etag_value(org_name, response.headers["ETag"])

        # If the response is empty, break
        page_repos = response.json()
        if not page_repos:
            break

        repos.extend(page_repos)

        # Check if there should be a next page
        if len(page_repos) < results_per_page:
            break

        # Increment the page number
        params["page"] += 1

    return needs_update, repos


def parse_secret_scanning_info(repos):
    data = {}
    for repo in repos:
        # Get full repo name from metadata
        name = repo["full_name"]

        # As per Github API Documentation,in order to see the
        # security_and_analysis block for a repository you must
        # have admin permissions for it/be an owner/secmanager for
        # the organization that owns it.
        # This is a check to see if this data is missing, indicating
        # missing permissions or if it was successfully retrieve.
        ss_value = deep_get(repo, "security_and_analysis", "secret_scanning", "status")
        ss_enabled = ss_value if ss_value else "Missing Perms"

        data[name] = ss_enabled
    return data


def scan(org_name, token, output, etag):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Print rate limits info before requests
    print_rate_limit(headers)

    # Get all repos metadata for the organization
    try:
        needs_update, repos = get_repositories(org_name, headers, etag)
    except Exception as e:
        print(f"Error fetching repositories: {e}")
        return

    # Print rate limits info after requests
    print_rate_limit(headers)

    # Parse secret_scanning info from metadata
    data = parse_secret_scanning_info(repos)

    # Output to destination file
    if needs_update:
        output_to_file(org_name, data, output)


def scan_list(org_file, token, output):
    orgs = get_org_list(org_file)
    params = [(org, token, output, retrieve_etag_value(org)) for org in orgs]

    # No more than 100 concurrent requests are allowed
    with Pool(processes=3) as pool:
        results = pool.starmap(scan, params)


if __name__ == "__main__":
    args = parse_args()

    org = args.org
    token = get_token(args)
    output = args.output

    # Multithreaded scan of orgs in a list
    if org.endswith(".json"):
        scan_list(org, token, output)
    # Scan only one organization given by name
    else:
        etag = args.etag if args.etag else retrieve_etag_value(org)
        scan(org, token, output, etag)
