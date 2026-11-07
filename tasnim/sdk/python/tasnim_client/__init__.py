# -*- coding: utf-8 -*-
"""tasnim_client — Python SDK for the Tasnim Web V1 read-only API
(PCM-20.6.4, scope C).

Standard library only (urllib) — no third-party dependencies, by design:
the corpus pipelines must not grow new deps. Works on Python 3.9+.

See ``README.md`` next to this package and
``docs/PCM-20.6.4-INTEGRATION.md`` in the repository for the full
integration guide (rate limits, pagination, ETag caching, error table).

    from tasnim_client import TasnimClient
    c = TasnimClient("https://tasnim.ai.ismc.ir")
    print(c.get_page(2)["visible_content"]["text"])
"""
from .client import (API_PREFIX, Page, TasnimAPIError, TasnimClient,
                     TasnimClientError, TopicDetail)

__version__ = "1.0.0"

__all__ = [
    "API_PREFIX",
    "Page",
    "TopicDetail",
    "TasnimAPIError",
    "TasnimClient",
    "TasnimClientError",
    "__version__",
]
