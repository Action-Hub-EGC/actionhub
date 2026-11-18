from datetime import datetime, timezone
from typing import Optional


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return *value* as an aware UTC datetime.

    MariaDB stores ``DATETIME`` without an offset, so values read back are
    naive even though every writer stores UTC. Attaching UTC here keeps the
    comparison and formatting code honest without changing the schema.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
