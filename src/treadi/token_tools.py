import keyring


SERVICE = "TreadI"
USERNAME = "GithubRefreshToken"


def get_refresh_token():
    refresh_token = keyring.get_password(SERVICE, USERNAME)
    if refresh_token is not None:
        keyring.delete_password(SERVICE, USERNAME)
    return refresh_token


def store_refresh_token(refresh_token):
    keyring.set_password(SERVICE, USERNAME, refresh_token)
