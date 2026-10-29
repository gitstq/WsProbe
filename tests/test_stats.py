"""统计模块的单元测试。"""

import unittest

from wsprobe.stats import SessionStats, percentile


class TestPercentile(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(percentile([], 50))

    def test_single(self):
        self.assertEqual(percentile([7.0], 50), 7.0)

    def test_median(self):
        self.assertEqual(percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50), 3.0)

    def test_min_max(self):
        values = [1.0, 2.0, 3.0]
        self.assertEqual(percentile(values, 0), 1.0)
        self.assertEqual(percentile(values, 100), 3.0)

    def test_interpolation(self):
        self.assertAlmostEqual(percentile([1.0, 2.0], 50), 1.5)


class TestSessionStats(unittest.TestCase):
    def setUp(self):
        self.stats = SessionStats()

    def test_counters(self):
        self.stats.record_received(0x1, 100)
        self.stats.record_received(0x2, 50)
        self.stats.record_sent(10)
        self.assertEqual(self.stats.messages_received, 2)
        self.assertEqual(self.stats.text_frames, 1)
        self.assertEqual(self.stats.binary_frames, 1)
        self.assertEqual(self.stats.bytes_received, 150)
        self.assertEqual(self.stats.bytes_sent, 10)

    def test_rtt_percentiles(self):
        for value in (0.1, 0.2, 0.3, 0.4, 0.5):
            self.stats.record_rtt(value)
        self.assertEqual(self.stats.rtt_percentile(50), 0.3)
        self.stats.finish()

    def test_to_dict_is_serializable(self):
        import json

        self.stats.record_received(0x1, 10)
        self.stats.record_rtt(0.01)
        self.stats.finish()
        payload = json.dumps(self.stats.to_dict())
        self.assertIn("messages_received", payload)
        self.assertIn("rtt_p50_ms", payload)

    def test_finish_is_idempotent(self):
        self.stats.finish()
        first = self.stats.end_time
        self.stats.finish()
        self.assertEqual(first, self.stats.end_time)

    def test_empty_rtt_report(self):
        report = self.stats.to_dict()
        self.assertIsNone(report["rtt_p50_ms"])
        self.assertEqual(report["rtt_samples"], 0)


if __name__ == "__main__":
    unittest.main()
