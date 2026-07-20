import subprocess, csv, sys, collections
from lucena_engine.board import Board
SF = '/opt/homebrew/bin/stockfish'
VAL = {'p':1,'n':3,'b':3,'r':5,'q':9,'k':0}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60


class Engine:
    def __init__(s):
        s.p = subprocess.Popen([SF], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        s._c('uci'); s._w('uciok'); s._c('isready'); s._w('readyok')
    def _c(s, x): s.p.stdin.write(x + '\n'); s.p.stdin.flush()
    def _w(s, tok):
        for l in s.p.stdout:
            if l.startswith(tok): return
    def go(s, fen, limit):
        s._c('position fen ' + fen); s._c('go ' + limit); pv = []
        for l in s.p.stdout:
            if l.startswith('info') and ' pv ' in l: pv = l.split(' pv ')[1].split()
            if l.startswith('bestmove'): return l.split()[1], pv
        return None, []


E = Engine()
def real_pv(fen): return E.go(fen, 'depth 12')[1]
def best(fen): return E.go(fen, 'movetime 25')[0]


def grab_from_line(fen, ucis, cap=8):
    """Multiset of pieces the mover of `fen` captures along the line, up to the PEAK net advantage."""
    me = Board(fen).side_to_move; b = Board(fen); net = 0; peak = 0; peak_i = -1; won = []
    for i, u in enumerate(ucis[:cap]):
        byp = b.side_to_move == me; dst = u[2:4]
        c = next((p for p in b.piece_list() if p.square == dst and p.color != b.side_to_move), None)
        if c:
            net += VAL[c.piece.lower()] if byp else -VAL[c.piece.lower()]
            if byp: won.append((c.piece.lower(), i))
        if net > peak: peak, peak_i = net, i
        try: b = b.apply(u)
        except Exception: break
    return collections.Counter(p for p, i in won if i <= peak_i)


def unopposed_grab(fen, cap=6):
    b = Board(fen); grab = collections.Counter(); forcing = False
    for _ in range(cap):
        if b.in_check: forcing = True; break
        u = best(b.fen)
        if not u: break
        dst = u[2:4]
        c = next((p for p in b.piece_list() if p.square == dst and p.color != b.side_to_move), None)
        if c: grab[c.piece.lower()] += 1
        try: b = b.apply(u)
        except Exception: break
        if b.in_check: forcing = True; break            # our move gave check -> forcing; can't pass
        try: b = b.null_move()
        except Exception: forcing = True; break
    return grab, forcing


def load(n, band=(1300, 1900)):
    out = []
    for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv')):
        try: rt = int(r['Rating'])
        except Exception: continue
        if band[0] <= rt <= band[1] and len((r.get('Moves') or '').split()) >= 2 and r.get('Themes'):
            out.append(r)
    return [out[i] for i in range(0, len(out), max(1, len(out) // n))][:n]


P = load(N); cat = collections.Counter(); th = collections.Counter(); th_csb = collections.Counter(); ex = []
for r in P:
    mv = r['Moves'].split()
    try: sfen = Board(r['FEN']).apply(mv[0]).fen
    except Exception: continue
    unopp, forcing = unopposed_grab(sfen)
    realg = grab_from_line(sfen, real_pv(sfen))
    saved = unopp - realg                                # what the opponent's best defense rescues
    if forcing and not unopp:                    c = 'forcing_only'
    elif not unopp:                              c = 'no_grab'
    elif unopp == realg:                         c = 'forced_all'
    elif realg and not (realg - unopp):          c = 'cant_save_both'   # real subset of unopp, non-empty
    elif not realg:                              c = 'fully_defended'
    else:                                        c = 'mixed'
    cat[c] += 1
    for t in r['Themes'].split():
        th[t] += 1
        if c == 'cant_save_both': th_csb[t] += 1
    if c == 'cant_save_both' and len(ex) < 6:
        ex.append("    saved=%s  won=%s  themes=%s" % (dict(saved), dict(realg), r['Themes']))
    sys.stderr.write('.'); sys.stderr.flush()

print('\n\nDELTA EXPERIMENT (unopposed grab vs real-PV grab), n=%d' % len(P))
for c, n in cat.most_common(): print('  %-16s %d' % (c, n))
print('\ncant_save_both examples (saved = what the defense rescues; won = what falls anyway):')
print('\n'.join(ex) if ex else '  (none)')
print('\ncant_save_both count by theme:')
for t, n in th.most_common(14):
    if th_csb[t]: print('  %-20s %d/%d' % (t, th_csb[t], n))
