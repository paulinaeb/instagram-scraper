from hashlib import new
from igramscraper.instagram import Instagram
from time import sleep
from collections import Counter
import json
from pprint import pprint
from datetime import datetime
import smtplib
from email.message import EmailMessage
from os import error  
import requests
from bs4 import BeautifulSoup
import random
import concurrent.futures


EMAIL_ADDRESS = 'platanitomaduro42@gmail.com'
EMAIL_PASSWORD = 'platanito42' 

#---funcion para obtener cuentas desde archivo .json
def getAccounts():
    accounts = []
    with open('accounts.json') as file:
        data = json.load(file)
    for account in data['accounts']: 
        accounts.append(account) 
    return accounts

#--funcion para obtener random cuenta
def newAccount(username, accounts):
    flag=0 
    while flag==0:
        newaccount = random.choice(accounts) 
        if newaccount['username']!=username:
            username=newaccount['username']
            flag=1  
    return newaccount   

#---------funciones para obtener proxies para su rotacion durante el scrape----------#
#scrape para obtener proxies gratis actualizados
def getProxies():
    r = requests.get('https://free-proxy-list.net/')
    soup = BeautifulSoup(r.content, 'html.parser')
    table = soup.find('tbody')
    proxies = []
    for row in table:
        if row.find_all('td')[4].text =='elite proxy':
            proxy = ':'.join([row.find_all('td')[0].text, row.find_all('td')[1].text])
            proxies.append(proxy)
        else:
            pass
    return proxies


def extract(proxy): 
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0'}
    try: 
        r = requests.get('https://httpbin.org/ip', headers=headers, proxies={'http' : proxy,'https': proxy}, timeout=1)
        print(r.json(), r.status_code)
    except:
        pass
    return proxy

#inicializa los proxies y escoge uno al azar
def newproxy(proxylist):
    proxy = random.choice(proxylist) 
    random_proxy= { 'http': 'http://'+proxy, 
                    } 
    return random_proxy
 
#------funciones para scraping-----
def send_email(scraped_user, receiver, flag):
    print(f'SENDING EMAIL TO {receiver}')
    msg = EmailMessage()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = receiver
    if flag:
        msg['Subject'] = 'Scrape Finalizado!'
        msg.set_content(f'Se ha completado la extracción de data de {scraped_user}')
    else:
        msg['Subject'] = 'Status de su solicitud de Scrape'
        msg.set_content(f'Su solicitud de extracción de data del usuario {scraped_user} contiene datos inválidos. Verifique e intente de nuevo.')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

#instagram scraper principal function
def scrape_user(username, email, scraping_user, scraping_pass):
    from flask_api import mongo
    db = mongo.db
    start_time = datetime.utcnow()
    user_has_been_scraped = False
    scraped_posts = None
    error_count = 0 
    proxylist = getProxies()
    #print(len(proxylist))
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(extract, proxylist) 
    instagram = Instagram()
    instagram.set_proxies(newproxy(proxylist))
    print('\n------LOGGING IN------\n') 
    #Hacer login
    try: 
        instagram.with_credentials(scraping_user, scraping_pass)
        instagram.login()
    except Exception as e: 
        send_email(username, email, False)
        return 'Error al hacer login: credenciales no validas'

    print('\n------GETTING ACCOUNT------\n') 
    # Obtener los datos de la cuenta
    try: 
        instagram.set_proxies(newproxy(proxylist))
        account = instagram.get_account(username)
    except Exception as e: 
        send_email(username, email, False)
        return 'Error al obtener la cuenta del usuario ingresado'

    print('\n------STARTING SCRAPE------\n') 

    # Verificar si ya ha sido scrapeado el usuario anteriormente
    cursor = db.scraped_profiles.find({'username': username}).sort('scraped_date', -1).limit(1)
    scraped_profile = next(cursor, None)
    if scraped_profile:
        print('Profile has been scraped before, collecting old data...\n')
        user_has_been_scraped = True
        # Buscar en BD la info de todos los posts de este usuario levantada durante el ultimo scrape
        query = {'profile_id': scraped_profile['id'], 'scraped_date': scraped_profile['scraped_date']}
        scraped_posts = list(db.posts.find(query))
        print(f'Profile had {db.posts.count_documents(query)} scraped posts last time it was analyzed')

    print(f'# DE POSTS DE {username}: {account.media_count}\n')

    # Obtener la lista actual de posts de la cuenta (3 intentos)
    for i in range(3):
        try:
            instagram.set_proxies(newproxy(proxylist))
            all_posts = instagram.get_medias_by_user_id(account.identifier, account.media_count)
        except Exception as e:
            print('Error obteniendo la lista de posts de la cuenta:\n', e)
            if i < 3:
                print('Intentando obtener posts nuevamente...')
            else:
                print('3 intentos fallidos al obtener posts, finalizando programa.')
                return
        else:
            break
    instagram.set_proxies(newproxy(proxylist))
    # Insertar usuario en la base de datos para marcar como iniciado
    inserted_id = db.scraped_profiles.insert_one({
        'id': account.identifier,
        'username': username,
        'post_count': account.media_count,
        'follower_count': account.followed_by_count,
        'following_count': account.follows_count,
        'total_likes_count': -1,
        'total_comments_count': -1,
        'total_engagement': -1,
        'scraped_date': start_time,
        'completed': False
    }).inserted_id

    result = []
    total_likes_count = 0
    total_comments_count = 0
    total_engagement_sum = 0
    # Obtener la lista de likes y comments por cada post
    for i, post in enumerate(all_posts, start=1):
        # Ver si este post ya ha sido scrapeado y en caso de haberlo sido, comparar likes y comments
        if user_has_been_scraped:
            # Generador que contiene el post evaluado si es que existe en el ultimo scrape de la BD
            instagram.set_proxies(newproxy(proxylist))
            found_post = next((p for p in scraped_posts if p['short_code'] == post.short_code), None)
            instagram.set_proxies(newproxy(proxylist))
            if found_post and found_post['likes_count'] == post.likes_count:
                print(F'--SKIPPING POST #{i} ({post.short_code}) AS IT HAS NOT CHANGED--\n')
                # Copiar en la BD el registro del post con otra fecha como si se hubiese vuelto a scrapear
                copied_post = {**found_post, 'scraped_date': start_time}
                copied_post.pop('_id')
                total_likes_count += post.likes_count
                total_comments_count += post.comments_count
                total_engagement_sum += found_post['engagement']
                db.posts.insert_one(copied_post)
                result.append(found_post)
                continue

        post_info = {}
        instagram.set_proxies(newproxy(proxylist))
        post_info['post_id'] = post.identifier
        post_info['short_code'] = post.short_code
        post_info['profile_id'] = account.identifier
        post_info['likes_count'] = post.likes_count
        post_info['comments_count'] = post.comments_count
        post_info['created_time'] = post.created_time
        post_info['scraped_date'] = start_time
        post_info['engagement'] = (post.likes_count + post.comments_count) / account.followed_by_count * 100
        instagram.set_proxies(newproxy(proxylist))
        total_likes_count += post.likes_count
        total_comments_count += post.comments_count
        total_engagement_sum += post_info['engagement']

        try:
            # Get likers
            instagram.set_proxies(newproxy(proxylist))
            print(f'--GETTING LIKERS OF POST #{i}: {post.short_code} ({post.likes_count} LIKES)--')
            likers = instagram.get_media_likes_by_code(post.short_code, post.likes_count)
            print(f"--DONE. GOT {len(likers['accounts'])} LIKERS--\n")
            post_info['likers'] = [liker.username for liker in likers['accounts']]

            # Get commenters
            instagram.set_proxies(newproxy(proxylist))
            if post.comments_count == 0:
                print('--Post has no comments--')
                post_info['commenters'] = []
            else:
                instagram.set_proxies(newproxy(proxylist))
                print(f'--GETTING COMMENTERS OF POST #{i}: {post.short_code} ({post.comments_count} COMMENTS)--')
                comments_result = instagram.get_media_comments_by_code(post.short_code, post.comments_count)
                all_commenters = [c.owner.username for c in comments_result['comments']]
                unique_commenters = list(set(all_commenters))
                print(f"--DONE. GOT {len(all_commenters)} COMMENTERS--\n")
                post_info['commenters'] = unique_commenters

            result.append(post_info)
            # Guardar el post en la BD 
            db.posts.insert_one(post_info)
        except Exception as e:
            print('Ocurrio una excepcion durante el scrape:', e)
            error_count += 1

    # Guardar perfil scrapeado en la BD
    instagram.set_proxies(newproxy(proxylist))
    db.scraped_profiles.update_one({'_id': inserted_id}, {'$set': {
        'total_likes_count': total_likes_count,
        'total_comments_count': total_comments_count,
        'total_engagement': total_engagement_sum / account.media_count,
        'completed': True
    }})

    print('--FINISHED GETTING POSTS--')
    print(f'ERROR COUNT: {error_count}')

    # Calcular las estadisticas de engagement
    if len(result) > 0:
        calculate_user_engagement(result, account, start_time, email, instagram, proxylist)
    send_email(account.username, email, True)

def calculate_user_engagement(posts, account, start_time, instagram, proxylist):
    from flask_api import mongo
    db = mongo.db
    # Se reciben todos los posts del perfil scrapeado, ya sea porque se haya obtenido por la API o de la BD
    likers = []
    commenters = []
    for post in posts:
        instagram.set_proxies(newproxy(proxylist))
        likers += post.get('likers', [])
        commenters += post.get('commenters', [])

    # Contar cuantas veces aparece cada usuario
    instagram.set_proxies(newproxy(proxylist))
    likes_counter = Counter(likers)
    comments_counter = Counter(commenters)

    print('INSERTING USER ENGAGEMENT RELATIONSHIPS TO DB...')
    instagram.set_proxies(newproxy(proxylist))
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
    instagram.set_proxies(newproxy(proxylist))
    db.user_engagement.insert_many(stats)

#-----funciones de micro-influencer finder-----
def interacciones(followers, instagram, account, proxylist, scraping_user, instaAccounts):
    likes= comments = engagement= 0
    last_post = []
    for i in range(4):
        try:
            last_post = instagram.get_medias_by_user_id(account.identifier, 1)
        except Exception as e:
            print('error: '+str(e))
            if i < 2:
                instagram.set_proxies(newproxy(proxylist))
                print('Intentando obtener posts nuevamente, rotando proxies...') 
            if i < 3:
                newScrapingAccount=newAccount(scraping_user, instaAccounts)
                instagram.set_proxies(newproxy(proxylist))
                instagram.with_credentials(newScrapingAccount['username'], newScrapingAccount['password'])
                instagram.login()
                print('Intentando obtener cuenta nuevamente, rotando cuentas...')
            else:
                print('4 intentos fallidos al obtener posts')
                return[likes,comments,engagement] 
        else:
            break
    if len(last_post)>0 and followers>0:
        instagram.set_proxies(newproxy(proxylist))
        likes= last_post[0].likes_count
        instagram.set_proxies(newproxy(proxylist))
        comments = last_post[0].comments_count   
        engagement = ((likes + comments)/followers)*100 
    return[likes,comments,engagement]    


def find_user(userSearch):
    from flask_api import mongo
    db = mongo.db
    start_time = datetime.utcnow()
    proxylist = getProxies()
    #print(len(proxylist))
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(extract, proxylist)
    instaAccounts = getAccounts()
    insta = Instagram()
    insta.set_proxies(newproxy(proxylist))
    scraping_user = 'prueba.ejemplo20'
    scraping_pass = 'nosoyunbot'
    print('\n------iniciando buscador: inicio de sesion------\n') 
    #Hacer login
    try: 
        insta.with_credentials(scraping_user, scraping_pass)
        insta.login()
    except Exception as e:  
        send_email(userSearch, 'pdespejo18@gmail.com', False)
        return 'Error al hacer login: credenciales no validas'+str(e)

    print('\n ---getting account--- \n')
    try:
        insta.set_proxies(newproxy(proxylist))
        account = insta.get_account(userSearch)
    except Exception as e:
        send_email(userSearch, 'pdespejo18@gmail.com', False)
        return 'Error al obtener la cuenta\n'+str(e) 

    insta.set_proxies(newproxy(proxylist))
    account_followers = account.followed_by_count 
    account_following = account.follows_count 
    id=account.identifier
    #guardar en base de datos
    inserted_id = db.searched_profile.insert_one({
        'id': id,
        'username': userSearch, 
        'follower_count': account_followers,
        'following_count': account_following, 
        'total_engagement': -1,
        'total_likes_count': -1,
        'total_comments_count': -1,
        'scraped_date': start_time,
        'completed': False
    }).inserted_id 
    print('---getting followers---')
    followers = []
    influencers = [] 
    followers = insta.get_followers(id, account_followers, account_followers)
    print('---finding influencers---')
    #encuentra y guarda en la base de datos los seguidores con cuentas publicas
    for follower in followers['accounts']: 
        insta.set_proxies(newproxy(proxylist))
        if follower.is_private is False:  
            insta.set_proxies(newproxy(proxylist))
            for i in range(4):
                try:
                    user = insta.get_account(follower.username) 
                except Exception as e:
                    print('error: '+str(e))
                    if i < 2:
                        insta.set_proxies(newproxy(proxylist))
                        print('Intentando obtener cuenta nuevamente, rotando proxies...') 
                    if i < 3:
                        newScrapingAccount=newAccount(scraping_user, instaAccounts)
                        insta.set_proxies(newproxy(proxylist))
                        insta.with_credentials(newScrapingAccount['username'], newScrapingAccount['password'])
                        insta.login()
                        print('Intentando obtener cuenta nuevamente, rotando cuentas...') 
                    else:
                        print('4 intentos fallidos al obtener posts')
                        send_email(userSearch, 'pdespejo18@gmail.com', False)
                        return 'error getting account'
                else:
                    break
            insta.set_proxies(newproxy(proxylist))
            username=user.username
            insta.set_proxies(newproxy(proxylist))   
            follower_count= user.followed_by_count 
            user_info = {}
            user_info['username']= username
            user_info['follower_count']= follower_count
            user_info['scraped_date']= start_time
            user_info['total_engagement']= -1 
            db.followers.insert_one(user_info)
            influencers.append(user)
    # busca en la base de datos los influencers para calcular su engagement
    col=db['followers'] 
    for user in influencers:
        insta.set_proxies(newproxy(proxylist))
        username=user.username
        for x in col.find({'scraped_date': start_time, 'username': username}): 
            insta.set_proxies(newproxy(proxylist))
            interacciones_follower = interacciones(x['follower_count'], insta, user, proxylist, scraping_user, instaAccounts)
            db.followers.update_one({
                'scraped_date': start_time, 
                'username': username}, {'$set': {'total_engagement': interacciones_follower[2]}})

    #guardar interacciones del usuario buscado 
    print('---finalizando busqueda---')
    insta.set_proxies(newproxy(proxylist))
    interacciones_list= interacciones(account_followers, insta, account, proxylist, scraping_user, instaAccounts) 
    db.searched_profile.update_one({'_id': inserted_id}, {'$set': { 
        'total_likes_count': interacciones_list[0],
        'total_comments_count':interacciones_list[1],
        'total_engagement': interacciones_list[2],
        'completed': True
    }})
    send_email(userSearch, 'pdespejo18@gmail.com', True)


if __name__ == '__main__':
    print('ejecutando scraper como __main__')
