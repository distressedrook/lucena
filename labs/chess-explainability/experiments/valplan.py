import subprocess, csv, sys, re, collections
from lucena_engine.board import Board
from lucena_backend.reasoning import describe_plan
from lucena_backend.reasoning.undermine import _sole_defender
SF = '/opt/homebrew/bin/stockfish'
VAL = {'p':1,'n':3,'b':3,'r':5,'q':9,'k':0}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 80
WORD = {'p':'pawn','n':'knight','b':'bishop','r':'rook','q':'queen'}


class Engine:
    def __init__(s):
        s.p = subprocess.Popen([SF], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        s._c('uci'); s._w('uciok'); s._c('isready'); s._w('readyok')
    def _c(s, x): s.p.stdin.write(x + '\n'); s.p.stdin.flush()
    def _w(s, tok):
        for l in s.p.stdout:
            if l.startswith(tok): return
    def pv(s, fen):
        s._c('position fen ' + fen); s._c('go depth 16'); pv = []; sc = None
        for l in s.p.stdout:
            if l.startswith('info') and ' pv ' in l:
                pv = l.split(' pv ')[1].split(); t = l.split()
                if 'score' in t:
                    j = t.index('score'); k, v = t[j + 1], int(t[j + 2])
                    sc = (1000 if v > 0 else -1000) if k == 'mate' else v
            if l.startswith('bestmove'): return pv, sc
        return pv, sc


E = Engine()


def _final_material(fen, pv):
    """Play the whole PV; return mover-POV material on the ACTUAL final board (independent of the
    reasoner's own walk — counts pieces, no peak logic)."""
    me = Board(fen).side_to_move; b = Board(fen)
    for u in pv:
        try: b = b.apply(u)
        except Exception: break
    w = sum(VAL[p.piece.lower()] for p in b.piece_list() if p.color == 'white')
    bl = sum(VAL[p.piece.lower()] for p in b.piece_list() if p.color == 'black')
    return (w - bl) if me == 'white' else (bl - w), b


def verify_claim(fen, pv, claim_sq, claim_word):
    """INDEPENDENT verification: (1) the mover is genuinely up material on the final board (objective
    piece count), and (2) the LAST capture on the claimed target square was the PLAYER's, with a player
    capture there beyond ply 0 (the player won the exchange on that square — not a re-occupation by some
    unrelated piece later). Returns (ok, final_net)."""
    me = Board(fen).side_to_move
    net, _ = _final_material(fen, pv)
    b = Board(fen); caps_here = []               # (by_player, ply) of captures ON claim_sq
    for i, u in enumerate(pv):
        by_player = b.side_to_move == me
        if u[2:4].lower() == claim_sq:
            if any(p.square == claim_sq and p.color != b.side_to_move for p in b.piece_list()):
                caps_here.append((by_player, i))
        try: b = b.apply(u)
        except Exception: break
    player_won_here = any(bp and i > 0 for bp, i in caps_here) and (caps_here and caps_here[-1][0])
    return (net > 0 and player_won_here), net


def load(n, band=(1300, 2000)):
    out = []
    for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv')):
        try: rt = int(r['Rating'])
        except Exception: continue
        if band[0] <= rt <= band[1] and len((r.get('Moves') or '').split()) >= 2 and r.get('Themes'):
            out.append(r)
    return [out[i] for i in range(0, len(out), max(1, len(out) // n))][:n]


P = load(N)
fires = under = wins = 0
ok = bad = 0
bad_ex = []; fix = []; th = collections.Counter(); th_fire = collections.Counter()
for r in P:
    mv = r['Moves'].split()
    try: sfen = Board(r['FEN']).apply(mv[0]).fen
    except Exception: continue
    pv, cp = E.pv(sfen)
    plan = describe_plan(sfen, pv, cp)
    for t in r['Themes'].split(): th[t] += 1
    if not plan:
        sys.stderr.write('.'); sys.stderr.flush(); continue
    fires += 1
    for t in r['Themes'].split(): th_fire[t] += 1
    is_under = 'undermines' in plan
    under += is_under; wins += (not is_under)
    # parse the claimed target square + piece word from the sentence
    m = re.search(r"(pawn|knight|bishop|rook|queen) on ([a-h][1-8])", plan)
    good = False; net = None
    if m:
        claim_word, claim_sq = m.group(1), m.group(2)
        good, net = verify_claim(sfen, pv, claim_sq, claim_word)
        if good and is_under:
            # additionally: the played move must undermine that target's sole defender in the pre position
            pre = Board(sfen); g = _sole_defender(pre, claim_sq); good = False
            if g is not None:
                dest = pv[0][2:4]
                good = (dest == g) or (dest in Board(sfen).apply(pv[0]).attackers(g, pre.side_to_move))
    ok += good; bad += (not good)
    if good and len(fix) < 4 and ((is_under and not any(f[4] for f in fix)) or (not is_under and sum(not f[4] for f in fix) < 2)):
        fix.append((sfen, pv[:8], cp, plan, is_under))
    if not good and len(bad_ex) < 8:
        bad_ex.append("  CLAIM: %s\n    final_net=%s  FEN=%s  PV=%s" % (plan[:70], net, sfen, ' '.join(pv)))
    sys.stderr.write('F'); sys.stderr.flush()

print('\n\nMULTI-PLY PLAN validation, n=%d' % len(P))
print('  fired:            %d/%d  (%d%%)' % (fires, len(P), 100 * fires // max(1, len(P))))
print('    undermine-plan: %d' % under)
print('    wins-target:    %d' % wins)
print('  VERIFIED correct: %d/%d  (%d%%)' % (ok, fires, 100 * ok // max(1, fires)))
print('  FALSE/mismatch:   %d' % bad)
if bad_ex:
    print('\nfalse / mismatch examples:')
    print('\n'.join(bad_ex))
print('\nfire rate by theme:')
for t, n in th.most_common(14):
    if th_fire[t]: print('  %-20s %d/%d' % (t, th_fire[t], n))
print('\n--- test fixtures (FEN | pv_ucis | cp | plan) ---')
for sfen, pv, cp, plan, iu in fix:
    print('FEN: %s\n  PV: %s\n  CP: %s\n  PLAN: %s\n' % (sfen, pv, cp, plan))
