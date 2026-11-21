import pytest
from fastapi import HTTPException

from app import auth


class FakeRequest:
    def __init__(self, cookies):
        self.cookies = cookies


def test_load_developers():
    devs = auth.load_developers()
    assert devs["dev2"] == ["map", "record", "card_image"]


def test_assign_developer_by_area():
    assert auth.assign_developer("map") == "dev2"
    assert auth.assign_developer("voice") == "dev1"


def test_assign_unknown_area_goes_dev3():
    assert auth.assign_developer(None) == "dev3"
    assert auth.assign_developer("nonsense") == "dev3"


def test_login_unknown_id_raises():
    with pytest.raises(ValueError):
        auth.login("dev9")


def test_login_and_current_dev_and_logout():
    token = auth.login("dev1")
    assert auth.current_dev(FakeRequest({"session": token})) == "dev1"
    auth.logout(token)
    with pytest.raises(HTTPException) as e:
        auth.current_dev(FakeRequest({"session": token}))
    assert e.value.status_code == 401


def test_current_dev_missing_cookie_401():
    with pytest.raises(HTTPException) as e:
        auth.current_dev(FakeRequest({}))
    assert e.value.status_code == 401
