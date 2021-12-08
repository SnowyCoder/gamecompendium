# -*- coding: utf-8 -*-
"""
Created on Sun Dec  5 09:46:32 2021

@author: scriviciAJEJE
"""

import time
import nltk
# third-party imports
import pandas as pd
import requests
from requests.exceptions import SSLError
pd.set_option("max_columns", 100)

from whoosh import fields
from whoosh.fields import Schema
from whoosh.filedb.filestore import Storage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser
import datetime
from analyzers import keep_numbers_analyzer

#Amount of games to request data of
REQUEST_AMOUNT = 5

schema = Schema(
    id=fields.ID(stored=True, unique=True),
    name=fields.TEXT(stored=True, analyzer=keep_numbers_analyzer()),
    storyline=fields.TEXT(stored=True),
    summary=fields.TEXT(stored=True),
    genres=fields.KEYWORD(stored=True),
    platforms=fields.KEYWORD(stored=True),
    dev_companies=fields.KEYWORD(stored=True),
    release_date=fields.DATETIME(stored=True),
)

def get_request(url, parameters=None):
    """Return json-formatted response of a get request using optional parameters.
    
    Parameters
    ----------
    url : string
    parameters : {'parameter': 'value'}
        parameters to pass as part of get request
    
    Returns
    -------
    json_data
        json-formatted response (dict-like)
    """
    try:
        response = requests.get(url=url, params=parameters)
    except SSLError as s:
        print('SSL Error:', s)
        
        for i in range(5, 0, -1):
            print('\rWaiting... ({})'.format(i), end='')
            time.sleep(1)
        print('\rRetrying.' + ' '*10)
        
        # recusively try again
        return get_request(url, parameters)
    
    if response:
        return response.json()
    else:
        # response is none usually means too many requests. Wait and try again 
        print('No response, waiting 10 seconds...')
        time.sleep(10)
        print('Retrying.')
        return get_request(url, parameters)
    
url = "https://steamspy.com/api.php"
parameters = {"request": "all"}

# request 'all' from steam spy and parse into dataframe
json_data = get_request(url, parameters=parameters)
steam_spy_all = pd.DataFrame.from_dict(json_data, orient='index')

# generate sorted app_list from steamspy data
app_list = steam_spy_all[['appid', 'name']].sort_values('appid').reset_index(drop=True)

#for index, row in app_list.iterrows():
 #   print(row['appid'], row['name'])
    
def get_app_data(start, stop, parser, pause):
    """Return list of app data generated from parser.
    
    parser : function to handle request
    """
    app_data = []
    
    # iterate through each row of app_list, confined by start and stop
    for index, row in app_list[start:stop].iterrows():
        print('Current index: {}'.format(index), end='\r')
        
        appid = row['appid']
        name = row['name']

        # retrive app data for a row, handled by supplied parser, and append to list
        data = parser(appid, name)
        app_data.append(data)

        time.sleep(pause) # prevent overloading api with requests
    
    return app_data

def parse_steam_request(appid, name):
    """Unique parser to handle data from Steam Store API.
    
    Returns : json formatted data (dict-like)
    """
    url = "http://store.steampowered.com/api/appdetails/"
    parameters = {"appids": appid}
    
    json_data = get_request(url, parameters=parameters)
    json_app_data = json_data[str(appid)]
    
    if json_app_data['success']:
        data = json_app_data['data']
    else:
        data = {'name': name, 'steam_appid': appid}
        
    return data

#transform steam's date format
def format_date(idx,listdata):
    a = listdata[idx]['release_date']['date']
    a = nltk.word_tokenize(a)
    if a[1] == 'Jan':
        month = 1
    if a[1] == 'Feb':
        month = 2
    if a[1] == 'Mar':
        month = 3
    if a[1] == 'Apr':
        month = 4
    if a[1] == 'May':
        month = 5
    if a[1] == 'Jun':
        month = 6
    if a[1] == 'Jul':
        month = 7
    if a[1] == 'Aug':
        month = 8
    if a[1] == 'Sep':
        month = 9
    if a[1] == 'Oct':
        month = 10
    if a[1] == 'Nov':
        month = 11
    if a[1] == 'Dec':
        month = 12
    gamedate = datetime.datetime(int(a[3]),month,int(a[0]))
    return gamedate


STORAGE_NAME = 'steam'
async def init_index(storage: Storage) -> Index:
    if not storage.index_exists(STORAGE_NAME):
        print("STEAM index not found, creating!")
        
        
        index = storage.create_index(schema, indexname=STORAGE_NAME)
        writer = index.writer()
        
        #actually obtain the data
        datalist = get_app_data(0,REQUEST_AMOUNT,parse_steam_request,0)
        
        for idx in range(0,(len(datalist))):
            
            genres_list = []
            for i in range(len(datalist[idx]['genres'])):
                genres_list.append(datalist[idx]['genres'][i]['description'])
                
            dev_list = datalist[idx]['developers']
            dev_list.extend(datalist[idx]['publishers'])
            
            if datalist[idx]['release_date']['coming_soon'] == True:
                game_date = datetime.datetime(0,0,0)
            else:
                game_date = format_date(idx,datalist)
            
            writer.add_document(
                id=str(datalist[idx]['steam_appid']),
                name=datalist[idx]['name'],
                genres=','.join(genres_list),
                platforms=','.join(datalist[idx]['platforms']),
                dev_companies=','.join(dev_list),
                release_date=game_date,
                storyline=datalist[idx]['detailed_description'],
                summary=datalist[idx]['about_the_game']
            )
        
        writer.commit()
    else:
        index = storage.open_index(STORAGE_NAME, schema)

    return index


async def test(index: Index):
    qp = MultifieldParser(('name', 'storyline', 'summary'), schema)
    with index.searcher() as searcher:
        while True:
            try:
                query_txt = input(">")
            except KeyboardInterrupt:
                return
            except EOFError:
                return

            query = qp.parse(query_txt)
            res = searcher.search(query, limit=5)
            print(f'Found {len(res)} results:')
            for (i, x) in enumerate(res):
                print(f"{i + 1}. {x['name']} - {x['dev_companies']} {x.get('release_date')}")


#Generic utility copypaste, ignore
# for idx in range(0,(len(datalist))):
#    print(datalist[idx]['name'])