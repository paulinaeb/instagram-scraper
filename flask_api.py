from flask import Flask, request, jsonify, Response, url_for
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


flask_app = Flask(__name__)
CORS(flask_app)
flask_app.config['MONGO_URI'] = config.MONGO_URI
flask_app.config['CELERY_BROKER_URL'] = config.CELERY_BROKER_URL

celery = make_celery(flask_app)
mongo = PyMongo(flask_app)


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


@flask_app.route('/scraped-profiles', methods=['GET'])
def get_scraped_profiles():
    users = mongo.db.scraped_profiles.find().sort('_id', -1)
    response = parse(users)
    # Se usa Response() para que el header content-type sea json
    return Response(response, mimetype='application/json')


@flask_app.route('/scrape-info', methods=['GET'])
def get_scrape_info():
    users = mongo.db.user_engagement
    page_size = int(request.args.get('pageSize', 20))
    page = int(request.args.get('page', 1))
    sort_by = request.args.get('sortBy', None)
    sort_order = request.args.get('order', None)
    user_id = request.args.get('userId')
    timestamp = int(request.args.get('timestamp')) / 1000.0

    parsed_date = datetime.utcfromtimestamp(timestamp)
    offset = (page-1) * page_size

    query = {'profile_id': user_id, 'date': parsed_date}
    total = users.count_documents(query)

    if sort_by and sort_order:
        engagements = users.find(query).sort(sort_by, int(sort_order)).skip(offset).limit(page_size)
    else:
        engagements = users.find(query).skip(offset).limit(page_size)

    xd = {'rows': list(engagements), 'count': total}
    response = parse(xd)

    return Response(response, mimetype='application/json')


@flask_app.route('/scrape-info/liked-posts', methods=['GET'])
def get_user_interacted_posts():
    username = request.args.get('username')
    profile_id = request.args.get('profileId')
    # el datetime de python esta en segundos y el de mongo en ms, por eso la division
    timestamp = int(request.args.get('timestamp')) / 1000.0
    parsed_date = datetime.utcfromtimestamp(timestamp)

    # Buscar todos los posts de ese scrape que el usuario dio like o comento
    pipeline = [
        {
            '$match': {
                'profile_id': profile_id,
                'scraped_date': parsed_date,
                '$or': [
                    {'likers': username},
                    {'commenters': username}
                ]
            }
        },
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
    posts = mongo.db.posts.aggregate(pipeline)
    response = parse(posts)
    return Response(response, mimetype='application/json')


@flask_app.route('/scrape', methods=['POST'])
def start_scraper():
    body = request.json
    username = body.get('username')
    email = body.get('email')

    if not username or not email:
        return Response(parse({'message': 'missing params'}),  status=400, mimetype='application/json')

    scrape_user.delay(username, email)
    return Response(parse({'message': f'started scraping {username}'}), status=202, mimetype='application/json')


# Celery tasks
@celery.task(name='flask_api.scrape_user')
def scrape_user(username, email):
    return scraper.scrape_user(username, email)


if __name__ == '__main__':
    flask_app.run(debug=True)
