"""The sign-up network signal's pure rules (docs/backoffice.md § The pages,
Trust and safety): where an address is cut, and that a network's key changes
with the UTC day. The counters and the page are test_account_controls.py and
test_operator.py.
"""

from datetime import date

from beats.auth.signup_networks import network_key, network_of

SECRET = "a-secret-long-enough-for-the-test-00000000"


class TestTruncation:
    def test_ipv4_is_cut_to_its_slash_24(self):
        assert network_of("203.0.113.7") == "203.0.113.0/24"
        assert network_of("203.0.113.255") == "203.0.113.0/24"
        assert network_of("203.0.114.0") == "203.0.114.0/24"

    def test_ipv6_is_cut_to_its_slash_48(self):
        assert network_of("2001:db8:abcd:1234::1") == "2001:db8:abcd::/48"
        assert network_of("2001:db8:abcd:ffff:ffff:ffff:ffff:ffff") == "2001:db8:abcd::/48"
        assert network_of("2001:db8:abce::1") == "2001:db8:abce::/48"

    def test_what_is_not_an_address_is_no_network(self):
        assert network_of("testclient") is None
        assert network_of("") is None


class TestKey:
    def test_the_same_network_reads_the_same_within_a_day(self):
        day = date(2026, 11, 14)
        assert network_key("203.0.113.7", day, SECRET) == network_key("203.0.113.200", day, SECRET)
        assert network_key("203.0.113.7", day, SECRET) != network_key("203.0.114.7", day, SECRET)

    def test_the_key_changes_at_midnight(self):
        before = network_key("203.0.113.7", date(2026, 11, 14), SECRET)
        after = network_key("203.0.113.7", date(2026, 11, 15), SECRET)
        assert before != after

    def test_the_key_is_opaque_and_short(self):
        key = network_key("203.0.113.7", date(2026, 11, 14), SECRET)
        assert key is not None
        assert len(key) == 32
        assert "203" not in key or "113" not in key  # not the address, in any form
        assert network_key("203.0.113.7", date(2026, 11, 14), "another-secret") != key
