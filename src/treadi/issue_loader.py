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
    repo: Repository
    author: str
    created_at: datetime
    updated_at: datetime
    number: int
    title: str
    url: str


def _make_issue(repo, gh_data):
    return Issue(
        repo=repo,
        author=gh_data['author']['login'],
        created_at=datetime.fromisoformat(gh_data['createdAt']),
        updated_at=datetime.fromisoformat(gh_data['updatedAt']),
        number=gh_data['number'],
        title=gh_data['title'],
        url=gh_data['url'],
    )


class IssueLoader:

    def __init__(self, gql_client, repos, progress_callback):
        self._client = gql_client
        self._repos = repos
        self._issues = []
        self._lock = threading.Lock()
        self._logger = logging.getLogger('IssueLoader')
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
                        viewerDidAuthor
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
                        viewerDidAuthor
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
                rkey = f'r{i}'
                data = result[rkey]
                with self._lock:
                    for issue in data['issues']['nodes']:
                        self._issues.append(_make_issue(r, issue))
                    for pr in data['pullRequests']['nodes']:
                        self._issues.append(_make_issue(r, pr))
            repos = repos[REPOS_PER_QUERY:]
            progress_callback((num_repos_at_start - len(repos)) / num_repos_at_start)

    def next_issue(self) -> Issue:
        with self._lock:
            if len(self._issues) == 0:
                return None
            self._issues.sort(key=lambda i: i.updated_at)
            return self._issues.pop(0)
