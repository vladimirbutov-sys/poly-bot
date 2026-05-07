"""One-shot diagnostic: run all filters on current candidates, show rejection stats."""
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

import json
from collections import Counter
import scanner
import filters
import tracker

def main():
    # Fetch candidates
    print("Fetching markets...")
    markets = scanner.fetch_all_open_markets()
    print(f"Total open markets: {len(markets)}")

    candidates = scanner.parse_candidates(markets)
    print(f"Candidates (price 0.975-0.993): {len(candidates)}")

    # Load tracker
    data = tracker.load()
    open_cids = tracker.get_open_condition_ids(data)
    print(f"Open positions (blocked by duplicate filter): {len(open_cids)}")

    # Run filters and count reasons
    reason_counts = Counter()
    passed_list = []

    for c in candidates:
        passed, reason = filters.run_all_filters(c, open_cids, data)
        if passed:
            passed_list.append(c)
        else:
            # Extract filter name (first word before colon)
            short = reason.split(":")[0] if ":" in reason else reason
            reason_counts[short] += 1

    # Print stats
    print(f"\n{'='*60}")
    print(f"FILTER REJECTION BREAKDOWN ({len(candidates)} candidates)")
    print(f"{'='*60}")

    for reason, count in reason_counts.most_common():
        pct = count / len(candidates) * 100
        print(f"  {count:>5} ({pct:>5.1f}%) | {reason}")

    print(f"  {len(passed_list):>5} ({len(passed_list)/len(candidates)*100:>5.1f}%) | PASSED ALL FILTERS")

    # Show what passed
    if passed_list:
        print(f"\n{'='*60}")
        print(f"PASSED CANDIDATES ({len(passed_list)}):")
        print(f"{'='*60}")
        for c in passed_list[:20]:
            print(f"  {c['price']:.3f} | {c['question'][:70]}")
            print(f"         liq=${c['liquidity']:.0f} vol=${c['volume_total']:.0f} end={c['end_date'][:10] if c['end_date'] else 'N/A'} cat={c['category']}")
    else:
        # Show some examples of end_date rejections
        print(f"\n{'='*60}")
        print("SAMPLE END_DATE REJECTIONS:")
        print(f"{'='*60}")
        end_date_samples = []
        for c in candidates:
            passed, reason = filters.run_all_filters(c, set(), data)  # empty open_cids
            if "End date" in reason and len(end_date_samples) < 10:
                end_date_samples.append((c, reason))
        for c, reason in end_date_samples:
            print(f"  {c['price']:.3f} | {c['question'][:60]}")
            print(f"         end={c['end_date'][:16] if c['end_date'] else 'N/A'} | {reason}")

        # Also show what passes if we remove duplicate filter
        print(f"\n{'='*60}")
        print("IF WE IGNORE DUPLICATE FILTER:")
        print(f"{'='*60}")
        no_dup_counts = Counter()
        no_dup_passed = []
        for c in candidates:
            passed, reason = filters.run_all_filters(c, set(), data)
            if passed:
                no_dup_passed.append(c)
            else:
                short = reason.split(":")[0] if ":" in reason else reason
                no_dup_counts[short] += 1

        for reason, count in no_dup_counts.most_common():
            pct = count / len(candidates) * 100
            print(f"  {count:>5} ({pct:>5.1f}%) | {reason}")
        print(f"  {len(no_dup_passed):>5} ({len(no_dup_passed)/len(candidates)*100:>5.1f}%) | PASSED")

        for c in no_dup_passed[:10]:
            print(f"    {c['price']:.3f} | {c['question'][:65]}")
            print(f"           end={c['end_date'][:16] if c['end_date'] else 'N/A'} cat={c['category']} liq=${c['liquidity']:.0f}")

if __name__ == "__main__":
    main()
