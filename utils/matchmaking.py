import itertools
from typing import Dict, List, Tuple

def balance_teams_by_mmr(slots: Dict[str, List[str]], user_mmrs: Dict[str, int]) -> Tuple[Dict[str, str], Dict[str, str]]:
    positions = ("pos1", "pos2", "pos3", "pos4", "pos5")
    
    best_diff = float('inf')
    best_radiant = {}
    best_dire = {}

    for combination in itertools.product((0, 1), repeat=5):
        current_radiant = {}
        current_dire = {}
        radiant_mmr = 0
        dire_mmr = 0

        for i, pos in enumerate(positions):
            players = slots.get(pos, [])
            if len(players) != 2:
                raise ValueError(f"CRITICAL: Слот {pos} не заполнен полностью.")

            rad_idx = combination[i]
            dir_idx = 1 - rad_idx

            rad_uid = players[rad_idx]
            dir_uid = players[dir_idx]

            current_radiant[pos] = rad_uid
            current_dire[pos] = dir_uid

            radiant_mmr += user_mmrs[rad_uid]
            dire_mmr += user_mmrs[dir_uid]

        diff = abs(radiant_mmr - dire_mmr)
        
        if diff < best_diff:
            best_diff = diff
            best_radiant = current_radiant.copy()
            best_dire = current_dire.copy()

            if best_diff == 0:
                break

    return best_radiant, best_dire