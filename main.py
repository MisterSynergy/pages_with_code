from json import JSONDecodeError
from os.path import expanduser
from time import strftime

import pandas as pd
import pywikibot as pwb
import requests
from mysql.connector import MySQLConnection, FieldType


WIKIDATA_API_ENDPOINT = 'https://www.wikidata.org/w/api.php'
USER_AGENT = f'{requests.utils.default_headers()["User-Agent"]} (Wikidata bot' \
              ' by User:MisterSynergy; mailto:mister.synergy@yahoo.com)'
DB_PARAMS = {
    'host' : 'wikidatawiki.analytics.db.svc.wikimedia.cloud',
    'database' : 'wikidatawiki_p',
    'option_files' : f'{expanduser("~")}/replica.my.cnf'
}


class Replica:
    def __init__(self):
        self.replica = MySQLConnection(**DB_PARAMS)
        self.cursor = self.replica.cursor()

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
        self.replica.close()


def query_mediawiki(query:str) -> tuple[list[tuple[int, str, str, int, int, str]], \
        tuple[str, str, str, str, str, str], list[str]]:
    with Replica() as db_cursor:
        db_cursor.execute(query)
        result = db_cursor.fetchall()

        column_names = db_cursor.column_names
        columns_to_convert = []

        for desc in db_cursor.description:
             # some are clearly missing here in this list
            if FieldType.get_info(desc[1]) in [ 'VAR_STRING', 'STRING' ]:
                columns_to_convert.append(desc[0])

    return result, column_names, columns_to_convert


def query_to_dataframe(query:str, convert_strings:bool=True) -> pd.DataFrame:
    result, column_names, columns_to_convert = query_mediawiki(query)
    df = pd.DataFrame(
        data=result,
        columns=column_names
    )
    if convert_strings is True:
        for column in columns_to_convert:
            df[column] = df[column].str.decode('utf8')
    return df


def retrieve_namespace_resolver() -> dict[int, str]:
    response = requests.get(
        url=WIKIDATA_API_ENDPOINT,
        params={
            'action' : 'query',
            'meta' : 'siteinfo',
            'siprop' : 'namespaces',
            'formatversion' : '2',
            'format' : 'json'
        },
        headers={ 'User-Agent': USER_AGENT }
    )

    if response.status_code not in [ 200 ]:
        raise RuntimeError('Cannot retrieve namespaces from Wikidata API; HTTP status ' \
                           f'code {response.status_code}')

    try:
        payload = response.json()
    except JSONDecodeError as exception:
        raise RuntimeError('Cannot parse JSON response') from exception

    namespaces = {}
    for namespace, data in payload.get('query', {}).get('namespaces', {}).items():
        namespaces[int(namespace)] = data.get('name')

    return namespaces

def query_pages_with_code(namespaces:dict[int, str]) -> pd.DataFrame:
    query = """SELECT
  page_namespace,
  page_title,
  page_content_model,
  page_len,
  rev_timestamp,
  actor_name
FROM
  page
    JOIN revision_userindex ON page_latest=rev_id
    JOIN actor_revision ON rev_actor=actor_id
WHERE
  page_content_model IN ('css', 'sanitized-css', 'json', 'javascript', 'Scribunto')
  AND page_namespace!=2;
"""

    df = query_to_dataframe(query)

    df['namespace'] = df['page_namespace'].apply(
        func=lambda x : namespaces.get(x)  # pylint: disable=unnecessary-lambda
    )
    df['full_page_title'] = df[['namespace', 'page_title']].apply(
        axis=1,
        func=lambda x : f'{x.namespace}:{x.page_title.replace("_", " ")}'
    )
    df['timestamp'] = pd.to_datetime(df['rev_timestamp'], format='%Y%m%d%H%M%S')

    return df


def print_df_by_content_model(df:pd.DataFrame) -> str:
    content_models = df['page_content_model'].unique().tolist()
    wikitext  = f"""This is a list of all pages in Wikidata with the following criteria:
* page_content_model one of <code>css</code>, <code>sanitized-css</code>, <code>json</code>, <code>javascript</code>, <code>Scribunto</code>
* page not in namespace 2 (User)
This list should contain the majority of pages that include some form of programming code (excluding templates) that needs to be maintained by the community.

Last update of this report: {strftime('%Y-%m-%d, %H:%M:%S')} (UTC)

"""

    for content_model in content_models:
        filt = df['page_content_model']==content_model
        fields = ['full_page_title', 'namespace', 'timestamp', 'actor_name', 'page_len']
        wikitext += print_dataframe_to_wikitext(
            content_model,
            df.loc[filt, fields].sort_values(by='full_page_title')
        )

    return wikitext


def print_dataframe_to_wikitext(content_model:str, df:pd.DataFrame) -> str:
    wikitext  = f'== {content_model} ==\n'
    wikitext += '{| class="wikitable sortable"\n'
    wikitext += '|-\n'
    wikitext += '! page !! namespace !! last edit !! last editor !! page length\n'
    for elem in df.itertuples():
        wikitext += '|-\n'
        wikitext += f'| [[{elem.full_page_title}]] || {elem.namespace} || {elem.timestamp} ||' \
                    f' [[User:{elem.actor_name}]] || {elem.page_len}\n'
    wikitext += '|}\n\n'

    return wikitext


def write_to_wikipage(wikitext:str) -> None:
    site = pwb.Site(code='wikidata', fam='wikidata')
    site.login()

    page = pwb.Page(site, 'User:MisterSynergy/pages_with_code')
    page.text = wikitext
    page.save(
        summary='update list (weekly job via Toolforge) #msynbot #unapproved',
        watch='nochange',
        minor=True,
        quiet=True
    )


def main() -> None:
    namespaces = retrieve_namespace_resolver()
    df = query_pages_with_code(namespaces)

    wikitext = print_df_by_content_model(df)
    write_to_wikipage(wikitext)


if __name__=='__main__':
    main()
    