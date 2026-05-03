from src.database import get_db_session
from src.models import Campaign, Bank, Card
from sqlalchemy.orm import joinedload

def get_garanti_pending():
    with get_db_session() as db:
        # Get Garanti bank ID
        garanti_bank = db.query(Bank).filter(Bank.name.ilike('%Garanti%')).first()
        if not garanti_bank:
            print("Garanti Bank not found!")
            return []
        
        # Get all campaigns for Garanti that are not approved
        pending = db.query(Campaign).join(Card).filter(
            Campaign.is_approved == False,
            Card.bank_id == garanti_bank.id
        ).all()
        
        return [c.id for c in pending]

if __name__ == "__main__":
    ids = get_garanti_pending()
    print(",".join(map(str, ids)))
