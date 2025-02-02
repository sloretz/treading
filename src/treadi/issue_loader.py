from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import threading
import time
import logging
from gql import gql
from .repo_loader import Repository


@dataclass
class Issue:
    repo: Repository = Repository
    author: str = ""
    created_at: datetime = None
    updated_at: datetime = None
    number: int = 0
    title: str = ""
    url: str = ""
    # Has the current viewer looked at this issue or PR?
    is_read: bool = False


def is_same_issue(l, r):
    return l.repo == r.repo and l.number == r.number


def _make_issue(repo, gh_data):
    return Issue(
        repo=repo,
        author=gh_data["author"]["login"],
        created_at=datetime.fromisoformat(gh_data["createdAt"]),
        updated_at=datetime.fromisoformat(gh_data["updatedAt"]),
        number=int(gh_data["number"]),
        title=gh_data["title"],
        url=gh_data["url"],
        is_read=bool(gh_data["isReadByViewer"]),
    )


class IssueLoader:

    def __init__(self, gql_client, repos, progress_callback):
        self._client = gql_client
        self._repos = repos
        # The list of issues that will be displayed next
        self._upcomming_issues = []
        # The list of issues currently being displayed
        self._displayed_issues = []
        # The list of issues that have been dismissed, and not yet promoted to upcomming
        self._dismissed_issues = []
        self._lock = threading.Lock()
        self._logger = logging.getLogger("IssueLoader")
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._submit(self._load_initial_issues, repos, progress_callback)

    def _submit(self, *args):
        f = self._executor.submit(*args)
        f.add_done_callback(self._log_exception)

    def _log_exception(self, future):
        try:
            future.result()
        except:
            self._logger.exception("Exception in IssueLoader background thread")

    def _load_initial_issues(self, repos, progress_callback):
        num_repos_at_start = len(repos)
        REPOS_PER_QUERY = 20
        while repos:
            repo_query = """
            r%d: repository(owner: "%s", name: "%s") {
                issues(first: 5, orderBy: {field: UPDATED_AT, direction: DESC}, states: [OPEN]) {
                    nodes {
                        author {
                            login
                        }
                        createdAt
                        number
                        title
                        updatedAt
                        url
                        isReadByViewer
                    }
                }
                pullRequests(first: 5, orderBy: {field: UPDATED_AT, direction: DESC}, states: [OPEN]) {
                    nodes {
                        author {
                            login
                        }
                        createdAt
                        updatedAt
                        number
                        title
                        url
                        isReadByViewer
                    }
                }
            }"""
            repo_queries = []
            for i, r in enumerate(repos[:REPOS_PER_QUERY]):
                repo_queries.append(repo_query % (i, r.owner, r.name))
            query = gql(
                f"""
                query {{
                    {'\n'.join(repo_queries)}
                }}
                """
            )
            result = self._client.execute(query)
            for i, r in enumerate(repos[:REPOS_PER_QUERY]):
                rkey = f"r{i}"
                data = result[rkey]
                with self._lock:
                    for issue in data["issues"]["nodes"]:
                        self._upcomming_issues.append(_make_issue(r, issue))
                    for pr in data["pullRequests"]["nodes"]:
                        self._upcomming_issues.append(_make_issue(r, pr))
            repos = repos[REPOS_PER_QUERY:]
            self._upcomming_issues.sort(reverse=True, key=lambda i: i.updated_at)
            progress_callback((num_repos_at_start - len(repos)) / num_repos_at_start)

        # TODO submit work to regularly check for new issues
        pass

    def _update_issue(self, issue):
        # Update the appropriate list with new data for an issue
        with self._lock:
            for i, u in enumerate(self._upcomming_issues):
                if is_same_issue(issue, u):
                    if issue.updated_at >= u.updated_at:
                        self._upcomming_issues[i] = issue
                        self._upcomming_issues.sort(
                            reverse=True, key=lambda i: i.updated_at
                        )
                    return
            for i, d in enumerate(self._displayed_issues):
                if is_same_issue(issue, d):
                    if issue.updated_at >= d.updated_at:
                        self._displayed_issues[i] = issue
                    return
            for i, d in enumerate(self._dismissed_issues):
                if is_same_issue(issue, d):
                    if issue.updated_at >= d.updated_at:
                        self._dismissed_issues[i] = issue
                    return
            # Must be new, add it to upcomming list
            self._upcomming_issues.append(issue)
            self._upcomming_issues.sort(reverse=True, key=lambda i: i.updated_at)

    def next_issue(self) -> Issue:
        with self._lock:
            if len(self._upcomming_issues) == 0:
                return None
            issue = self._upcomming_issues.pop(0)
            self._displayed_issues.append(issue)
            return issue

    def dismiss_issue(self, issue):
        with self._lock:
            for i, d in enumerate(self._displayed_issues):
                if is_same_issue(issue, d):
                    del self._displayed_issues[i]
            self._dismissed_issues.append(issue)
