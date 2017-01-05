#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan  5 19:30:04 2017

@author: andyjones
"""

import re
import scipy as sp
import pandas as pd
import listing_scraper
import tfl

from jinja2 import Template

from diskcache import Cache

WEEKS_PER_MONTH = 365/12./7
EARTH_CIRCUMFERENCE = 40075
KM_PER_MILE = 1.609
MEAN_RADIUS_OF_POINT_IN_UNIT_DISC = 2./3.
WALKING_SPEED = 5./60.#km per minute
MAX_DISTANCE_FROM_STATION_IN_KM = KM_PER_MILE*0.5
MAX_DISTANCE_FROM_STATION_IN_MINS = int(MEAN_RADIUS_OF_POINT_IN_UNIT_DISC*MAX_DISTANCE_FROM_STATION_IN_KM/WALKING_SPEED)

def walking_distance(lat_1, lon_1, lat_2, lon_2):
    change_in_lat = EARTH_CIRCUMFERENCE*(lat_1 - lat_2)/360

    average_lat = (lat_1 + lat_2)/2
    circumference_at_lat = EARTH_CIRCUMFERENCE*sp.cos(sp.pi/180*average_lat)
    change_in_lon = circumference_at_lat*(lon_1 - lon_2)/360

    distance_in_km = sp.sqrt(change_in_lat**2 + change_in_lon**2)
    distance_in_minutes = distance_in_km/WALKING_SPEED

    return int(sp.ceil(distance_in_minutes))

def distance_from_station(lat, lon, station_name):
    station_lat, station_lon = listing_scraper.get_coords(station_name)
    return walking_distance(lat, lon, station_lat, station_lon)

def distances_from_stations(listing):
    if 'latitude' in listing and 'longitude' in listing:
        lat, lon = listing['latitude'], listing['longitude']
        return {name: distance_from_station(lat, lon, name) for name in listing['station_name']}
    else:
        return {name: MAX_DISTANCE_FROM_STATION_IN_MINS for name in listing['station_name']}

            
def get_listings():
    with Cache('cache') as cache:
        listings = {k.split('/')[-1]: cache[k] for k in cache if re.match('listings/\d{8}$', k)}
        
    times = tfl.get_fast_stations()
    results = {}
    for k, l in listings.items():
        l = pd.Series(l)
        travel_times = {s: times[s] + t for s, t in distances_from_stations(l).items()}
        l['travel_time'] = int(min(travel_times.values())) + 3
        results[k] = l
    results = pd.concat(results, 1).T
    results['price'] = (results['price'].astype(float) * WEEKS_PER_MONTH).div(10).apply(sp.around).mul(10).astype(int)
    results['printable_station_names'] = results.station_name.apply(lambda x: ', '.join([n.replace(' Underground Station', '') for n in x]))
    
    return results
    
def get_rendered_page():
    listings = get_listings().sort_values('travel_time').head()
    
    template = Template(open('templates/index.j2').read())
    rendered = template.render(listings=[l for _, l in listings.iterrows()])
    
    with open('index.html', 'w+') as f:
        f.write(rendered)