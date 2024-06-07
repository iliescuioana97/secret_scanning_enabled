# secret_scanning_enabled

### 1. What would you do when using the tool to extract data for lots of organisations without hitting the rate limit
- Optimised the number of requests that count towards the rate limit by checking if requested data has been updated through the use of ETags in the request header, significantly dropping request numbers
- Checked if exceeded primary/secondary rate limits through response headers params
    - For secondary rate limit: if retry-after exists, we should wait for its value in seconds
    - For primary rate limit: if x-ratelimit-remaining is 0, then we have used our requests for this hour timeframe; sleeping until rate limit window refreshes (indicated by x-ratelimit-reset value in UTC epoch seconds)
    - Otherwise, if requests keep failing, Github REST API Docs advise to wait for a minute before retrying. Consequently, I implemented truncated exponential backoff

Link: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2022-11-28#exceeding-the-rate-limit

### 2. How would you good runtime performance when extracting data for lots of organisations
- Scaling horizontally across threads/processes and providing a targets.json file containing a list of organisations to be scanned, as to evenly distribute the workload between workers

### 3. How would you schedule such a tool to monitor a set of organisations on regular basis
- Depending on goal, scheduling on a periodic basis / based on trigger (addition off new orgs to the list) as a batch job
