# instagram-bot-api
Script para scrapear instagram expuesto con API de flask

# Instalación (local)
Este proyecto depende de librerías como `PyMongo`, `instagram-scraper` (link del repo: https://github.com/realsirjoe/instagram-scraper) y `celery`. A su  vez, `celery` para poder ejecutarse requiere que se tenga instalado un message broker para poder realizar tareas asíncronas, en este proyecto se utilizó `RabbitMQ`. Se utiliza un ambiente virtual como es costumbre en los proyectos de Python, ucibado en la carpeta `venv`. 

El proyecto puede ser ejecutado tanto en windows como en linux, sin embaargo, debido a que depende de **celery** y de **RabbitMQ** y estos no tienes un buen soporte de windows, se recomienda el uso de linux.

1. Se debe asegurar que se tenga instalado RabbitMQ en la computadora anfitriona y esté corriendo como servicio de broker
2. Inicializar el ambiente virtual de python e instalar las librerías con PIP a través de la línea de comandos y el archivo `requirements.txt`
3. Debido a que se hizo un cambio en el código fuente de la librería `instagram-scraper` para poder visualizar por consola la cantidad de requests y los errores, una vez instaladas las dependencias se debe reemplazar el archivo **instagram.py**  instalado por PIP por el que se encuentra en la carpeta base de este repositorio. La ubicación del archivo a sustituir es `venv\Lib\site-packages\igramscraper\instagram.py`.

# Para correr el proyecto (localmente)
1. Se utiliza el comando de consola para iniciar el broker de celery que estará a la espera de los requests de la API. Dependiendo de la plataforma este comando es:
  Para linux: `celery worker -A flask_api.celery --loglevel=INFO`
  Para windows: `celery worker -A flask_api.celery --loglevel=INFO --pool=gevent --concurrency=1`
2. Una vez esté corriendo el broker de celery exitosamente, se procede a iniciar la API de flask ejecutando el archivo `flask_api.py` ya sea a través del IDE o por consola.
3. Si se desea correr el front-end se debe abrir su proyecto y correrlo mediante `npm start`

# Información importante
La aplicación consta de 2 partes:
- Un backend hecho en Python con Flask, el cual es el que realiza el scrape de Instagram y escribe a la base de datos en mongoDB.
- Un front-end hecho en React en donde se visualizan los resultados.

## El back-end
Consiste en un script de python que utiliza la librería https://github.com/realsirjoe/instagram-scraper para realizar la extracción de data de perfiles de instagram. En el archivo`scraper.py` se encuentra detallado la implementación del código. Para realizar esta extracción de data de instagram es necesario utilizar un perfil existente, ya que sin estar logeados Instagram no permite ver la información completa, por ello, se utiliza una cuenta fake creada con anterioridad con un correo válido (esta cuenta puede ser baneada, no usar perfiles personales).

Para la extracción de datos se ha venido utilizando una cuenta fake cuyas credenciales son: email `platanitomaduro42@gmail.com`, user `platanitomaduro42` y clave `nosoyunbot`, desde el front-end esto puede ser cambiado, si se indica el correo y clave que se quiere usar el script usará estos parámetros pasados a través de la API para inciar sesión en instagram. Los perfiles privados solo pueden ser analizados si la cuenta de ig a usar sigue al usuario deseado.

En el archivo `flask_api.py` están las cosas relacionadas a la API y a la conexión con celery (la cual se instancia en `flask_celery.py`) y MongoDB.

## El front-end
El front-end se encuentra como un módulo del dashboard de opentech, en el apartado de "scraper instagram", el código fue hecho en ReactJS usando hooks. Este se conecta con la API de flask para comunicarse con el scraper
