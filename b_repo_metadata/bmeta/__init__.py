"""B 阶段（仓库元数据与 AI 标签）的实现包。

与 A 的 ``gharchive_a`` 对应：脚本入口在 ``scripts/``，实现细节集中在本包，
便于测试与复用。
"""

__version__ = "0.1.0"
__all__ = ["common", "select", "api", "fetch", "rules", "label", "join"]
