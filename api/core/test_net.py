from django.test import RequestFactory

from core.net import client_ip


def test_the_address_caddy_saw_wins_and_forwarded_for_is_ignored():
    request = RequestFactory().get(
        "/",
        HTTP_X_REAL_IP="190.80.1.2",
        HTTP_X_FORWARDED_FOR="10.9.9.9, 190.80.1.2",
        REMOTE_ADDR="172.18.0.5",
    )
    assert client_ip(request) == "190.80.1.2"


def test_without_caddy_the_socket_address_is_used():
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="172.18.0.5")
    assert client_ip(request) == "172.18.0.5"


def test_a_malformed_address_is_never_stored():
    assert client_ip(RequestFactory().get("/", HTTP_X_REAL_IP="not-an-ip", REMOTE_ADDR="")) is None
    assert client_ip(RequestFactory().get("/", HTTP_X_REAL_IP="2001:db8::1")) == "2001:db8::1"
    assert client_ip(object()) is None
