import subprocess, csv, sys, collections
from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional
from lucena_backend.reasoning import describe_plan, undermines_defender
SF = '/opt/homebrew/bin/stockfish'
THRESH = int(sys.argv[2]) if len(sys.argv) > 2 else 30   # mover-relative term-delta to fire
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
MOVER = {'white': 'White', 'black': 'Black'}
PHRASE = {'king_safety': "improves %s's king safety",
          'activity': "improves %s's piece activity",
          'pawns': "improves %s's pawn structure",
          'center': "strengthens %s's grip on the centre"}


class Engine:
    def __init__(s):
        s.p = subprocess.Popen([SF], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        s._c('uci'); s._w('uciok')
    def _c(s, x): s.p.stdin.write(x + '\n'); s.p.stdin.flush()
    def _w(s, tok):
        for l in s.p.stdout:
            if l.startswith(tok): return
    def pv(s, fen):
        s._c('position fen ' + fen); s._c('go depth 16'); pv = []; sc = None
        for l in s.p.stdout:
            if l.startswith('info') and ' pv ' in l:
                pv = l.split(' pv ')[1].split()
                t = l.split()
                if 'score' in t:
                    j = t.index('score'); kind, val = t[j + 1], int(t[j + 2])
                    sc = 100000 * (1 if val > 0 else -1) if kind == 'mate' else val
            if l.startswith('bestmove'): return pv, sc          # sc = mover-POV cp (mate -> ±100000)
        return pv, sc


E = Engine()


def describe_positional(pre_fen, uci):
    """Name the dominant NON-material positional term the move improves (mover-relative)."""
    try:
        pre = Board(pre_fen); me = pre.side_to_move; sign = 1 if me == 'white' else -1
        before = analyze_positional(pre)['terms']
        after = analyze_positional(pre.apply(uci))['terms']
        deltas = {k: sign * (after[k]['cp'] - before[k]['cp']) for k in before if k != 'material'}
        best = max(deltas, key=lambda k: deltas[k])
        if deltas[best] < THRESH: return None
        return (best, deltas[best], "The point of this move: it " + PHRASE[best] % MOVER[me] + ".")
    except Exception:
        return None


def load_slice(themes_any, themes_none, n):
    ta, tn = set(themes_any), set(themes_none)
    out = []
    for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv')):
        th = set((r.get('Themes') or '').split())
        if len((r.get('Moves') or '').split()) < 2: continue
        if ta and not (th & ta): continue
        if tn and (th & tn): continue
        out.append(r)
    return [out[i] for i in range(0, len(out), max(1, len(out) // n))][:n]


SLICES = {
    'tactical': (['fork', 'pin', 'hangingPiece', 'capturingDefender', 'discoveredAttack'], []),
    'positional': (['advantage', 'quietMove', 'positional', 'defensiveMove'],
                   ['fork', 'hangingPiece', 'capturingDefender', 'mate']),
}


GATE_LO, GATE_HI = 50, 350   # mover-POV cp band: good, but not a winning tactic


def run(label, rows):
    mat = pos = gated = none = 0; terms = collections.Counter(); ex = []
    for r in rows:
        mv = r['Moves'].split()
        try: sfen = Board(r['FEN']).apply(mv[0]).fen
        except Exception: continue
        m1 = mv[1]
        material = bool(undermines_defender(sfen, m1))
        pv, cp = E.pv(sfen)                                  # cp = mover-POV eval at sfen
        if not material:
            material = bool(describe_plan(sfen, pv))
        if material:
            mat += 1; continue
        p = describe_positional(sfen, m1)
        if p:
            pos += 1; terms[p[0]] += 1
            survives = cp is not None and GATE_LO <= cp <= GATE_HI
            gated += survives
            if len(ex) < 10:
                ex.append("  [%s] cp=%s %s %s  (%s)" %
                           (p[0], cp, 'PASS' if survives else 'drop', p[2][:52], r['Themes'][:38]))
        else:
            none += 1
        sys.stderr.write('.'); sys.stderr.flush()
    tot = mat + pos + none
    print('\n[%s] n=%d' % (label, tot))
    print('  material-reasoner fired:      %d (%d%%)' % (mat, 100 * mat // max(1, tot)))
    print('  positional raw fired:         %d (%d%%)' % (pos, 100 * pos // max(1, tot)))
    print('  positional AFTER cp-gate:     %d' % gated)
    print('  nothing derived:              %d (%d%%)' % (none, 100 * none // max(1, tot)))
    print('  term distribution (raw):', dict(terms))
    if ex:
        print('  positional fires (cp shown, PASS = survived %d..%dcp gate):' % (GATE_LO, GATE_HI))
        print('\n'.join(ex))


for label, (any_, none_) in SLICES.items():
    run(label, load_slice(any_, none_, N))
