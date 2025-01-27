import kivy
kivy.require('2.3.1')

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
Config.set('graphics', 'resizable', False)
from kivy.core.window import Window
from kivy.properties import NumericProperty

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen

import urllib
import webbrowser
import requests
import threading
import time

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

from . import token_tools
from .issue_loader import IssueLoader

CLIENT_ID = 'Iv23lipDhNiLUggDOf1B'
USERNAME = None
REPOS = None
ISSUES = None
GQL_CLIENT = None


def make_gql_client(access_token):
    global GQL_CLIENT
    transport = RequestsHTTPTransport(
        url="https://api.github.com/graphql",
        headers = {
            "Authorization": f"bearer {access_token}",
        },
        verify=True,
        retries=3,
    )
    GQL_CLIENT = Client(transport=transport, fetch_schema_from_transport=True)


def get_username():
    global USERNAME
    if USERNAME is not None:
        return USERNAME
    global GQL_CLIENT
    query = gql(
        """
        query {
            viewer {
                login
            }
        }
        """
    )
    result = GQL_CLIENT.execute(query)
    USERNAME = result['viewer']['login']
    return USERNAME


def get_all_user_repos():

    def _query(after=""):
        global GQL_CLIENT
        query = gql(
            """
            query($after: String!) {
                viewer {
                    repositories(after: $after, first: 100, visibility: PUBLIC, affiliations: [OWNER]) {
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
        result = GQL_CLIENT.execute(query, variable_values={'after': after})
        print(result)
        return result

    q = None
    while q is None or q['viewer']['repositories']['pageInfo']['hasNextPage']:
        if q is None:
            q = _query("")
        else:
            q = _query(q['viewer']['repositories']['pageInfo']['endCursor'])
        for r in q['viewer']['repositories']['nodes']:
            yield r['nameWithOwner'].split('/')


def get_newest_issues_and_prs(repos):
    global GQL_CLIENT
    repo_query = """
    r%d: repository(owner: "%s", name: "%s") {
        issues(first: 5, orderBy: {field: CREATED_AT, direction: ASC}, states: [OPEN]) {
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
        pullRequests(first: 5, orderBy: {field: CREATED_AT, direction: ASC}, states: [OPEN]) {
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
    }
    """
    repo_queries = []
    for i, r in enumerate(repos[:25]):
        repo_queries.append(repo_query % (i, r[0], r[1]))
    query = gql(
        f"""
        query {{
            {'\n'.join(repo_queries)}
        }}
        """
    )

    result = GQL_CLIENT.execute(query)
    print(result)
    return result


class FatChance(BoxLayout):
    pass


class Issue(BoxLayout):
    pass


class IssueScreen(Screen):
    pass


class RepoPickerScreen(Screen):

    def use_all_user_repos(self):
        global REPOS
        REPOS = [r for r in get_all_user_repos()]
        self.switch_to_loading()

    def switch_to_loading(self):
        # Must only be called on main thread
        self.manager.transition.direction = 'left'
        self.manager.current = 'loading'


class LoadingScreen(Screen):

    progress = NumericProperty(0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def update_progress(self, progress):
        self.progress = progress * 100
        if progress >= 1.0:
            Clock.schedule_once(lambda dt: self._loader.cleanup())
            Clock.schedule_once(lambda dt: self.switch_to_issues())

    def on_enter(self):
        global REPOS
        global ISSUES
        global GQL_CLIENT
        self._loader = IssueLoader(GQL_CLIENT, REPOS, self.update_progress)

    def switch_to_issues(self):
        # Must only be called on main thread
        self.manager.transition.direction = 'left'
        self.manager.current = 'issues'


class LoginScreen(Screen):

    def __init__(self, **kwargs):
        self.device_code = ""
        self.user_code = ""
        self.verification_uri = ""
        super().__init__(**kwargs)

    def check_login(self):
        if self.auth_with_cached_token():
            self.switch_to_repos()
        else:
            self.get_device_flow_codes()

    def auth_with_cached_token(self):
        rt = token_tools.get_refresh_token()
        if rt is None:
            return False
        data = {
            'client_id': CLIENT_ID,
            'grant_type': 'refresh_token',
            'refresh_token': rt,
        }
        r = requests.post('https://github.com/login/oauth/access_token', data=data)
        if r.status_code != 200:
            return False
        
        response = urllib.parse.parse_qs(r.text)
        token_tools.store_refresh_token(response['refresh_token'][0])
        make_gql_client(response['access_token'][0])
        return True

    def get_device_flow_codes(self):
        url = "https://github.com/login/device/code"
        r = requests.post(url, data={'client_id': CLIENT_ID})
        if r.status_code != 200:
            raise RuntimeError(f'TODO Handle device code request failure {r}')
        response = urllib.parse.parse_qs(r.text)
        self.device_code = response['device_code'][0]
        self.user_code = response['user_code'][0]
        self.verification_uri = response['verification_uri'][0]
        interval = int(response['interval'][0])
        expire_time = time.time() + int(response['expires_in'][0])
        Clock.schedule_once(lambda dt: self.check_auth(interval, expire_time), interval)

    def open_browser(self, url):
        webbrowser.open(url)

    def check_auth(self, interval, expire_time):
        if time.time() >= expire_time:
            self.get_device_flow_codes()
            return
        data = {
            'client_id': CLIENT_ID,
            'device_code': self.device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        }
        r = requests.post('https://github.com/login/oauth/access_token', data=data)
        if r.status_code != 200:
            raise RuntimeError(f'TODO handle auth check failure {r}')
        response = urllib.parse.parse_qs(r.text)
        if 'error' in response.keys():
            if 'slow_down' == response['error'][0]:
                # Check again even later
                Clock.schedule_once(lambda dt: self.check_auth(interval, expire_time), interval + 5)
                return
            if 'authorization_pending' == response['error'][0]:
                # Check again later
                Clock.schedule_once(lambda dt: self.check_auth(interval, expire_time), interval)
                return
            raise RuntimeError(f'TODO Handle auth check error {response}')
        else:
            token_tools.store_refresh_token(response['refresh_token'][0])
            make_gql_client(response['access_token'][0])
            self.switch_to_repos()
            return

    def switch_to_repos(self):
        print("Switch to repos")

        def _switch_any_thread(dt):
            # Must only be called on main thread
            self.manager.transition.direction = 'left'
            self.manager.current = 'repos'

        Clock.schedule_once(_switch_any_thread)


class TreadingApp(App):

    def build(self):
        Window.size = (500, 518)
        Window.always_on_top = True

        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(RepoPickerScreen(name='repos'))
        sm.add_widget(LoadingScreen(name='loading'))
        sm.add_widget(IssueScreen(name='issues'))

        return sm


def main():
    TreadingApp().run()


if __name__ == '__main__':
    main()