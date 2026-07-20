import subprocess, csv
from lucena_engine.board import Board
from lucena_backend.reasoning import describe_plan
SF='/opt/homebrew/bin/stockfish'
class E:
    def __init__(s):
        s.p=subprocess.Popen([SF],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        s.c('uci'); s.w('uciok')
    def c(s,x): s.p.stdin.write(x+'\n'); s.p.stdin.flush()
    def w(s,t):
        for l in s.p.stdout:
            if l.startswith(t): return
    def pv(s,fen):
        s.c('position fen '+fen); s.c('go depth 16'); pv=[]; sc=None
        for l in s.p.stdout:
            if l.startswith('info') and ' pv ' in l:
                pv=l.split(' pv ')[1].split(); t=l.split()
                if 'score' in t:
                    j=t.index('score'); k,v=t[j+1],int(t[j+2]); sc=(1000 if v>0 else -1000) if k=='mate' else v
            if l.startswith('bestmove'): return pv,sc
        return pv,sc
E=E()
rows=[r for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv'))
      if 1400<=int(r['Rating'] or 0)<=1900 and len((r['Moves'] or '').split())>=2]
und=[]; win=[]
for r in [rows[i] for i in range(0,len(rows),311)][:400]:
    mv=r['Moves'].split()
    try: sfen=Board(r['FEN']).apply(mv[0]).fen
    except: continue
    pv,cp=E.pv(sfen); plan=describe_plan(sfen,pv,cp)
    if not plan: continue
    b=Board(sfen); san=b.san(pv[0])
    row=(sfen,san,cp,plan,r['Rating'])
    if 'undermines' in plan and len(und)<2: und.append(row)
    elif 'undermines' not in plan and len(win)<3: win.append(row)
    if len(und)>=2 and len(win)>=3: break
for sfen,san,cp,plan,rat in und+win:
    print('FEN : %s' % sfen)
    print('play: %s   (best move, cp=%s, rating~%s)' % (san,cp,rat))
    print('want: %s\n' % plan)
