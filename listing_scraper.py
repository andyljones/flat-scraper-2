import json
import pandas as pd
import os
import datetime
import time
import requests
import logging
from diskcache import Cache

from image_scraper import save_photos
from bs4 import BeautifulSoup

WEEKS_PER_MONTH = 365/12./7

FIELDS_TO_STORE = [
    'listing_id',
    'status',
    'price',
    'description',
    'details_url',
    'first_published_date',
    'last_published_date',
    'agent_name',
    'agent_phone',
    'latitude',
    'longitude']

REQUEST_DELAY = 1#seconds
CACHE_LENGTH = 60*60#seconds

ZOOPLA_URL = 'http://api.zoopla.co.uk/api/v1/property_listings.js'

def zoopla_listings(**kwargs):
    kwargs['api_key'] = json.load(open('credentials.json'))['zoopla_key']        
    key = 'listings/' + str(hash(tuple(sorted(kwargs.items()))))
    
    kwargs['page_size'] = 100
    kwargs['page_number'] = 1
    with Cache('cache') as cache:
        if key not in cache:
            listings = []
            while True:
                r = requests.get(ZOOPLA_URL, params=kwargs)   
                time.sleep(REQUEST_DELAY)
                r.raise_for_status()
                result = json.loads(r.content.decode())
                
                listings.extend(result['listing'])
                kwargs['page_number'] += 1

                logging.debug('Fetched {} results'.format(len(listings)))
                
                limit = min(result['result_count'], kwargs.get('max_results', 10000))
                if len(listings) >= limit:
                    break
                
            cache.add(key, listings, CACHE_LENGTH)    
            
        return cache[key]

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

    options = json.load(open('config.json', 'r'))
    params['radius'] = options['radius']
    params['minimum_beds'] = 0
    params['maximum_beds'] = options['beds']
    params['maximum_price'] = int(options['max_price']/WEEKS_PER_MONTH)

    results = {}
    stations = options['stations'] if stations is None else stations
    for station_name in stations:
        lat, lon = get_coords(station_name)
        params_for_name = params.copy()
        params_for_name['latitude'] = lat
        params_for_name['longitude'] = lon

        results[station_name] = params_for_name

    return results

def scrape_property_info(page_text):
    bs = BeautifulSoup(page_text, 'html.parser')
    tag = bs.find('h3', text='Property info').find_next_sibling('ul')
    if tag:
        return tag.encode_contents()
    else:
        return ''

def create_storable_listing(station_name, start_time, listing):
    page_text = requests.get(listing['details_url']).text

    return dict(
        {field: listing[field] for field in FIELDS_TO_STORE},
        station_name=[station_name],
        photo_filenames=save_photos(page_text, listing['listing_id']),
        property_info=scrape_property_info(page_text),
        store_times=[str(start_time)]
    )

def update_storable_listing(station_name, start_time, stored_listing, listing):
    storable_listing = create_storable_listing(station_name, start_time, listing)
    storable_listing['station_name'] = list(set(stored_listing['station_name']).union(storable_listing['station_name']))
    storable_listing['store_times'] = list(set(stored_listing['store_times']).union(storable_listing['store_times']))

    return storable_listing

def store_listing(station_name, start_time, listing):
    listing_id = listing['listing_id']
    key = 'listings/{}'.format(listing_id)
    with Cache('cache') as cache:
        stored_listing = cache.get(key, {})
    

    if not stored_listing:
        logging.info(str.format('Storing listing #{}', listing_id))
        stored_listing = create_storable_listing(station_name, start_time, listing)
        time.sleep(REQUEST_DELAY)
    elif (listing['last_published_date'] > stored_listing['last_published_date']):
        logging.info(str.format('Updating listing #{}', listing_id))
        stored_listing = update_storable_listing(station_name, start_time, stored_listing, listing)
        time.sleep(REQUEST_DELAY)
    else:
        logging.debug(str.format('No change in listing #{}', listing_id))
        stored_listing['station_name'] = list(set(stored_listing['station_name']).union([station_name]))
        stored_listing['store_times'] = list(set(stored_listing['store_times']).union([str(start_time)]))

    with Cache('cache') as cache:
        cache[key] = stored_listing

def scrape_listings_and_images():
    start_time = datetime.datetime.now()
    
    for i, (station_name, station_params) in enumerate(get_search_params().items()):
        listings = list(zoopla_listings(**station_params))
        logging.info(str.format('{} listings to store for station {}, {}', len(listings), i+1, station_name))
        for listing in listings:
            store_listing(station_name, start_time, listing)

def survey_prices(stations):
    
    results = []
    for i, (station_name, station_params) in enumerate(get_search_params(stations).items()):     
        print('Surveying {} of {}'.format(i, len(stations)))
        with Cache('cache') as cache:
            key = 'survey/' + station_name
            if key not in cache:        
                listings = list(zoopla_listings(**station_params))
                cache[key] = [l['price'] for l in listings]
            
            results.append(pd.Series(cache[key], [station_name]*len(cache[key])))
    
    results = WEEKS_PER_MONTH*pd.to_numeric(pd.concat(results))
    
    return results
    
# import interactive_console_options
# scrape_listings_and_images()
