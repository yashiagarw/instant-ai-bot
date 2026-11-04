"""Imports every model module so Base.metadata is complete (Alembic, tests)."""

from app.accounts import models as accounts  # noqa: F401
from app.admin import models as admin  # noqa: F401
from app.diagnosis import models as diagnosis  # noqa: F401
from app.knowledge import models as knowledge  # noqa: F401
from app.llm import models as llm  # noqa: F401
from app.mechanics import models as mechanics  # noqa: F401
from app.notify import models as notify  # noqa: F401
from app.parts import models as parts  # noqa: F401
from app.quality import models as quality  # noqa: F401
from app.requests import models as requests  # noqa: F401
from app.uploads import models as uploads  # noqa: F401
from app.vehicles import models as vehicles  # noqa: F401
from app.vision import models as vision  # noqa: F401
