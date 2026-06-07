import os
import requests
import json
from dotenv import load_dotenv
from datetime import date, timedelta
import psycopg
from psycopg.types.json import Jsonb
load_dotenv()

# Definir parametros da conexão com o banco de dados (Postgress)
conn = psycopg.connect(
    host = os.getenv("DB_HOST"),
    dbname = os.getenv("DB_NAME"),
    user = os.getenv("DB_USER"),
    password = os.getenv("DB_PASSWORD"),
    port = os.getenv("DB_PORT")
)



# Conexão com o Banco de dados & checagem/criação das tabelas)
def db_init(conn):


 cur = conn.cursor()


    cur.execute("""CREATE TABLE IF NOT EXISTS dim_accounts (
                    account_id BIGINT PRIMARY KEY,
                    account_name VARCHAR NOT NULL,
                    account_platform VARCHAR NOT NULL, CHECK (account_platform IN ('meta_ads', 'google_ads'),
                    last_sync_at TIMESTAMP NOT NULL),
                    last_data_date DATE);

                    CREATE TABLE IF NOT EXISTS dim_campaign (
                    campaign_id BIGINT PRIMARY KEY,
                    campaign_name VARCHAR,
                    campaign_status VARCHAR,
                    objective VARCHAR);

                    CREATE TABLE IF NOT EXISTS dim_adset (
                    adset_id BIGINT PRIMARY KEY,
                    adset_name VARCHAR);

                    CREATE TABLE IF NOT EXISTS dim_ad (
                    ad_id BIGINT PRIMARY KEY,
                    ad_name VARCHAR);

                    CREATE TABLE IF NOT EXISTS dim_data (
                    date DATE PRIMARY KEY);

                    CREATE TABLE IF NOT EXISTS fact_daily_data (
                    fact_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    date DATE REFERENCES dim_data(date),
                    account_id BIGINT REFERENCES dim_accounts(account_id),
                    campaign_id BIGINT REFERENCES dim_campaign(campaign_id),
                    adset_id BIGINT REFERENCES dim_adset(adset_id),
                    ad_id BIGINT REFERENCES dim_ad(ad_id),

                    spend NUMERIC(18,2),
                    impressions BIGINT,
                    reach BIGINT,
                    clicks BIGINT,
                    link_clicks BIGINT,
                    outbound_link_clicks BIGINT,
                    ctr NUMERIC(10,4),
                    cpc NUMERIC(10,4),
                    cpm NUMERIC(10,4),
                    frequency NUMERIC(10,2),

                    actions JSONB,
                    action_values JSONB,
                    cost_per_action_type JSONB,
                    purchase_roas JSONB,

                    UNIQUE (date, ad_id))
                    """
    )
 

    conn.commit()


## "E" Extract, uma função que recebe um account_id do meta
def extract_meta_ads(account_id):
    access_token = os.getenv("META_USER_TOKEN_JOHN")
    api_version = os.getenv("META_API_VERSION")
    hoje = date.today()

    url = f"https://graph.facebook.com/{api_version}/act_{account_id}/insights"
    params = {
    "fields": "account_name, account_id, campaign_name, campaign_id, adset_name, adset_id, ad_name, ad_id, spend, impressions, reach, cpm, clicks, inline_link_clicks, outbound_clicks, ctr, cpc, frequency, actions, action_values, cost_per_action_type, purchase_roas",
    "access_token": access_token,
    "time_range": json.dumps({"since":"2026-01-06","until":hoje.isoformat()}),
    "level": "ad",
    "limit": 500,
    "time_increment": "1"
    }


    response = requests.get(url, params = (params))

    response.raise_for_status()

    request_data = (response.json())
    all_pages_data = request_data["data"]
    if "next" in request_data["paging"]:
     has_next_page = True
    else: has_next_page = False

    #Paginação // Loop para buscar todas as páginas
    while has_next_page and request_data["data"] != []:
     url = request_data["paging"]["next"]
     response = requests.get(url)
     request_data = (response.json())
     has_next_page = "next" in request_data["paging"]
     all_pages_data = all_pages_data + request_data["data"]

    return all_pages_data


## "L" Load,  faz upsert de cada linha nas dimensões e na fact
def load(dados, conn):
    ontem = date.today() - timedelta(days=1)
    cur = conn.cursor()
    for row in dados:
        cur.execute(
            """
            INSERT INTO dim_accounts (account_id, account_name, account_platform, last_sync_at, last_data_date)
            VALUES (%s, %s, %s, NOW(), %s)
            ON CONFLICT (account_id)
            DO UPDATE SET
                account_name = EXCLUDED.account_name,
                last_sync_at = EXCLUDED.last_sync_at
            """,
            (row["account_id"], row["account_name"], "meta_ads", ontem),
        )

        cur.execute(
            """
            INSERT INTO dim_campaign (campaign_id, campaign_name, campaign_status, objective)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (campaign_id)
            DO UPDATE SET
                campaign_name = EXCLUDED.campaign_name,
                campaign_status = EXCLUDED.campaign_status,
                objective = EXCLUDED.objective
            """,
            (row["campaign_id"], row["campaign_name"], row.get("campaign_status"), row.get("objective")),
        )

        cur.execute(
            """
            INSERT INTO dim_adset (adset_id, adset_name)
            VALUES (%s, %s)
            ON CONFLICT (adset_id)
            DO UPDATE SET adset_name = EXCLUDED.adset_name
            """,
            (row["adset_id"], row["adset_name"]),
        )

        cur.execute(
            """
            INSERT INTO dim_ad (ad_id, ad_name)
            VALUES (%s, %s)
            ON CONFLICT (ad_id)
            DO UPDATE SET ad_name = EXCLUDED.ad_name
            """,
            (row["ad_id"], row["ad_name"]),
        )

        cur.execute(
            """
            INSERT INTO dim_data (date)
            VALUES (%s)
            ON CONFLICT (date) DO NOTHING
            """,
            (row["date_start"],),
        )

        cur.execute(
            """
            INSERT INTO fact_daily_data (
                date, account_id, campaign_id, adset_id, ad_id,
                spend, impressions, reach, clicks, link_clicks, outbound_link_clicks,
                ctr, cpc, cpm, frequency,
                actions, action_values, cost_per_action_type, purchase_roas)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)

                ON CONFLICT (date, ad_id)
                DO UPDATE SET
                spend = EXCLUDED.spend,
                impressions = EXCLUDED.impressions,
                reach = EXCLUDED.reach,
                clicks = EXCLUDED.clicks,
                link_clicks = EXCLUDED.link_clicks,
                outbound_link_clicks = EXCLUDED.outbound_link_clicks,
                ctr = EXCLUDED.ctr,
                cpc = EXCLUDED.cpc,
                cpm = EXCLUDED.cpm,
                frequency = EXCLUDED.frequency,
                actions = EXCLUDED.actions,
                action_values = EXCLUDED.action_values,
                cost_per_action_type = EXCLUDED.cost_per_action_type,
                purchase_roas = EXCLUDED.purchase_roas
            """,
            (
                row["date_start"], row["account_id"], row["campaign_id"], row["adset_id"], row["ad_id"],
                row.get("spend"), row.get("impressions"), row.get("reach"), row.get("clicks"),
                row.get("inline_link_clicks"), row.get("outbound_clicks"),
                row.get("ctr"), row.get("cpc"), row.get("cpm"), row.get("frequency"),
                Jsonb(row.get("actions")), Jsonb(row.get("action_values")),
                Jsonb(row.get("cost_per_action_type")), Jsonb(row.get("purchase_roas")),
            ),
        )

    conn.commit()


#meta_pipeline()
#db_init(conn)
#extract_meta_ads()
#load(dados, conn)
dados = (extract_meta_ads(2894362954056557))
print (len(dados))
print (json.dumps(dados[0], indent=2, ensure_ascii=False))
