import os
import requests
import json
from dotenv import load_dotenv
from datetime import date
import psycopg
load_dotenv()

## Inicialização da conexão com o Banco de dados 
# Postgress e checagem/criação das tabelas)



def db_init():
    conn = psycopg.connect(
        host = os.getenv("DB_HOST"),
        dbname = os.getenv("DB_NAME"),
        user = os.getenv("DB_USER"),
        password = os.getenv("DB_PASSWORD"),
        port = os.getenv("DB_PORT")
        )
    
    cur = conn.cursor()

    # Para o DB, usamos o modelo Star Schema, uma Tabela Central
    # Esta deve conter os dados na menor granularidade possível que buscamos analisar
    # Todas as demais para cima construimos a partir de agregações
    # Para nosso caso de uso vamos usar: 1 linha = performance de 1 criativo/dia
    
    cur.execute("""CREATE TABLE IF NOT EXISTS dim_campaign (
                    campaign_id BIGINT PRIMARY KEY,
                    campaign_name VARCHAR,
                    objective VARCHAR)
                    ;
                    CREATE TABLE IF NOT EXISTS dim_adset (
                    adset_id BIGINT PRIMARY KEY,
                    adset_name VARCHAR);
                
                    CREATE TABLE IF NOT EXISTS dim_ad (
                    ad_id BIGINT PRIMARY KEY,
                    ad_name VARCHAR);

                    CREATE TABLE IF NOT EXISTS dim_data (
                    date DATE PRIMARY KEY);
                    
                    CREATE TABLE IF NOT EXISTS fact_daily_data (
                    fact_id INT PRIMARY KEY,
                    date DATE REFERENCES dim_data(date),
                    campaign_id BIGINT REFERENCES dim_campaign(campaign_id),
                    adset_id BIGINT REFERENCES dim_adset(adset_id),
                    ad_id BIGINT REFERENCES dim_ad(ad_id));"""
                )
    
    conn.commit()

    cur.execute("""SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' """
                )
    
    
    print(cur.fetchall())
    

db_init()

## "E" Extract, uma função para extrair os dados do meta
def fetch_insights(account_id):
    access_token = os.getenv("META_USER_TOKEN_JOHN")
    api_version = os.getenv("META_API_VERSION")
    hoje = date.today()

    url = f"https://graph.facebook.com/{api_version}/act_{account_id}/insights"
    params = {
    "fields": "campaign_name, spend",
    "access_token": access_token,
    "time_range": json.dump({"since":"2026-01-01","until":hoje.isoformat()}),
    "level": "campaign",
    "time_increment": "1"
    }
    response = requests.get(url, params = (params))
    response.raise_for_status()

    request_data = (response.json())
    all_pages_data = request_data["data"]
    if "next" in request_data["paging"]:
        has_next_page = True
    else: has_next_page = False

    while has_next_page:
        url = request_data["paging"]["next"]
        response = requests.get(url)
        request_data = (response.json())
        has_next_page = "next" in request_data["paging"]
        all_pages_data = all_pages_data + request_data["data"]

    for nome, valor in response.headers.items():
        print(f"{nome}: {valor}")

    return json.dumps(all_pages_data, indent=2, ensure_ascii=False)
    

## print(fetch_insights(2894362954056557))

##def load()
    
