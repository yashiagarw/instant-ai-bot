"""Imports every model module so Base.metadata is complete (Alembic, tests)."""

from app.diagnosis import models as diagnosis  # noqa: F401
from app.knowledge import models as knowledge  # noqa: F401
from app.llm import models as llm  # noqa: F401
from app.parts import models as parts  # noqa: F401
from app.requests import models as requests  # noqa: F401
from app.vehicles import models as vehicles  # noqa: F401
