import threading
import time
import logging
from gql import gql
from datetime import datetime
from dateutil.parser import isoparse

from .data import Issue
from .data import Repository


def _make_issue(gh_data):
    repo = Repository(
        owner=gh_data["repository"]["owner"]["login"],
        name=gh_data["repository"]["name"],
    )
    if gh_data["author"] is None:
        # https://github.com/ghost
        author = "ghost"
    else:
        author = gh_data["author"]["login"]
    return Issue(
        repo=repo,
        author=author,
        created_at=isoparse(gh_data["createdAt"]),
        updated_at=isoparse(gh_data["updatedAt"]),
        number=int(gh_data["number"]),
        title=gh_data["title"],
        url=gh_data["url"],
        is_read=bool(gh_data["isReadByViewer"]),
    )


FRAGMENT_ISSUE = """
fragment issueFields on Issue {
    author {
        login
    }
    createdAt
    number
    title
    updatedAt
    url
    isReadByViewer
    repository {
        name
        owner {
            login
        }
    }
}
"""
FRAGMENT_PR = """
fragment prFields on PullRequest {
    author {
        login
    }
    createdAt
    number
    title
    updatedAt
    url
    isReadByViewer
    repository {
        name
        owner {
            login
        }
    }
}
"""


class IssueQuery:

    def __init__(self, *, first=100, after=None, states=("OPEN",)):
        self.first = first
        self.after = after
        self.states = states

    def __str__(self):
        parts = [f"issues(first: {self.first}"]
        if self.after:
            parts.append(f', after: "{self.after}"')
        if self.states:
            parts.append(", states: [")
            parts.append(",".join(self.states))
            parts.append("]")
        parts.append(
            ") { nodes { ...issueFields } pageInfo { endCursor hasNextPage } }"
        )
        return "".join(parts)


class PRQuery:

    def __init__(self, *, first=100, after=None, states=("OPEN",)):
        self.first = first
        self.after = after
        self.states = states

    def __str__(self):
        parts = [f"pullRequests(first: {self.first}"]
        if self.after:
            parts.append(f', after: "{self.after}"')
        if self.states:
            parts.append(", states: [")
            parts.append(",".join(self.states))
            parts.append("]")
        parts.append(") { nodes { ...prFields } pageInfo { endCursor hasNextPage } }")
        return "".join(parts)


class IssueLoader:

    def __init__(self, gql_client, repos, cache, progress_callback):
        self._client = gql_client
        self._repos = tuple(repos)
        self._cache = cache
        self._lock = threading.Lock()
        self._logger = logging.getLogger("IssueLoader")
        self._thread = threading.Thread(daemon=True, target=self._run)
        self._progress_callback = progress_callback
        self._thread.start()

    def _run(self):
        try:
            self._load_all_issues(
                repos_per_query=10, progress_callback=self._progress_callback
            )
        except:
            self._logger.exception("Exception in IssueLoader thread")
        while True:
            time.sleep(15)
            try:
                # Uses search API to get updated issues and PRs
                self._update_all_issues()
            except:
                self._logger.exception("Exception in IssueLoader thread")

    def _load_all_issues(self, repos_per_query, progress_callback=None):
        num_repos_at_start = len(self._repos)

        # These dicts indicate if repos have more issues or PRs to query
        issue_page_info = {}
        pr_page_info = {}
        for r in self._repos:
            # Use "None" to mean we haven't queried anything yet
            issue_page_info[r] = {"endCursor": None}
            pr_page_info[r] = {"endCursor": None}

        # Outer loop runs until it finishes exploring all issues and PRs
        # on all repos
        next_queries = []
        issue_count = 0
        pr_count = 0
        while issue_page_info or pr_page_info:
            # This loop looks for repos that still need to be explored
            for r in self._repos:
                issue_query = None
                pr_query = None
                if r in issue_page_info:
                    ipi = issue_page_info[r]
                    issue_query = IssueQuery(after=ipi["endCursor"])
                if r in pr_page_info:
                    prpi = pr_page_info[r]
                    pr_query = PRQuery(after=prpi["endCursor"])

                if issue_query or pr_query:
                    repo_query = (
                        f'r{id(r)}: repository(owner: "{r.owner}", name: "{r.name}")'
                    )
                    repo_query += "{"
                    if issue_query:
                        repo_query += str(issue_query)
                    if pr_query:
                        repo_query += str(pr_query)
                    repo_query += "}"
                    next_queries.append(repo_query)

                if len(next_queries) == repos_per_query:
                    # Found enough repos, ditch the for loop
                    break

            # Execute the next query
            joined_queries = "\n".join(next_queries)
            query_str = f"""
                query {{
                    {joined_queries}
                }}
                """
            next_queries = []
            # It's an error to include unused fragments,
            # so only include a fragment if it's used.
            if issue_page_info:
                query_str += FRAGMENT_ISSUE
            if pr_page_info:
                query_str += FRAGMENT_PR
            query = gql(query_str)
            result = self._client.execute(query)

            # Figure out what repos the query included,
            # and add the issues and PRs to the cache
            for r in self._repos:
                key = f"r{id(r)}"
                if key not in result:
                    # Query didn't include this repo
                    continue
                repo_result = result[key]
                if "issues" in repo_result:
                    for issue in repo_result["issues"]["nodes"]:
                        self._cache.insert(_make_issue(issue))
                        issue_count += 1
                    if repo_result["issues"]["pageInfo"]["hasNextPage"]:
                        issue_page_info[r] = repo_result["issues"]["pageInfo"]
                    else:
                        del issue_page_info[r]
                if "pullRequests" in repo_result:
                    for pr in repo_result["pullRequests"]["nodes"]:
                        self._cache.insert(_make_issue(pr))
                        pr_count += 1
                    if repo_result["pullRequests"]["pageInfo"]["hasNextPage"]:
                        pr_page_info[r] = repo_result["pullRequests"]["pageInfo"]
                    else:
                        del pr_page_info[r]
            if progress_callback:
                i_max = pr_max = num_repos_at_start
                progress_callback(
                    (i_max - len(issue_page_info) + pr_max - len(pr_page_info))
                    / (i_max + pr_max)
                )
        self._logger.info(f"Loaded {issue_count} issues and {pr_count} PRs")

    def _update_all_issues(self):

        updated_time = self._cache.newest_update_time().isoformat()

        def make_query(extra):
            gh_search = f"{extra} is:open updated:>{updated_time} "
            gh_search += " ".join([f"repo:{r.owner}/{r.name}" for r in self._repos])
            query_parts = ["{"]
            query_parts.append(f'search(first: 1, query: "{gh_search}", type: ISSUE) ')
            query_parts.append("{ nodes {...issueFields ...prFields} }")
            query_parts.append("}")
            query_parts.append(FRAGMENT_ISSUE)
            query_parts.append(FRAGMENT_PR)
            return " ".join(query_parts)

        # TODO use pagination for unlikely case of more than 100 updated issues
        # Must query for issues and PRs separately
        # https://github.com/orgs/community/discussions/149046
        issues = self._client.execute(gql(make_query("is:issue")))
        for i in issues["search"]["nodes"]:
            self._cache.insert(_make_issue(i))

        prs = self._client.execute(gql(make_query("is:pr")))
        for pr in prs["search"]["nodes"]:
            self._cache.insert(_make_issue(pr))
