import abc
from dataclasses import dataclass
import threading
import time

from gql import gql


@dataclass(frozen=True)
class Repository:
    owner: str = ""
    name: str = ""


class RepoLoader(abc.ABC):

    def __init__(self, gql_client):
        self._client = gql_client
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


class CurrentUserRepoLoader(RepoLoader):

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

    def __init__(self, organization, *args, **kwargs):
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
