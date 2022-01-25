import asyncio
import os
from whoosh.filedb.filestore import FileStorage

#import igdb
import steam
from app import App
from resolver import EntityResolver

INDEX_DIR = 'indexes'


async def main():
    app = App()
    await app.init()
    app.prompt()


async def main_test():
    if not os.path.exists(INDEX_DIR):
        os.mkdir(INDEX_DIR)
    storage = FileStorage(INDEX_DIR)

    #igdbIndex = await igdb.init_index(storage, EntityResolver())
    #await igdb.test(index)
    steamIndex = await steam.init_index(storage, EntityResolver())
    await steam.test(steamIndex)


if __name__ == '__main__':
    asyncio.run(main())
