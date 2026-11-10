"""Print the prompt -> answer pairs for the sub-agents of a stage.   python v3_pairs.py <stage>"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "v3"
IDS = ["opec_quota", "chip_controls", "app_store", "ev_tariffs"]
n = sys.argv[1]
seats = {s: [x["name"] for x in json.loads((HERE / s / "scenario.json").read_text("utf-8-sig"))["seats"]] for s in IDS}
for k in range(4):
    print(f"SEAT {k + 1}")
    for i, s in enumerate(IDS, 1):
        a = seats[s][k]
        print(f"{i}. {s}\\prompts\\stage_{n}_{a}.txt -> {s}\\answers\\stage_{n}_{a}.json")
print("REFEREE")
for i, s in enumerate(IDS, 1):
    print(f"{i}. {s}\\prompts\\stage_{n}_referee.txt -> {s}\\answers\\stage_{n}_referee.json")
