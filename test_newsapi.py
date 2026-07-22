import os
from datetime import date
from dotenv import load_dotenv
from eventregistry import EventRegistry, QueryArticlesIter

load_dotenv()


def test_newsapi_connectivity():
    """
    Verifies the newsapi.ai key is valid and returns financial articles.
    Fetches exactly 1 article to minimize credit usage.
    Does not require AWS credentials.
    """
    api_key = os.getenv('NEWS_API_KEY')
    assert api_key, "NEWS_API_KEY not found — add it to your .env file"

    er = EventRegistry(apiKey=api_key, allowUseOfArchive=False, verboseOutput=False)

    today = date.today().isoformat()
    q = QueryArticlesIter(
        keywords='"stock market" OR earnings',
        dateStart=today,
        dateEnd=today,
        lang='eng',
    )

    articles = []
    for article in q.execQuery(er, sortBy='date', maxItems=1):
        articles.append(article)

    assert len(articles) > 0, "No articles returned — check API key or quota"

    article = articles[0]
    for field in ('title', 'url', 'dateTime'):
        assert field in article and article[field], f"Article missing field: {field}"

    print(f"OK — sample headline: {article['title']}")
    print(f"    source: {article.get('source', {}).get('title')}")
    print(f"    published: {article['dateTime']}")


if __name__ == '__main__':
    test_newsapi_connectivity()
