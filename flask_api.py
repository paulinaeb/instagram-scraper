from flask import Flask, request, jsonify, Response, make_response, url_for
from flask_cors import CORS
from bson import json_util
from flask_pymongo import PyMongo
from flask_celery import make_celery
import config
import scraper
import os
import random
import time
from datetime import datetime
import pandas as pd

flask_app = Flask(__name__)
CORS(flask_app)
flask_app.config['MONGO_URI'] = config.MONGO_URI
flask_app.config['CELERY_BROKER_URL'] = config.CELERY_BROKER_URL

celery = make_celery(flask_app)
mongo = PyMongo(flask_app)

# Convierte a json
def parse(data):
    return json_util.dumps(data)


@flask_app.errorhandler(404)
def not_found(error=None):
    # jsonify so we can add status code
    response = jsonify({
        'message': f'Rey, error {request.url}',
        'status': 404
    })
    response.status_code = 404
    return response

# Lista de scrapes ordenados por fecha
@flask_app.route('/scraped-profiles', methods=['GET'])
def get_scraped_profiles():
    collection = mongo.db.scraped_profiles
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    offset = (page-1) * page_size

    total = collection.count_documents({})
    users = collection.find({}).sort('_id', -1).skip(offset).limit(page_size)

    res = {'rows': list(users), 'count': total}
    jsonRes = parse(res)
    return Response(jsonRes, mimetype='application/json')

# Lista de usuarios que interactuaron con una cuenta scrapeada
@flask_app.route('/scrape-info', methods=['GET'])
def get_scrape_info():
    users = mongo.db.user_engagement
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    sort_by = request.args.get('sortBy', None)
    sort_order = request.args.get('order', None)
    user_id = request.args.get('userId')
    timestamp = int(request.args.get('timestamp')) / 1000.0 # Python timestamp es segundos y mongodb es en ms since epoch

    parsed_date = datetime.utcfromtimestamp(timestamp)
    offset = (page-1) * page_size

    query = {'profile_id': user_id, 'date': parsed_date}
    total = users.count_documents(query)

    if sort_by and sort_order:
        engagements = users.find(query).sort(sort_by, int(sort_order)).skip(offset).limit(page_size)
    else:
        engagements = users.find(query).skip(offset).limit(page_size)
    
    res = {'rows': list(engagements), 'count': total}
    jsonRes = parse(res)
    return Response(jsonRes, mimetype='application/json')

# Lista de posts de una cuenta a los que el usuario indicado comento o dio like
@flask_app.route('/scrape-info/liked-posts', methods=['GET'])
def get_user_interacted_posts():
    username = request.args.get('username')
    profile_id = request.args.get('profileId')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    sort_by = request.args.get('sortBy', None)
    sort_order = request.args.get('order', None)
    timestamp = int(request.args.get('timestamp')) / 1000.0

    parsed_date = datetime.utcfromtimestamp(timestamp)
    offset = (page-1) * page_size

    query = {
        'profile_id': profile_id,
        'scraped_date': parsed_date,
        '$or': [{'likers': username}, {'commenters': username}]
    }

    pipeline = [
        {'$match': query},
        {
            '$project': {
                'short_code': 1,
                'likes_count': 1,
                'comments_count': 1,
                'engagement': 1,
                'has_liked': {'$in': [username, '$likers']},
                'has_commented': {'$in': [username, '$commenters']},
            }
        }
    ]

    if sort_by and sort_order:
        pipeline.append({'$sort': {sort_by: int(sort_order)}})

    pipeline.append({'$skip': offset})
    pipeline.append({'$limit': page_size})

    total = mongo.db.posts.count_documents(query)
    posts = mongo.db.posts.aggregate(pipeline)
    res = {'rows': list(posts), 'count': total}
    jsonRes = parse(res)

    return Response(jsonRes, mimetype='application/json')

# Inicia un nuevo scrape
@flask_app.route('/scrape', methods=['POST'])
def start_scraper():
    body = request.json
    username = body.get('username')
    email = body.get('email')
    scraping_user = body.get('scrapingUser', None)
    scraping_pass = body.get('scrapingPass', None)

    if not username or not email:
        return Response(parse({'message': 'missing params'}),  status=400, mimetype='application/json')

    if not scraping_user or not scraping_pass:
        scraping_user = 'platanitomaduro42'
        scraping_pass = 'platanito42'

    scrape_user.delay(username, email, scraping_user, scraping_pass)
    return Response(parse({'message': f'started scraping {username}'}), status=202, mimetype='application/json')

# CSV de la lista de scrapes
@flask_app.route('/export-csv-scrapes', methods=['GET'])
def export_scraped_profiles():
    cursor = mongo.db.scraped_profiles.find({}).sort('_id', -1)
    df = pd.DataFrame(list(cursor))
    del df['_id']
    del df['id']

    resp = make_response(df.to_csv())
    resp.headers["Content-Disposition"] = "attachment; filename=scrapes.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp

# CSV de la lista de usuarios que interactuaron con una cuenta
@flask_app.route('/export-csv-engagements')
def export_engagements_csv():
    users = mongo.db.user_engagement
    user_id = request.args.get('userId')
    timestamp = int(request.args.get('timestamp')) / 1000.0

    parsed_date = datetime.utcfromtimestamp(timestamp)
    cursor = users.find({'profile_id': user_id, 'date': parsed_date})

    df = pd.DataFrame(list(cursor))
    del df['_id']
    del df['profile_id']

    resp = make_response(df.to_csv())
    resp.headers["Content-Disposition"] = "attachment; filename=user_engagement.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp

# CSV de la lista de posts de un scrape con los que una persona dada interactuo
@flask_app.route('/export-csv-posts')
def export_posts_csv():
    posts = mongo.db.posts
    username = request.args.get('username')
    profile_id = request.args.get('profileId')
    timestamp = int(request.args.get('timestamp')) / 1000.0

    parsed_date = datetime.utcfromtimestamp(timestamp)
    query = {
        'profile_id': profile_id,
        'scraped_date': parsed_date,
        '$or': [{'likers': username}, {'commenters': username}]
    }

    pipeline = [
        {'$match': query},
        {
            '$project': {
                'short_code': 1,
                'likes_count': 1,
                'comments_count': 1,
                'engagement': 1,
                'has_liked': {'$in': [username, '$likers']},
                'has_commented': {'$in': [username, '$commenters']},
            }
        }
    ]
    cursor = posts.aggregate(pipeline)

    df = pd.DataFrame(list(cursor))
    del df['_id']

    resp = make_response(df.to_csv())
    resp.headers["Content-Disposition"] = "attachment; filename=interacted_posts.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp


# Celery tasks
@celery.task(name='flask_api.scrape_user')
def scrape_user(username, email, scraping_user, scraping_pass):
    return scraper.scrape_user(username, email, scraping_user, scraping_pass)


if __name__ == '__main__':
    flask_app.run(debug=True)
