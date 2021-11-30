import asyncio
import os

from whoosh.filedb.filestore import FileStorage

import igdb

INDEX_DIR = 'indexes'


async def main():
    if not os.path.exists(INDEX_DIR):
        os.mkdir(INDEX_DIR)
    storage = FileStorage(INDEX_DIR)
    index = await igdb.init_index(storage)
    await igdb.test(index)


if __name__ == '__main__':
    asyncio.run(main())
