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
import humanhash
import os
import pickle
import matplotlib.pyplot as plt
from flask import Flask, render_template, send_from_directory, request, jsonify

from diskcache import Cache

FIELDS_TO_FORMAT = [
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
    'longitude',
    'num_bathrooms',
    'num_bedrooms',]

WEEKS_PER_MONTH = 365/12./7
EARTH_CIRCUMFERENCE = 40075
KM_PER_MILE = 1.609
MEAN_RADIUS_OF_POINT_IN_UNIT_DISC = 2./3.
WALKING_SPEED = 5./60.#km per minute
MAX_DISTANCE_FROM_STATION_IN_KM = KM_PER_MILE*0.5
MAX_DISTANCE_FROM_STATION_IN_MINS = int(MEAN_RADIUS_OF_POINT_IN_UNIT_DISC*MAX_DISTANCE_FROM_STATION_IN_KM/WALKING_SPEED)

app = Flask(__name__)

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

            
def format_listings():
    
    times = tfl.get_station_travel_times()
    
    results = []
    for fn in os.listdir('listings'):
        listing = pickle.load(open('listings/' + fn, 'rb'))
        listing['is_room'] = ('Room to rent</h2>' in listing['page_text'])

        for field in FIELDS_TO_FORMAT:
            listing[field] = listing['search_result'][field]
        
        travel_times = {s: times[s] + t for s, t in distances_from_stations(listing).items()}
        listing['travel_time'] = int(min(travel_times.values())) + 3
      
        listing['price'] = int(10*sp.around(float(listing['search_result']['price'])*WEEKS_PER_MONTH/10))
            
        station_names = [n.replace(' Underground Station', '') for n in listing['station_name']]
        listing['printable_station_names'] = ', '.join(station_names)
        
        listing['humanhash'] = humanhash.humanhash(listing['listing_id']).decode()
        
        del listing['page_text']
        del listing['search_result']
        results.append(listing)
    results = pd.DataFrame(results).sort_values('listing_id').reset_index(drop=True)
    
    return results

def get_bg_color(value, lower, upper, cmap=plt.cm.viridis):
    relative_value = sp.clip((value - lower)/(upper - lower), 0, 1)
    background_color = tuple([int(255*c) for c in cmap(relative_value)[:3]])
    
    return background_color
    
def get_text_color(bg_color):
    is_dark = sum(bg_color[:3])/(3*255) < 0.5
    text_color = (230, 230, 230) if is_dark else (50, 50, 50)
    
    return text_color
    
@app.route('/')
def index():
    return render_template('index.j2')

@app.route('/listings')
def listings():
    with Cache('cache') as cache:
        if 'listings' not in cache:
            cache['listings'] = format_listings()
        listings = cache['listings']
        
    price = (float(request.args.get('price_lower', 0)), float(request.args.get('price_upper', sp.inf)))
    time = (float(request.args.get('time_lower', 0)), float(request.args.get('time_upper', sp.inf)))
    lower_index, upper_index = request.args.get('index_lower'), request.args.get('index_upper')
    
    matches = (listings
                   .loc[lambda df: df.num_bedrooms.astype(int) > 0]
                   .loc[lambda df: df.photo_filenames.apply(len) > 0]
                   .loc[lambda df: ~df.is_room]
                   .loc[lambda df: df.price.between(*price)]
                   .loc[lambda df: df.travel_time.between(*time)]
                   .loc[lambda df: ~df[['latitude', 'longitude', 'price', 'agent_name', 'description']].duplicated()]
                   .sort_values(['first_published_date'], ascending=False))
    
    subset = matches.iloc[int(lower_index):int(upper_index)]
    
    subset['price_bg_color'] = subset.price.apply(get_bg_color, args=(price[0], price[1], plt.cm.magma))
    subset['price_text_color'] = subset.price_bg_color.apply(get_text_color)
    
    subset['time_bg_color'] = subset.travel_time.apply(get_bg_color, args=(time[0], time[1], plt.cm.magma))
    subset['time_text_color'] = subset.time_bg_color.apply(get_text_color)
    
    subset['printable_published_date'] = subset.first_published_date.pipe(pd.to_datetime).dt.strftime('%-d %b')
                          
    return jsonify({'num-results': len(matches), 
                    'listings': [l.to_dict() for _, l in subset.iterrows()]})
            
        
    
    
@app.route('/photos/<filename>')
def photos(filename):
    return send_from_directory('photos', filename)