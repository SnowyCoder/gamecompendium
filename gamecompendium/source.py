from typing import Protocol

from whoosh.fields import Schema
from whoosh.index import FileIndex

from resolver import EntityResolver


class Source(Protocol):
    """Name of the data source"""
    name: str
    """Schema of the IR system"""
    schema: Schema

    async def scrape(self) -> None:
        """Download the data and store it for later"""

    async def reindex(self, index: FileIndex, resolver: EntityResolver) -> None:
        """
        Use previously downloaded data to create an index

        If there is no scraped data, it should be downloaded too."""


