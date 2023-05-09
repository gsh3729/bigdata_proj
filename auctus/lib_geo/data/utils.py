import asyncio
import itertools
import logging
import requests
from urllib.parse import urlencode


logger = logging.getLogger('import_wikidata')


def sparql_query(query):
    """Get results from the Wikidata SparQL endpoint.
    """
    url = 'https://query.wikidata.org/sparql?' + urlencode({
        'query': query,
    })
    logger.info("Querying: %s", url)
    response = requests.get(
        url,
        headers={
            'Accept': 'application/sparql-results+json',
            'User-Agent': 'Auctus',
        },
    )
    response.raise_for_status()
    obj = response.json()
    results = obj['results']['bindings']
    logger.info("SparQL: %d results", len(results))
    return results


def literal(item):
    assert item['type'] == 'literal'
    return item['value']


def q_entity_uri(item):
    assert item['type'] == 'uri'
    prefix = 'http://www.wikidata.org/entity/'
    value = item['value']
    assert value.startswith(prefix)
    return value[len(prefix):]


def uri(item):
    assert item['type'] == 'uri'
    return item['value']


async def apply_async(func, iterable, *, max_tasks):
    # Start N tasks
    tasks = {
        asyncio.ensure_future(func(*elem))
        for elem in itertools.islice(iterable, max_tasks)
    }

    while tasks:
        # Wait for any task to complete
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Poll them
        for task in done:
            tasks.discard(task)
            task.result()

        # Schedule new tasks
        for elem in itertools.islice(iterable, max_tasks - len(tasks)):
            tasks.add(asyncio.ensure_future(func(*elem)))
