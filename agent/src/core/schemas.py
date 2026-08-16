from pydantic import BaseModel, Field
from typing import Dict

class ArtifactSchema(BaseModel):
    """Worker Agent 产出产物的标准输出 Schema。"""
    summary: str = Field(description="对执行操作和关键发现的简要总结。")
    artifacts: Dict[str, str] = Field(
        default_factory=dict,
        description="文件路径到描述的字典映射（如 {'output/chart.png': '销售趋势图'}）。"
    )
