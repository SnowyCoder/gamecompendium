import asyncio
import os
from whoosh.filedb.filestore import FileStorage

#import igdb
import steam

INDEX_DIR = 'indexes'
#separated it for now just in case
INDEX_DIR_STEAM = 'steam_index'

async def main():
    #if not os.path.exists(INDEX_DIR):
    #    os.mkdir(INDEX_DIR)
    #storage = FileStorage(INDEX_DIR)
    #index = await igdb.init_index(storage)
    #await igdb.test(index)
    
    if not os.path.exists(INDEX_DIR_STEAM):
        os.mkdir(INDEX_DIR_STEAM)
    steamStorage = FileStorage(INDEX_DIR_STEAM)
    steamIndex = await steam.init_index(steamStorage)
    await steam.test(steamIndex)
    


if __name__ == '__main__':
    asyncio.run(main())
