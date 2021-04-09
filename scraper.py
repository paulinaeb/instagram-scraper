from igramscraper.instagram import Instagram
from time import sleep
from collections import Counter
import json
from pprint import pprint
from datetime import datetime
import smtplib
from email.message import EmailMessage

EMAIL_ADDRESS = 'platanitomaduro42@gmail.com'
EMAIL_PASSWORD = 'platanito42'

def scrape_test(username, email):
    from flask_api import mongo as flaskmongo
    start_time = datetime.utcnow()
    
    print('tamos en eso rey...')
    insta = Instagram(5, 2, 5) # sleep, min_sleep, max_sleep

    try:
        account = insta.get_account(username)
    except Exception as e:
        print('Error al obtener la cuenta\n', e)
        return 'error ocurred'

    print(f'\n# DE POSTS DE {username}: {account.media_count}\n')

    flaskmongo.db.test.insert_one({
        'id': account.identifier,
        'username': username,
        'post_count': account.media_count,
        'follower_count': account.followed_by_count,
        'following_count': account.follows_count,
        'scraped_date': start_time
    })

    send_email(username, email)
    return f'Se completo el scrape_test para {username}'


def send_email(scraped_user, receiver):
    print(f'SENDING EMAIL TO {receiver}')
    msg = EmailMessage()
    msg['Subject'] = 'Scrape Finalizado!'
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = receiver
    msg.set_content(f'Se ha completado la extraccion de data de {scraped_user}')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


def scrape_user(username, email=''):
    from flask_api import mongo
    db = mongo.db
    start_time = datetime.utcnow()
    user_has_been_scraped = False
    scraped_posts = None

    print('\n------STARTING SCRAPE------\n')

    # Verificar si ya ha sido scrapeado el usuario anteriormente
    cursor = db.scraped_profiles.find({'username': username}).sort('scraped_date', -1).limit(1)
    scraped_profile = next(cursor, None)
    if scraped_profile:
        print('Profile has been scraped before, collecting old data...\n')
        user_has_been_scraped = True
        # Buscar en BD la info de todos los posts de este usuario levantada durante el ultimo scrapeo
        query = {'profile_id': scraped_profile['id'], 'scraped_date': scraped_profile['scraped_date']}
        scraped_posts = db.posts.find(query)

    # Obtener los datos de la cuenta
    try:
        instagram = Instagram(5, 5, 12) # sleep, min_sleep, max_sleep
        instagram.with_credentials('platanitomaduro42', 'platanito42')
        instagram.login()
        account = instagram.get_account(username)
    except Exception as e:
        print('Error al obtener la cuenta\n', e)
        return

    # account.media_count = 5
    print(f'# DE POSTS DE {username}: {account.media_count}\n')

    # Obtener la lista actual de posts de la cuenta
    try:
        all_posts = instagram.get_medias_by_user_id(account.identifier, account.media_count)
    except Exception as e:
        print('Error obteniendo la lista de posts de la cuenta\n', e)
        return

    result = []
    total_likes_count = 0
    total_comments_count = 0
    total_engagement_sum = 0
    # Obtener la lista de likes y comments por cada post
    for i, post in enumerate(all_posts, start=1):
        # Ver si este post ya ha sido scrapeado y en caso de haberlo sido, comparar likes y comments
        if user_has_been_scraped:
            # Generador que contiene el post evaluado si es que existe en el ultimo scrapeo de la BD
            found_post = next((p for p in scraped_posts if p['short_code'] == post.short_code), None)
            if found_post and found_post['likes_count'] == post.likes_count:
                print(F'--SKIPPING POST #{i} ({post.short_code}) AS IT HAS NOT CHANGED--\n')
                # Copiar en la BD el registro del post con otra fecha como si se hubiera vuelto a scrapear
                copied_post = {**found_post, 'scraped_date': start_time}
                copied_post.pop('_id')
                total_likes_count += post.likes_count
                total_comments_count += post.comments_count
                total_engagement_sum += found_post['engagement']
                db.posts.insert_one(copied_post)
                result.append(found_post)
                continue

        post_info = {}
        post_info['post_id'] = post.identifier
        post_info['short_code'] = post.short_code
        post_info['profile_id'] = account.identifier
        post_info['likes_count'] = post.likes_count
        post_info['comments_count'] = post.comments_count
        post_info['scraped_date'] = start_time
        post_info['engagement'] = (post.likes_count + post.comments_count) / account.followed_by_count * 100

        total_likes_count += post.likes_count
        total_comments_count += post.comments_count
        total_engagement_sum += post_info['engagement']

        try:
            # Get likers
            print(f'--GETTING LIKERS OF POST #{i}: {post.short_code} ({post.likes_count} LIKES)--')
            likers = instagram.get_media_likes_by_code(post.short_code, post.likes_count)
            print(f"--DONE. GOT {len(likers['accounts'])} LIKERS--\n")
            post_info['likers'] = [liker.username for liker in likers['accounts']]

            # Get commenters
            print(f'--GETTING COMMENTERS OF POST #{i}: {post.short_code} ({post.comments_count} COMMENTS)--')
            comments_result = instagram.get_media_comments_by_code(post.short_code, post.comments_count)
            all_commenters = [c.owner.username for c in comments_result['comments']]
            unique_commenters = list(set(all_commenters))
            print(f"--DONE. GOT {len(all_commenters)} COMMENTERS--\n")
            print('------------------------------------------------------')
            post_info['commenters'] = unique_commenters

            # post_info['commenters'] = []
            result.append(post_info)

            # Guardar o actualizar el post en la BD
            # mongo.update_one('posts', post.identifier, post_info)
            db.posts.insert_one(post_info)
        except Exception as e:
            print('Ocurrio una excepcion durante el scrape:', e)

    # Guardar perfil scrapeado en la BD
    db.scraped_profiles.insert_one({
        'id': account.identifier,
        'username': username,
        'post_count': account.media_count,
        'follower_count': account.followed_by_count,
        'following_count': account.follows_count,
        'total_likes_count': total_likes_count,
        'total_comments_count': total_comments_count,
        'total_engagement': total_engagement_sum / account.media_count,
        'scraped_date': start_time,
    })

    # Calcular las estadisticas de engagement
    if len(result) > 0:
        calculate_user_engagement(result, account, user_has_been_scraped, start_time, email)


def calculate_user_engagement(posts, account, previously_scraped, start_time, email):
    from flask_api import mongo
    db = mongo.db
    # Se reciben todos los posts del perfil scrapeado, ya sea porque se haya obtenido por la API o de la BD
    likers = []
    commenters = []
    for post in posts:
        likers += post.get('likers', [])
        commenters += post.get('commenters', [])

    # Contar cuantas veces aparece cada usuario
    likes_counter = Counter(likers)
    comments_counter = Counter(commenters)

    print('INSERTING USER ENGAGEMENT RELATIONSHIPS TO DB...')
    stats = [{
        'username': user,
        'profile_id': account.identifier,
        'profile_username': account.username,
        'like_count': likes,
        'like_percent': likes / account.media_count * 100,
        'comment_count': comments_counter.get(user, 0),
        'comment_percent': comments_counter.get(user, 0) / account.media_count * 100,
        'date': start_time
    } for user, likes in likes_counter.most_common()]

    db.user_engagement.insert_many(stats)
    send_email(account.username, email)


def test(user):
    insta = Instagram(3, 2, 5) # sleep, min_sleep, max_sleep

    try:
        account = insta.get_account(user)
    except Exception as e:
        print('Error al obtener la cuenta\n', e)

    print(account)


if __name__ == '__main__':
    print('ejecutando scraper como __main__')
    instagram = Instagram(5, 2, 5) # sleep, min_sleep, max_sleep
    # instagram.with_credentials('platanitomaduro42', 'platanito42')
    # instagram.login()
    
    # comments_result = instagram.get_media_comments_by_code('CM5oND8F4f8', 10)
    # for c in comments_result['comments']:
    #     print(c.text, '-', c.owner.username)
    # all_commenters = [c.owner.username for c in comments_result['comments']]
    # unique_commenters = list(set(all_commenters))

    # test('somosopentech')
    # login()
    # get_account_likers('worl.d.manga')

    # send_email('gg')
    # now = datetime.now()
    # current_time = now.strftime("%H:%M:%S")
    # print("End Time =", current_time)
    # calculate_user_engagement('somosopentech')

# def get_account_likers_old(username):
#     start_time = datetime.utcnow()
#     user_has_been_scraped = False
#     scraped_posts = None

#     # Verificar si ya ha sido scrapeado el usuario anteriormente
#     cursor = mongo.find_many('scraped_profiles', 'username', username, sorted=True, sorted_by='scraped_date', limit=1)
#     scraped_profile = next(cursor, None)
#     if scraped_profile:
#         print('Profile has been scraped before, collecting old data...\n')
#         user_has_been_scraped = True
#         # Buscar en BD la info de todos los posts de este usuario levantada durante el ultimo scrapeo
#         query = {'profile_id': scraped_profile['id'], 'scraped_date': scraped_profile['scraped_date']}
#         scraped_posts = mongo.find_many('posts', query=query)

#     # Obtener los datos de la cuenta
#     try:
#         instagram = Instagram(5, 2, 5) # sleep, min_sleep, max_sleep
#         instagram.with_credentials('platanitomaduro42', 'platanito42')
#         instagram.login()
#         account = instagram.get_account(username)
#     except Exception as e:
#         print('Error al obtener la cuenta\n', e)
#         return

#     account.media_count = 5
#     print(f'# DE POSTS DE {username}: {account.media_count}\n')

#     # Guardar perfil scrapeado en la BD
#     mongo.insert_one('scraped_profiles', {
#         'id': account.identifier,
#         'username': username,
#         'post_count': account.media_count,
#         'follower_count': account.followed_by_count,
#         'following_count': account.follows_count,
#         'scraped_date': start_time
#     })

#     # Obtener la lista actual de posts de la cuenta
#     try:
#         all_posts = instagram.get_medias_by_user_id(account.identifier, account.media_count)
#     except Exception as e:
#         print('Error obteniendo la lista de posts de la cuenta\n', e)
#         return

#     result = []
    
#     # Obtener la lista de likes y comments por cada post
#     for i, post in enumerate(all_posts, start=1):
#         # Ver si este post ya ha sido scrapeado y en caso de haberlo sido, comparar likes y comments
#         if user_has_been_scraped:
#             # Generador que contiene el post evaluado si es que existe en el ultimo scrapeo de la BD
#             found_post = next((p for p in scraped_posts if p['short_code'] == post.short_code), None)
#             if found_post and found_post['likes_count'] == post.likes_count:
#                 print(F'--SKIPPING POST #{i} ({post.short_code}) AS IT HAS NOT CHANGED--\n')
#                 # Copiar en la BD el registro del post con otra fecha como si se hubiera vuelto a scrapear
#                 copied_post = {**found_post, 'scraped_date': start_time}
#                 copied_post.pop('_id')
#                 mongo.insert_one('posts', copied_post)
#                 result.append(found_post)
#                 continue

#         post_info = {}
#         post_info['post_id'] = post.identifier
#         post_info['short_code'] = post.short_code
#         post_info['profile_id'] = account.identifier
#         post_info['likes_count'] = post.likes_count
#         post_info['comments_count'] = post.comments_count
#         post_info['scraped_date'] = start_time
        
#         try:
#             # Get likers
#             print(f'--GETTING LIKERS OF POST #{i}: {post.short_code} ({post.likes_count} LIKES)--')
#             likers = instagram.get_media_likes_by_code(post.short_code, post.likes_count)
#             print(f"--DONE. GOT {len(likers['accounts'])} LIKERS--\n")
#             post_info['likers'] = [liker.username for liker in likers['accounts']]

#             # Get commenters
#             # print(f'--GETTING COMMENTS OF POST {post.short_code} ({post.comments_count} comments)--')
#             # comments = instagram.get_media_comments_by_code(post.short_code, post.comments_count)
#             # print(f"--DONE. # OF COMMENTS OF {post.short_code}: {len(comments['accounts'])}--\n")
#             # post_info['commenters'] = commenters_users

#             post_info['commenters'] = []
#             result.append(post_info)

#             # Guardar o actualizar el post en la BD
#             # mongo.update_one('posts', post.identifier, post_info)
#             mongo.insert_one('posts', post_info)
#         except Exception as e:
#             print('Ocurrio una excepcion:\n', e)

#     # Calcular las estadisticas de engagement
#     if len(result) > 0:
#         calculate_user_engagement(result, account, user_has_been_scraped, start_time)
