from typing import Dict, List, Tuple
from core.config import DEFAULT_MMR

def balance_teams_by_mmr(slots: Dict[str, List[str]], user_mmrs: Dict[str, int]) -> Tuple[Dict[str, str], Dict[str, str]]:
    positions = ("pos1", "pos2", "pos3", "pos4", "pos5")
    
    pairs = []
    for pos in positions:
        players = slots.get(pos)
        if not players or len(players) != 2:
            raise ValueError(f"CRITICAL: Slot {pos} is not fully populated.")
        
        p0, p1 = players[0], players[1]
        pairs.append((
            (p0, user_mmrs.get(p0, DEFAULT_MMR)),
            (p1, user_mmrs.get(p1, DEFAULT_MMR))
        ))

    best_diff = float('inf')
    best_mask = 0

    for mask in range(32):
        rad_mmr = 0
        dir_mmr = 0
        
        for i in range(5):
            rad_idx = (mask >> i) & 1
            dir_idx = 1 - rad_idx
            
            rad_mmr += pairs[i][rad_idx][1]
            dir_mmr += pairs[i][dir_idx][1]

        diff = abs(rad_mmr - dir_mmr)
        
        if diff < best_diff:
            best_diff = diff
            best_mask = mask
            if diff == 0:
                break

    best_radiant: Dict[str, str] = {}
    best_dire: Dict[str, str] = {}
    
    for i, pos in enumerate(positions):
        rad_idx = (best_mask >> i) & 1
        dir_idx = 1 - rad_idx
        
        best_radiant[pos] = pairs[i][rad_idx][0]
        best_dire[pos] = pairs[i][dir_idx][0]

    return best_radiant, best_dire