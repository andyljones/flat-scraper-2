import json
import tfl
import pandas as pd
import os
import datetime
import time
import requests
import logging
import interactive_console_options
import pickle
from diskcache import Cache
from image_scraper import save_photos

WEEKS_PER_MONTH = 365/12./7

CACHE_LENGTH = 60*60#seconds
API_LIMIT = 100
REQUEST_DELAY = 1

ZOOPLA_URL = 'http://api.zoopla.co.uk/api/v1/property_listings.js'

def wait_for_quota():
    while True:
        limit = pd.datetime.now() - pd.Timedelta(hours=1)
        with Cache('callcache') as cache:
            cache['zoopla_calls'] = [c for c in cache.get('zoopla_calls', []) if c > limit]
            
            if len(cache['zoopla_calls']) < API_LIMIT - 1:
                cache['zoopla_calls'] = cache.get('zoopla_calls', []) + [pd.datetime.now()]
                return
            else:
                print('There have been {} calls in the past hour'.format(len(cache['zoopla_calls'])))
            
            time.sleep(10)        
        

def zoopla_listings(**kwargs):
    kwargs['api_key'] = json.load(open('credentials.json'))['zoopla_key']      
    kwargs['page_size'] = 100
    kwargs['page_number'] = 1
    listings = []
    while True:
        wait_for_quota()
        r = requests.get(ZOOPLA_URL, params=kwargs)   
        r.raise_for_status()
        
        result = json.loads(r.content.decode())
        
        listings.extend(result['listing'])
        kwargs['page_number'] += 1

        logging.debug('Fetched {} results'.format(len(listings)))
        
        limit = min(result['result_count'], kwargs.get('max_results', 10000))
        if len(listings) >= limit:
            break
                
    return listings

def get_coords(station_name):
    coords = json.load(open('station_coords.json', 'r'))

    if station_name in coords:
        return coords[station_name]

    long_station_name = station_name + ' Underground Station'
    if long_station_name in coords:
        return coords[long_station_name]

def get_search_params(stations=None):
    params = dict(
        order_by='age',
        listing_status='rent',
        minimum_price=0,
        furnished='furnished',
        description_style=1)

    params['radius'] = 0.5
    params['minimum_beds'] = 0
    params['maximum_beds'] = 1
    params['maximum_price'] = int(2000/WEEKS_PER_MONTH)

    if stations is None:
        stations = (tfl.get_station_travel_times()
                        .loc[lambda s: (s < 20) & (s.index.str.contains('Underground'))]
                        .index)
    
    results = {}
    for station_name in stations:
        lat, lon = get_coords(station_name)
        params_for_name = params.copy()
        params_for_name['latitude'] = lat
        params_for_name['longitude'] = lon

        results[station_name] = params_for_name

    return results

def create_storable_listing(station_name, start_time, listing):
    page_text = requests.get(listing['details_url']).text
    time.sleep(REQUEST_DELAY)
    
    return dict(
        station_name=[station_name],
        photo_filenames=save_photos(page_text, listing['listing_id']),
        store_times=[str(start_time)],
        page_text=page_text,
        search_result=listing
    )

def update_storable_listing(station_name, start_time, stored_listing, listing):
    listing_id = listing['listing_id']
    if (listing['last_published_date'] > stored_listing['search_result']['last_published_date']):
        logging.info(str.format('Updating listing #{}', listing_id))
        storable_listing = create_storable_listing(station_name, start_time, listing)
    else:
        logging.debug(str.format('No change in listing #{}', listing_id))
        storable_listing = stored_listing.copy()
        
    storable_listing['station_name'] = list(set(stored_listing['station_name']).union([station_name]))
    storable_listing['store_times'] = list(set(stored_listing['store_times']).union([str(start_time)]))

    return storable_listing

def store_listing(station_name, start_time, listing):
    listing_id = listing['listing_id']
    path = 'listings/{}.pkl'.format(listing_id)
    
    if not os.path.exists('listings'):
        os.makedirs('listings')
    
    if not os.path.exists(path):
        logging.info(str.format('Storing listing #{}', listing_id))
        storable_listing = create_storable_listing(station_name, start_time, listing)
    else:
        stored_listing = pickle.load(open(path, 'rb'))
        storable_listing = update_storable_listing(station_name, start_time, stored_listing, listing)

    pickle.dump(storable_listing, open(path, 'wb+'))
    
def get_listing(listing_id):
    path = 'listings/{}.pkl'.format(listing_id)
    return pickle.load(open(path, 'rb'))
    
def scrape_listings_and_images(skip=0):
    start_time = datetime.datetime.now()
    
    for i, (station_name, station_params) in enumerate(get_search_params().items()):
        if i < skip:
            logging.info('Skipping station {}, {}'.format(i, station_name))
            continue
        
        listings = list(zoopla_listings(**station_params))
        logging.info(str.format('{} listings to store for station {}, {}', len(listings), i+1, station_name))
        for listing in listings:
            try:
                store_listing(station_name, start_time, listing)
            except Exception as e:
                logging.warning(str.format('Failed to save listing {}. Exception: {}', listing['listing_id'], e))
                
