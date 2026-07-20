import csv
from collections import Counter
c=Counter()
with open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv') as f:
    for r in csv.DictReader(f):
        for t in (r.get('Themes') or '').split(): c[t]+=1
print("distinct themes:", len(c), " | total rows:", sum(1 for _ in open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv'))-1)
for t,n in c.most_common(): print(f"  {t:22} {n}")
