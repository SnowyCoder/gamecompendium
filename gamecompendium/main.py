import asyncio
import os
from whoosh.filedb.filestore import FileStorage

#import igdb
import steam

INDEX_DIR = 'indexes'

async def main():
    if not os.path.exists(INDEX_DIR):
        os.mkdir(INDEX_DIR)
    storage = FileStorage(INDEX_DIR)

    #igdbIndex = await igdb.init_index(storage)
    #await igdb.test(index)
    steamIndex = await steam.init_index(storage)
    await steam.test(steamIndex)


if __name__ == '__main__':
    asyncio.run(main())
