import kivy
kivy.require('2.3.1')

from kivy.app import App

from kivy.config import Config
Config.set('graphics', 'resizable', False)
from kivy.core.window import Window
Window.size = (500, 518)
Window.always_on_top = True
Window.minimum_width = 256
# Window.borderless = True

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.widget import Widget


class Issue(BoxLayout):
    pass


class IssueList(StackLayout):
    pass


class TreadingApp(App):

    def build(self):
        return IssueList()


def main():
    TreadingApp().run()


if __name__ == '__main__':
    main()