import unittest

from collector import extract


class CollectorExtractionSafetyTests(unittest.TestCase):
    def test_anonymizes_account_and_does_not_invent_stats(self):
        result = extract([('steam-user', 'Bloom', 0, b'opaque-data')], 'secret-salt')
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertNotIn('steam-user', row.values())
        self.assertEqual(row['p_character_name'], 'Bloom')
        self.assertTrue(row['p_alive'])
        self.assertIsNone(row['p_kills_total'])
        self.assertIsNone(row['p_survival_seconds'])

    def test_skips_incomplete_identification(self):
        result = extract([(None, 'Bloom', 0, b''), ('user', '', 0, b'')], 'secret-salt')
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
