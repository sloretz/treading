from .data import is_same_issue
from threading import Lock


class IssueCache:

    def __init__(self):
        self.__upcomming = []
        self.__dismissed = []
        self.__lock = Lock()

    def insert(self, issue):
        """Insert an issue into the cache.

        If the cache already has newer info for the issue,
        it will silently ignore this insertion.
        """
        with self.__lock:
            self._insert(issue)

    def _insert(self, issue):
        for di, d in enumerate(self.__dismissed):
            if is_same_issue(issue, d):
                if issue.updated_at <= d.updated_at:
                    # Not new data, nothing to do here
                    return
                if not issue.is_read:
                    # Put it into the incomming list
                    del self.__dismissed[di]
                    break
                # Update the dismissed list
                self.__dismissed[di] = issue
                return
        # If we get here, the issue belongs in the
        # upcomming list
        for ui, u in enumerate(self.__upcomming):
            if is_same_issue(issue, u):
                if issue.updated_at > u.updated_at:
                    self.__upcomming[ui] = issue
                    return
                return
        # If we get here, the issue is new to us
        self.__upcomming.append(issue)

    def dismiss(self, issue):
        """
        Dismiss an issue so that it no longer
        comes up in `most_recent_not_dismissed`.
        """
        with self.__lock:
            self._dismiss(issue)

    def _dismiss(self, issue):
        for di, d in enumerate(self.__dismissed):
            if is_same_issue(issue, d):
                # already dismissed, nothing to do!
                return
        for ui, u in enumerate(self.__upcomming):
            if is_same_issue(issue, u):
                # Move from upcomming to dismiseed
                del self.__upcomming[ui]
                self.__dismissed.append(u)
                return

    def most_recent_issues(self, n=1):
        """
        Return the n most recently updated and not
        dismissed issues.
        """
        with self.__lock:
            return self._most_recent_issues(n)

    def newest_update_time(self):
        with self.__lock:
            self._sort()
            u = self.__upcomming[:1]
            d = self.__dismissed[:1]
        if not u and not d:
            return None
        if not u:
            return d[0].updated_at
        if not d:
            return u[0].updated_at
        if d[0].updated_at > u[0].updated_at:
            return d[0].updated_at
        return u[0].updated_at

    def _most_recent_issues(self, n):
        self._sort()
        return self.__upcomming[:n]

    def _sort(self):
        self.__upcomming.sort(reverse=True, key=lambda i: i.updated_at)
        self.__dismissed.sort(reverse=True, key=lambda i: i.updated_at)
