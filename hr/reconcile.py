"""Compare payroll results without printing employee names, salaries, or bank data."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

MONEY = ('fixed', 'perf', 'position', 'wa', 'full_attend', 'transport', 'allowance',
         'overtime', 'adjustments', 'incentive', 'qc_deduction', 'violation_deduction', 'net')
COUNTS = ('present_days', 'qualified_days', 'wa_days', 'total_hours', 'overtime_hours')
DETAILS = ('day_rows', 'perf_days', 'adjustment_items', 'incentive_days')


def compare(before, after):
    if before['week'] != after['week']:
        raise ValueError('Payroll weeks differ')
    def index(items):
        rows = {}
        for row in items:
            eid = row['employee_id']
            if eid in rows:
                raise ValueError('Duplicate employee in payroll')
            rows[eid] = row
        return rows
    left, right = index(before['slips']), index(after['slips'])
    changes = []
    for eid in sorted(set(left) | set(right)):
        if eid not in left or eid not in right:
            changes.append({'employee_id': eid, 'fields': ['employee_missing']})
            continue
        fields = []
        for field in MONEY + COUNTS:
            if field not in left[eid] or field not in right[eid]:
                fields.append(field + ':missing')
            elif Decimal(str(left[eid][field])) != Decimal(str(right[eid][field])):
                fields.append(field)
        for field in DETAILS:
            if field not in left[eid] or field not in right[eid] or left[eid][field] != right[eid][field]:
                fields.append(field)
        if fields:
            changes.append({'employee_id': eid, 'fields': fields})
    return {'week': before['week'], 'matches': not changes, 'employees': len(left), 'differences': changes}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before', type=Path)
    p.add_argument('after', type=Path)
    args = p.parse_args()
    result = compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['matches'] else 1)


if __name__ == '__main__':
    main()
