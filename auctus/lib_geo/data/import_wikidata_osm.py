#!/usr/bin/env python3
import csv
import logging
import os
import sys

from utils import sparql_query, q_entity_uri, literal


logger = logging.getLogger('import_wikidata_osm')


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    os.chdir(os.path.dirname(__file__) or '.')

    csv.field_size_limit(sys.maxsize)

    # Find items with GeoNames ID and OSM ID from Wikidata
    if not os.path.exists('osm_shapes.csv'):
        with open('osm_shapes.csv', 'w') as fout:
            writer = csv.writer(fout)
            writer.writerow(['wikidataId', 'geonamesId', 'label', 'osmId'])
            rows = sparql_query(
                '''
                SELECT ?item ?itemLabel ?geonamesId ?osmId
                WHERE
                {
                  ?item wdt:P1566 ?geonamesId.
                  ?item wdt:P402 ?osmId.
                  SERVICE wikibase:label {
                    bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en".
                  }
                }
                ''',
            )
            for row in rows:
                writer.writerow([
                    q_entity_uri(row['item']),
                    literal(row['geonamesId']),
                    literal(row['itemLabel']),
                    literal(row['osmId']),
                ])


if __name__ == '__main__':
    main()
