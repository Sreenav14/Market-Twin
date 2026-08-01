""" Request and results models for browser testing """

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

class BrowserRequest(BaseModel);