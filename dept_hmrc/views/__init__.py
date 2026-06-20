from .hmrc_home import dept_home, regime_list, regime_home      # noqa: F401
from .iht.reckoner import iht_reckoner_threshold, iht_reckoner_compute               # noqa: F401
from .iht.orchestrate import (                                                              # noqa: F401
    iht_action_deceased, iht_action_reckoner, iht_action_tailor,
    iht_action_common,
)
from core.views_layer1 import (                             # noqa: F401
    regime_schedule_sections,
    regime_schedules,
    regime_sections,
    regime_top_level,
)
