FROM continuumio/miniconda3:latest

RUN pip install mlflow[extras] pymysql

ADD . /app
WORKDIR /app