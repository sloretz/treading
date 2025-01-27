import threading
import time


class IssueLoader:

    def __init__(self, gqlClient, repos, progress_callback):
        self._client = gqlClient
        self._repos = repos
        self._progress_callback = progress_callback
        self._repos_to_query = repos
        self._queried_repos = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._load_issues, daemon=True)
        self._thread.start()

    def _load_issues(self):
        while self._repos_to_query:
            with self._lock:
                current_repos = self._repos_to_query[:20]

            # TODO make actual progress
            print("Making progress!")
            time.sleep(1)

            with self._lock:
                self._queried_repos.extend(current_repos)
                self._repos_to_query = self._repos_to_query[20:]

            self._progress_callback(self.progress())
        print("all done loading!")

    def progress(self):
        with self._lock:
            progress = len(self._queried_repos) / (len(self._repos_to_query) + len(self._queried_repos))
        return progress

    def issues(self):
        # TODO return loaded issues
        return [1, 2, 3, 4, 5]

    def cleanup(self):
        self._thread.join()
        self._thread = None