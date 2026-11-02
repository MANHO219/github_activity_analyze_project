"""把 ``b_repo_metadata/`` 加入 sys.path，使 ``scripts/`` 下的入口能导入 ``bmeta``。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
