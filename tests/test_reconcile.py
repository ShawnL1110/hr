import copy
import unittest
from hr.reconcile import compare, MONEY, COUNTS, DETAILS


class ReconciliationTests(unittest.TestCase):
    def sample(self):
        return {'week': '2026-09-21', 'slips': [dict(employee_id=7, **{k: 0 for k in MONEY+COUNTS}, **{k: [] for k in DETAILS})]}

    def test_component_difference_even_if_net_matches(self):
        before = self.sample()
        after = copy.deepcopy(before)
        after['slips'][0]['fixed'] = 0.01
        result = compare(before, after)
        self.assertFalse(result['matches'])
        self.assertEqual(['fixed'], result['differences'][0]['fields'])

    def test_missing_and_duplicate_employee(self):
        before = self.sample()
        after = copy.deepcopy(before)
        after['slips'] = []
        self.assertFalse(compare(before, after)['matches'])
        after['slips'] = before['slips'] * 2
        with self.assertRaises(ValueError):
            compare(before, after)

    def test_matches_and_missing_field(self):
        before = self.sample()
        self.assertTrue(compare(before, copy.deepcopy(before))['matches'])
        after = copy.deepcopy(before)
        del after['slips'][0]['perf_days']
        self.assertFalse(compare(before, after)['matches'])
