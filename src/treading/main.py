import kivy
kivy.require('2.3.1')

from kivy.app import App
from kivy.uix.label import Label


class MyApp(App):

    def build(self):
        return Label(text='Hello world')


def main():
    MyApp().run()


if __name__ == '__main__':
    main()