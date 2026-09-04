import unittest

from bot.helper.ranges import RangeNotSatisfiable, parse_range, plan_chunks


MIB = 1024 * 1024


class RangeTests(unittest.TestCase):
    def test_full_response(self):
        value, partial = parse_range(None, 10)
        self.assertFalse(partial)
        self.assertEqual((value.start, value.end, value.length), (0, 9, 10))

    def test_single_byte_is_one_chunk(self):
        value, _ = parse_range("bytes=0-0", 2 * MIB)
        self.assertEqual(plan_chunks(value).count, 1)

    def test_inclusive_chunk_boundary_needs_two_chunks(self):
        value, _ = parse_range(f"bytes=0-{MIB}", 2 * MIB)
        plan = plan_chunks(value)
        self.assertEqual(plan.count, 2)
        self.assertEqual(plan.last_cut, 1)

    def test_suffix_and_open_ended_ranges(self):
        suffix, _ = parse_range("bytes=-4", 10)
        open_end, _ = parse_range("bytes=7-", 10)
        self.assertEqual((suffix.start, suffix.end), (6, 9))
        self.assertEqual((open_end.start, open_end.end), (7, 9))

    def test_invalid_ranges(self):
        for header in ("bytes=10-", "bytes=5-3", "bytes=0-1,3-4", "items=0-1"):
            with self.subTest(header=header), self.assertRaises(RangeNotSatisfiable):
                parse_range(header, 10)


if __name__ == "__main__":
    unittest.main()
