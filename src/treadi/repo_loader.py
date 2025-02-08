import abc
import threading
import time

from gql import gql

import requests

from yaml import safe_load as load_yaml

from .data import Repository


class RepoLoader(abc.ABC):

    def __init__(self):
        self._done_callback = None
        self._repos = None
        self._thread = threading.Thread(target=self._load_repos, daemon=True)

    def begin_loading(self, done_callback):
        self._done_callback = done_callback
        self._thread.start()

    @abc.abstractmethod
    def load_repos(self) -> tuple[Repository]: ...

    def _load_repos(self):
        self._repos = self.load_repos()
        self._done_callback(self._repos)
        self._done_callback = None

    def repos(self) -> tuple[Repository]:
        return self._repos

    def cleanup(self):
        self._thread.join()
        self._thread = None


class SequentialRepoLoaders(RepoLoader):
    """Invokes multiple repo loaders in a chain."""

    def __init__(self, repo_loaders, *args, **kwargs):
        self._loaders = repo_loaders
        super().__init__(*args, **kwargs)

    def load_repos(self):
        repos = []
        for loader in self._loaders:
            repos.extend(loader.load_repos())
        repos = tuple(set(repos))
        return repos


class CurrentUserRepoLoader(RepoLoader):

    def __init__(self, gql_client, *args, **kwargs):
        self._client = gql_client
        super().__init__(*args, **kwargs)

    def load_repos(self):
        repos = []

        def _query(after=""):
            query = gql(
                """
                query($after: String!) {
                    viewer {
                        repositories(after: $after, first: 100, visibility: PUBLIC, affiliations: [OWNER], isArchived: false) {
                            nodes {
                                nameWithOwner
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
                """
            )
            result = self._client.execute(query, variable_values={"after": after})
            return result

        q = None
        while q is None or q["viewer"]["repositories"]["pageInfo"]["hasNextPage"]:
            if q is None:
                q = _query("")
            else:
                q = _query(q["viewer"]["repositories"]["pageInfo"]["endCursor"])
            for r in q["viewer"]["repositories"]["nodes"]:
                owner, name = r["nameWithOwner"].split("/")
                repos.append(Repository(name=name, owner=owner))
        return tuple(repos)


class OrgRepoLoader(RepoLoader):

    def __init__(self, organization, gql_client, *args, **kwargs):
        self._client = gql_client
        self.organization = organization
        super().__init__(*args, **kwargs)

    def load_repos(self):
        repos = []

        def _query(after=""):
            query = gql(
                """
                query($after: String!, $organization: String!) {
                    organization(login: $organization) {
                        repositories(after: $after, first: 100, visibility: PUBLIC, isArchived: false) {
                            nodes {
                                nameWithOwner
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
                """
            )
            result = self._client.execute(
                query,
                variable_values={"after": after, "organization": self.organization},
            )
            return result

        q = None
        while q is None or q["organization"]["repositories"]["pageInfo"]["hasNextPage"]:
            if q is None:
                q = _query("")
            else:
                q = _query(q["organization"]["repositories"]["pageInfo"]["endCursor"])
            for r in q["organization"]["repositories"]["nodes"]:
                owner, name = r["nameWithOwner"].split("/")
                repos.append(Repository(name=name, owner=owner))
        return tuple(repos)


class FileRepoLoader(RepoLoader):

    def __init__(self, filepath, *args, **kwargs):
        self.filepath = filepath
        super().__init__(*args, **kwargs)

    def load_repos(self):
        repos = []

        with self.filepath.open() as f:
            while line := f.readline():
                print(line)
                # Strip comments
                if "#" in line:
                    line = line[: line.find("#")]
                # strip whitespace
                line = line.strip()
                if not line:
                    # ingore blank lines
                    continue
                if line.count("/") != 1:
                    raise RuntimeError(
                        "Incorrect format: {line}. Use one owner/name per line."
                    )
                owner, name = line.split("/")
                print(line)
                repos.append(Repository(name=name, owner=owner))
        return tuple(repos)


class VcsRepoLoader(RepoLoader):

    def __init__(self, url, *args, **kwargs):
        self.url = url
        super().__init__(*args, **kwargs)

    def load_repos(self):
        repos = []

        r = requests.get(self.url)
        if r.status_code != 200:
            raise RuntimeError(f"TODO Handle VCS Repose download failure {r}")

        repos_file = load_yaml(r.text)
        if "repositories" not in repos_file:
            raise RuntimeError(f"TODO handle invalid repos file {repos_file}")

        for repo_data in repos_file["repositories"].values():
            if "url" not in repo_data:
                raise RuntimeError(f"TODO handle invalid repos file {repos_file}")
            url = repo_data["url"]
            if not url.startswith("https://github.com/"):
                continue
            url = url[len("https://github.com/") :]
            if url.endswith(".git"):
                url = url[: -len(".git")]
            if url.count("/") != 1:
                raise RuntimeError("Unable to parse url: {repo_data['url']}")
            owner, name = url.split("/")
            repos.append(Repository(name=name, owner=owner))

        return tuple(repos)
