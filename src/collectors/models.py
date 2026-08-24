"""
数据模型
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Tweet:
    tweet_id: str
    author: str          # @handle
    author_name: str = ""  # 显示名
    content: str = ""
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    views: int = 0
    created_at: str = ""
    url: str = ""
    tags: list = field(default_factory=list)
    assets: list = field(default_factory=list)   # [(symbol, type), ...]
    themes: list = field(default_factory=list)
    quality_score: float = 0.0
    is_kol: bool = False
    comments: list = field(default_factory=list)  # list[Tweet]
