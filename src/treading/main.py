import kivy
kivy.require('2.3.1')

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
Config.set('graphics', 'resizable', False)
from kivy.core.window import Window

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen

from github import Auth
from github import Github
from github import GithubIntegration

import urllib
import webbrowser
import requests
import threading
import time

CLIENT_ID = 'Iv23lipDhNiLUggDOf1B'
USER_ACCESS_TOKEN = None
REFRESH_TOKEN = None

class Token:

    def __init__(self, value, expires_in):
        self.expires_at = time.time() + expires_in
        self.value = value

    def __str__(self):
        return self.value


class FatChance(BoxLayout):
    pass


class Issue(BoxLayout):
    pass


class IssueScreen(Screen):
    pass


class LoginScreen(Screen):

    def __init__(self, **kwargs):
        # TODO check for cached token first
        self.authenticated = False
        self.get_device_flow_codes()
        super().__init__(**kwargs)

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

    def on_login():
        print("hello world")

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
            USER_ACCESS_TOKEN = Token(response['access_token'][0], int(response['expires_in'][0]))
            REFRESH_TOKEN = Token(response['refresh_token'][0], int(response['refresh_token_expires_in'][0]))
            self.switch_to_issues()
            return

    def switch_to_issues(self):
        # Must only be called on main thread
        self.manager.transition.direction = 'left'
        self.manager.current = 'issues'


class TreadingApp(App):

    def build(self):
        Window.size = (500, 518)
        Window.always_on_top = True

        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(IssueScreen(name='issues'))
        return sm


def main():
    TreadingApp().run()


if __name__ == '__main__':
    main()