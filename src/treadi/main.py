import kivy
kivy.require('2.3.1')

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
Config.set('graphics', 'resizable', False)
from kivy.core.window import Window
from kivy.properties import NumericProperty
from kivy.properties import ObjectProperty

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen

import urllib
import webbrowser
import requests
import threading
import time
import pathlib

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

from . import auth
from .issue_loader import IssueLoader
from .repo_loader import CurrentUserRepoLoader


USERNAME = None
REPOS = None
ISSUES = None


def make_gql_client(access_token):
    transport = RequestsHTTPTransport(
        url="https://api.github.com/graphql",
        headers = {
            "Authorization": f"bearer {access_token}",
        },
        verify=True,
        retries=3,
    )
    schema_path = pathlib.Path(__file__).parent.resolve() / "schema.docs.graphql"
    return Client(transport=transport, schema=schema_path.read_text())


def get_newest_issues_and_prs(client, repos):
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

    result = gql_client.execute(query)
    return result


class FatChance(BoxLayout):
    pass


class Issue(BoxLayout):
    pass


class IssueScreen(Screen):
    pass


class RepoPickerScreen(Screen):

    def use_all_user_repos(self):
        self.manager.switch_to(RepoLoadingScreen(CurrentUserRepoLoader))


class RepoLoadingScreen(Screen):

    def __init__(self, repo_loader_class, **kwargs):
        self._loader = repo_loader_class(
            App.get_running_app().gql_client,
            self.switch_to_issue_loading
        )
        super().__init__(**kwargs)

    def switch_to_issue_loading(self, repos):

        def _switch(dt):
            self.manager.switch_to(IssueLoadingScreen(repos))

        Clock.schedule_once(lambda dt: self._loader.cleanup())
        Clock.schedule_once(_switch)


class IssueLoadingScreen(Screen):

    progress = NumericProperty(0.0)

    def __init__(self, repos, **kwargs):
        self._loader = IssueLoader(
            App.get_running_app().gql_client,
            repos,
            self.update_progress)
        super().__init__(**kwargs)

    def update_progress(self, progress):
        self.progress = progress * 100
        if progress >= 1.0:
            Clock.schedule_once(lambda dt: self._loader.cleanup())
            Clock.schedule_once(lambda dt: self.switch_to_issues())

    def switch_to_issues(self):
        # Must only be called on main thread
        self.manager.transition.direction = 'left'
        self.manager.current = 'issues'


class LoginScreen(Screen):

    device_flow = ObjectProperty(
            auth.DeviceFlow(
            device_code="",
            user_code="",
            verification_uri="",
            interval=0,
            expires_in=0,
        ),
        rebind=True,
    )
    token_response = ObjectProperty()

    def on_enter(self):
        self.start_device_flow()

    def start_device_flow(self):
        self.device_flow = auth.start_device_flow()
        print("Device flow started: ", self.device_flow)
        Clock.schedule_once(
            lambda dt: self.check_auth(),
            self.device_flow.interval)

    def open_browser(self, url):
        webbrowser.open(url)

    def check_auth(self):
        response = auth.ask_for_token(self.device_flow)
        match response.status:
            case auth.Status.AUTHORIZATION_PENDING:
                Clock.schedule_once(lambda dt: self.check_auth(), self.device_flow.interval)
            case auth.Status.EXPIRED_TOKEN:
                self.start_device_flow()
            case auth.Status.ACCESS_DENIED:
                raise RuntimeError('TODO nice error message when user denies TreadI App')
            case auth.Status.ACCESS_GRANTED:
                # Listeners on the token_response property are notified here
                self.token_response = response
            case _:
                raise RuntimeError('TODO nice error message when other error encountered')


class TreadIApp(App):

    gql_client = None
    sm = None

    def make_client_from_response(self, token_response):
        if token_response.status == auth.Status.ACCESS_GRANTED:
            self.gql_client = make_gql_client(token_response.access_token)
            return True
        return False

    def on_login_result(self, _, token_response):
        if self.make_client_from_response(token_response):
            self.manager.transition.direction = 'left'
            self.manager.current = 'repos'
        raise RuntimeError('TODO more graceful response to login failure')

    def build(self):
        Window.size = (500, 518)
        Window.always_on_top = True

        self.sm = ScreenManager()

        token_response = auth.cycle_cached_token()
        if not self.make_client_from_response(token_response):
            # Ask user to login
            login_screen = LoginScreen()
            login_screen.bind(token_response=self.on_login_result)
            self.sm.add_widget(login_screen)

        self.sm.add_widget(RepoPickerScreen(name='repos'))
        self.sm.add_widget(IssueScreen(name='issues'))

        return self.sm


def main():
    TreadIApp().run()


if __name__ == '__main__':
    main()