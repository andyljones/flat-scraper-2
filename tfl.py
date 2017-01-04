# -*- coding: utf-8 -*-
"""
Created on Sun May  8 11:19:10 2016

@author: andyjones
"""
import networkx as nx
import scipy as sp
import json
import pandas as pd
import requests
from diskcache import Cache

ROOT = 'https://api.tfl.gov.uk/'
KEYS = json.load(open('credentials.json'))

DEFAULT_ORIGIN = '940GZZLUGPK'

def call_api(endpoint, **kwargs):
    result = requests.get(ROOT + endpoint, params=dict(KEYS, **kwargs))
    return json.loads(result.content.decode())
    
def get_routes():
    with Cache('cache') as cache:
        if 'tfl/routes' in cache:
            return cache['tfl/routes']
    
    data = call_api('Line/Route')
    results = []
    for route in data:
        for section in route['routeSections']:
            results.append({
                'route_id': route['id'],
                'mode': route['modeName'],
                'route_name': route['name'],
                'destination_id': section['destination'],
                'destination_name': section['destinationName'],
                'origin_id': section['originator'],
                'origin_name': section['originationName'],
                'section_name': section['name'],
                'direction': section['direction']
            })
            
    results = pd.DataFrame(results)
    
    with Cache('cache') as cache:
        cache['tfl/routes'] = results
        
    return results
    
def get_timetable(route_id, origin, destination):
    key = 'tfl/timetables/{}-{}-{}.json'.format(route_id, origin, destination)
    with Cache('cache') as cache:
        if key not in cache:
            print('Fetching timetable {}-{}-{}'.format(route_id, origin, destination))
            cache[key] = call_api('Line/{}/Timetable/{}/to/{}'.format(route_id, origin, destination))
        
        return cache[key]            
            
def walk_timetables(routes):    
    for _, row in routes.iterrows():
        data = get_timetable(row['route_id'], row['origin_id'], row['destination_id'])
        if ('timetable' in data) and (len(data['timetable']['routes']) > 0):
            yield data
        
def get_stops(route_id):
    key = 'tfl/stoppoints/{}.json'.format(route_id)
    with Cache('cache') as cache:
        if key not in cache:
            print('Fetching {}'.format(route_id))
            cache[key] = call_api('Line/{}/StopPoints'.format(route_id))

        return cache[key]
            
def walk_stops(routes):
    for _, row in routes.iterrows():
        data = get_stops(row['route_id'])
        yield data    
        
def get_locations(routes):
    with Cache('cache') as cache:
        if 'tfl/locations' in cache:
            return cache['tfl/locations']
    
    results = []
    for stops in walk_stops(routes):
        for stop in stops:
            results.append({
                'id': stop['id'],
                'naptan': stop['naptanId'],
                'station_naptan': stop.get('stationNaptan', ''),
                'hub_naptan': stop.get('hubNaptanCode', ''),
                'name': stop['commonName'],
                'latitude': stop['lat'],
                'longitude': stop['lon']
            })
            
    results = pd.DataFrame(results).drop_duplicates('naptan').set_index('naptan')
    
    with Cache('cache') as cache:
        cache['tfl/locations'] = results
        
    return results
    
def get_edges(routes):
    with Cache('cache') as cache:
        if 'tfl/edges' in cache:
            return cache['tfl/edges']
    
    results = []
    for timetable in walk_timetables(routes):
        origin = timetable['timetable']['departureStopId']
        for route in timetable['timetable']['routes']:
            for intervals in route['stationIntervals']:
                stops = [origin] + [x['stopId'] for x in intervals['intervals']]
                edges = [[s, t] for s, t in zip(stops, stops[1:])]
                
                times = [0] + [x['timeToArrival'] for x in intervals['intervals']]
                weights = list(sp.diff(sp.array(times)))
                
                results.extend([[s, t, w] for (s, t), w in zip(edges, weights)])
    
    results = pd.DataFrame(results, columns=['origin', 'destination', 'time'])
    results = results.groupby(['origin', 'destination']).mean()
    
    with Cache('cache') as cache:
        cache['tfl/edges'] = results
    
    return results

def get_travel_times(edges, locations, origin=DEFAULT_ORIGIN, transit_time=5):
    with Cache('cache') as cache:
        if 'tfl/travel_times' in cache:
            return cache['tfl/travel_times']
    
    G = nx.Graph()
    G.add_weighted_edges_from(map(tuple, list(edges.reset_index().values)))
    
    for naptan, location in locations.iterrows():
        if location.hub_naptan != '':
            G.add_weighted_edges_from([(naptan, location.hub_naptan, transit_time)])
            
    times = nx.single_source_dijkstra_path_length(G, origin, weight='weight')
    times = pd.Series(times)
    
    with Cache('cache') as cache:
        cache['tfl/travel_times'] = times
    
    return times
    
def cache():
    routes = get_routes()
    edges = get_edges(routes)
    locations = get_locations(routes)
    
    names = locations['name'].to_dict()
    times = get_travel_times(edges, locations)
    times = times.loc[list(names.keys())].rename(names).dropna()
    
    return edges, locations, times