FROM python:3.9-slim-buster

SHELL ["/bin/bash", "-c"]

WORKDIR /usr/src/app

RUN apt-get update

RUN pip install supervisor

# RUN python3 -m venv venv
# RUN source venv/bin/activate

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

# RUN chmod a+x start.sh

COPY instagram.py /usr/local/lib/python3.9/site-packages/igramscraper

EXPOSE 5000

CMD ["supervisord","-c","./service_script.conf"]