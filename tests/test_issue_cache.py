import copy
import random

from dateutil.parser import isoparse

from treadi.data import Issue
from treadi.data import Repository
from treadi.issue_cache import IssueCache


def random_string(*, len=5):
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    numbers = "0123456789"
    symbols = "_-"
    return "".join(
        random.sample(alphabet + alphabet.upper() + numbers + symbols, k=len)
    )


def rand_repo():
    return Repository(owner=random_string(), name=random_string())


def rand_issue(*, updated_at, repo=None, is_read=False):
    if repo is None:
        repo = rand_repo()
    return Issue(
        repo=repo,
        author=random_string(),
        created_at=isoparse("2006-07-04T15:00:00Z"),
        updated_at=isoparse(updated_at),
        number=random.randint(1, 9999),
        title=random_string(),
        url=random_string(),
        is_read=is_read,
    )


def test_cache_sorted():
    cache = IssueCache()
    first = rand_issue(updated_at="2006-07-04T15:00:00Z")
    second = rand_issue(updated_at="2006-07-04T16:00:00Z")
    third = rand_issue(updated_at="2006-07-04T17:00:00Z")
    fourth = rand_issue(updated_at="2006-07-04T18:00:00Z")
    fifth = rand_issue(updated_at="2006-07-04T19:00:00Z")
    sixth = rand_issue(updated_at="2006-07-04T20:00:00Z")
    issues_to_add = [
        first,
        second,
        third,
        fourth,
        fifth,
        sixth,
    ]
    random.shuffle(issues_to_add)
    for i in issues_to_add:
        cache.insert(i)
    assert [sixth, fifth, fourth] == cache.most_recent_issues(3)


def test_cache_dismissed():
    cache = IssueCache()
    first = rand_issue(updated_at="2006-07-04T15:00:00Z")
    second = rand_issue(updated_at="2006-07-04T16:00:00Z")
    third = rand_issue(updated_at="2006-07-04T17:00:00Z")
    cache.insert(first)
    cache.insert(second)
    cache.insert(third)
    cache.dismiss(second)
    assert [third, first] == cache.most_recent_issues(3)
    cache.insert(second)
    assert [third, first] == cache.most_recent_issues(3)


def test_cache_update_dismissed():
    cache = IssueCache()
    issue = rand_issue(updated_at="2006-07-04T15:00:00Z")
    cache.insert(issue)
    cache.dismiss(issue)
    assert [] == cache.most_recent_issues(1)
    issue = copy.deepcopy(issue)
    issue.updated_at = isoparse("2006-07-04T16:00:00Z")
    cache.insert(issue)
    assert [issue] == cache.most_recent_issues(1)


def test_cache_update_dismissed_is_read():
    cache = IssueCache()
    issue = rand_issue(updated_at="2006-07-04T15:00:00Z")
    cache.insert(issue)
    cache.dismiss(issue)
    assert [] == cache.most_recent_issues(1)
    issue = copy.deepcopy(issue)
    issue.updated_at = isoparse("2006-07-04T16:00:00Z")
    issue.is_read = True
    cache.insert(issue)
    assert [] == cache.most_recent_issues(1)
