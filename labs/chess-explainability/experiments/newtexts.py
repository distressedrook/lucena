import sys; sys.path.insert(0, "python")
from lucena_engine.board import Board
from lucena_engine.detectors.hanging import detect_hanging
from lucena_engine.detectors.null_move import detect_null_move_threat
from lucena_engine import Engine
import os, shutil
FENS = {
 "opp_worked": "6k1/5ppp/8/4n3/8/8/5PPP/4R1K1 w - - 0 1",
 "danger_worked": "6k1/5ppp/6b1/8/4N3/8/5PPP/6K1 w - - 0 1",
 "queen_d6": "6k1/5ppp/3q4/1N6/8/8/5PPP/6K1 w - - 0 1",
 "rook_d6": "6k1/5ppp/3r4/1N6/8/8/5PPP/6K1 w - - 0 1",
 "queen_d4_danger": None, "pawn_d5_danger": None, "exd6": None, "gxf3": None, "kxe5": None,
}
# print hanging texts for the known ones
for k,f in FENS.items():
    if not f: continue
    for fact in detect_hanging(Board(f)):
        print(f"{k}: {fact.text!r}")
