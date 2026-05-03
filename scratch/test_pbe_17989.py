import sys
import os
sys.path.append(os.getcwd())

from src.database import get_db_session
from src.services.point_blank_matcher import get_point_blank_matcher

with get_db_session() as db:
    matcher = get_point_blank_matcher(db)
    
    # 17989 content snippet
    title = "Bonus kredi kartlarınızdan yapacağınız dijital abonelik harcamalarınızın yarısı kadar bonus kazanma fırsatı!"
    text = "Kampanya sadece Netflix, Amazon Prime, HBO Max, Spotify, BluTV, Gain, Exxen, Spotify, Youtube Premium platformlarında geçerlidir."
    
    matches = matcher.match_campaign(title, text)
    print(f"PBE Matches: {matches}")
