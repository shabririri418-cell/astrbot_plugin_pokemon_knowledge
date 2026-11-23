import unittest
from pokemon_knowledge.policy import permitted


class Policy(unittest.TestCase):
    def test_default_available_but_never_for_proactive_messages(self):
        self.assertTrue(permitted({}, 'platform:GroupMessage:example', False))
        self.assertFalse(permitted({}, 'platform:GroupMessage:example', True))

    def test_disabled_and_allowlist(self):
        self.assertFalse(permitted({'enabled': False}, 'allowed', False))
        self.assertFalse(permitted({'allowed_origins': ['allowed']}, 'other', False))
        self.assertTrue(permitted({'allowed_origins': ['allowed']}, 'allowed', False))
