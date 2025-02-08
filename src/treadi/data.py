from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Repository:
    owner: str = ""
    name: str = ""


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
