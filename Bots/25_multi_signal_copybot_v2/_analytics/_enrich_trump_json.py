"""Enrich scraped Trump JSON with content/type info gathered via WebFetch on empty-snippet posts."""
import json

# Manual enrichment from WebFetch results on empty-snippet posts.
# Each entry: id -> (content, post_type, iran_relevant_bool, note)
ENRICH = {
    '37770': {
        'content': 'This was put out by the CATO Institute, who hates "TRUMP," but they can\'t hide the facts. The Democrats were a DISASTER on the Border, and we were the best in the History of the U.S.A.! President DONALD J. TRUMP',
        'post_type': 'original',
        'iran_relevant': False,
        'note': 'Border/CATO chart — not Iran; matched on scraper metadata only'
    },
    '37790': {
        'content': '[VIDEO] US Navy blockade warning: "The US has announced a formal blockade of Iranian ports in coastal areas. This is illegal action. All vessels are advised to immediately return to port if leaving and discontinue transit to Iran if that is your next port of call. Do not attempt to breach the blockade. Vessels will be boarded for interdiction and seizure transiting to or from an Iranian port. Turn around and prepare to be boarded. If you do not comply with this blockade, we will use force. The whole of the United States Navy is ready to force compliance."',
        'post_type': 'original',
        'iran_relevant': True,
        'note': 'Video post — Navy blockade warning broadcast'
    },
    '37800': {
        'content': '[IMAGE ONLY — letter from Franklin Graham dated Apr 15 2026, re: illustration controversy, religious freedom]',
        'post_type': 'original',
        'iran_relevant': False,
        'note': 'Franklin Graham letter — not Iran'
    },
    '37816': {
        'content': 'MORNING GLORY: Trump has restored the GOP as the party of defense and deterrence: [Fox News link]',
        'post_type': 'original',
        'iran_relevant': True,
        'note': 'Fox News article referencing Iran negotiation window'
    },
    '37839': {
        'content': '[IMAGE ONLY — letter from Franklin Graham dated Mar 2 2026, references "freedom opportunities to Iran"]',
        'post_type': 'original',
        'iran_relevant': False,
        'note': 'Old Graham letter mentioning Iran — not a live Iran statement'
    },
    '37868': {
        'content': '[RETRUTH of FAN TRUMP ARMY post about Russia trading with US in dollars, BRICS]',
        'post_type': 'retruth',
        'iran_relevant': False,
        'note': 'Russia/BRICS fan retruth — not Iran'
    },
    '37871': {
        'content': '[RETRUTH of Sean Hannity post quoting Victor Davis Hanson on European leaders and Iran policy — credits Trump + Israeli military]',
        'post_type': 'retruth',
        'iran_relevant': True,
        'note': 'Hannity/VDH commentary on Iran — mild Iran relevance'
    },
    '37875': {
        'content': '[RETRUTH of @heyitsmeCarolyn: "Not just a President... Trump is the best Grandpa!"]',
        'post_type': 'retruth',
        'iran_relevant': False,
        'note': 'Grandpa meme retruth — not Iran'
    },
    '37878': {
        'content': '[RETRUTH of @KarluskaP: "President Trump is the best political athlete."]',
        'post_type': 'retruth',
        'iran_relevant': False,
        'note': 'Fan meme retruth — not Iran'
    },
    '37914': {
        'content': '[RETRUTH of Eric Daugherty tweet on 2019 impeachment expungement, Tulsi Gabbard files, Jim Jordan]',
        'post_type': 'retruth',
        'iran_relevant': False,
        'note': 'Impeachment/expungement — not Iran'
    },
    '37922': {
        'content': '[IMAGE ONLY — Franklin Graham letter dated Apr 7 2026, prayer for President]',
        'post_type': 'original',
        'iran_relevant': False,
        'note': 'Graham prayer letter — not Iran'
    },
}

path = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\trump_truth_iran_apr13_20.json'
with open(path, encoding='utf-8') as f:
    data = json.load(f)

# Add iran_relevant flag for all posts; default True if content has iran/israel/hormuz/ceasefire
kw = ('iran', 'hormuz', 'israel', 'blockade', 'ceasefire', 'tehran', 'strait')
for p in data:
    pid = p['id']
    if pid in ENRICH:
        e = ENRICH[pid]
        p['content'] = e['content']
        p['post_type'] = e['post_type']
        p['iran_relevant'] = e['iran_relevant']
        p['enrichment_note'] = e['note']
    else:
        c = (p.get('content') or '').lower()
        p['iran_relevant'] = any(k in c for k in kw)

relevant = [p for p in data if p['iran_relevant']]
print(f'Total posts in window: {len(data)}')
print(f'Iran-relevant: {len(relevant)}')
print(f'Off-topic (matched via metadata): {len(data) - len(relevant)}')

from collections import Counter
dates = Counter(p['timestamp_utc'][:10] for p in relevant)
print('\nIran-relevant date distribution:')
for d in sorted(dates):
    print(f'  {d}: {dates[d]}')

types = Counter(p['post_type'] for p in relevant)
print(f'\nPost types (iran-relevant): {dict(types)}')

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'\nSaved enriched file: {path}')
