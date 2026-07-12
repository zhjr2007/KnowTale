import asyncio
import logging
from pathlib import Path

import httpx
import fitz

from app.config import settings

logger = logging.getLogger(__name__)
