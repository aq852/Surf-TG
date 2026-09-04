import unittest

from bot.helper.security import (
    StreamTokenError,
    create_stream_token,
    hash_password,
    verify_password,
    verify_stream_token,
)


class SecurityTests(unittest.TestCase):
    def test_password_hash(self):
        encoded = hash_password("correct horse", salt=b"0123456789abcdef")
        self.assertTrue(verify_password("correct horse", encoded))
        self.assertFalse(verify_password("wrong", encoded))

    def test_stream_token_round_trip(self):
        token = create_stream_token("s" * 32, -100123, 42, ttl=60, now=100)
        claim = verify_stream_token("s" * 32, token, now=120)
        self.assertEqual((claim.chat_id, claim.message_id, claim.expires_at), (-100123, 42, 160))

    def test_tampered_and_expired_tokens_fail(self):
        token = create_stream_token("s" * 32, -100123, 42, ttl=10, now=100)
        with self.assertRaises(StreamTokenError):
            verify_stream_token("s" * 32, token + "x", now=101)
        with self.assertRaises(StreamTokenError):
            verify_stream_token("s" * 32, token, now=111)


if __name__ == "__main__":
    unittest.main()
