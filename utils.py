import json
import requests
import os
import json
import time

from functools import reduce
from datetime import datetime, timezone, timedelta

GITHUB_TOKEN_ENV_VAR = "GITHUB_TOKEN"
TARGET_FILE = "targets.json"


def deep_get(dictionary, *keys):
    return reduce(lambda d, key: d.get(key) if d else {}, keys, dictionary)


def get_token(args):
    if args.token:
        return args.token

    token = os.environ.get(GITHUB_TOKEN_ENV_VAR)
    if token:
        return token

    print("No token provided: Request Rate Limit will be 60/h.")
    return None


def print_rate_limit(headers):
    response = requests.get("https://api.github.com/rate_limit", headers=headers)
    ret = json.loads(response.text)
    rates = ret["rate"]
    print(
        f"Limit: {rates['limit']}, ",
        f"Used: {rates['used']}, ",
        f"Limit: {rates['remaining']}",
    )


def get_if_modified_since_date(diff_timeframe):
    # This can be used to pass as arg an amount of hours to
    # lookback and generate the date in the past. The date can then be
    # further used to compare last update time of the data requested
    # from the API with conditional requests, using 'If-Modified-Since'
    # header, if the endpoint returns this.
    current_time = datetime.now(timezone.utc)
    modified_since_time = current_time - timedelta(hours=diff_timeframe)
    return modified_since_time.strftime("%a, %d %b %Y %H:%M:%S GMT")


def retrieve_etag_value(org):
    # This is simply to simulate etag storage in a local json file.
    # Alternatively, for production, this should be a db.
    storage = os.path.join(os.getcwd(), TARGET_FILE)
    with open(storage, "r") as f:
        targets = json.load(f)

    if org in targets:
        return targets[org]

    return None


def update_etag_value(org, etag):
    # This is simply to simulate etag storage in a local json file.
    # Alternatively, for production, this should be a db.
    print(f"Updating ETag for org: {org}")
    storage = os.path.join(os.getcwd(), TARGET_FILE)
    with open(storage, "r") as f:
        targets = json.load(f)

    targets[org] = etag

    with open(storage, "w") as file:
        json.dump(targets, file, indent=4)


def output_to_file(org_name, results, output):
    filename = f"{org_name}_status.json"
    path = os.path.join(output, filename)

    # Output results to a JSON file
    with open(path, "w") as outfile:
        json.dump(results, outfile, indent=4)


def get_org_list(org_file):
    with open(org_file, "r") as f:
        targets = json.load(f)

    return list(targets.keys())


def check_rate_limits(headers, retries):
    if "retry-after" in headers:
        return False, int(headers["retry-after"])

    if "x-ratelimit-remaining" in headers:
        if int(headers["x-ratelimit-remaining"]) > 0:
            return False, 0

        reset_timestamp = int(headers["x-ratelimit-reset"])
        current_timestamp = int(time.time())
        delta = reset_timestamp - current_timestamp + 1

        return False, delta

    return True, 60 * 2 ** (retries - 1)
