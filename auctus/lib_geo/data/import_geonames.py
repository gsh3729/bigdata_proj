#!/usr/bin/env python3
import csv
import geopandas
import io
import logging
import os
from shapely import wkb
import sqlite3
import sys
import unicodedata


def normalize(string):
    string = string.lower()
    string = unicodedata.normalize('NFC', string)
    return string


logger = logging.getLogger('import_geonames')


def main(directory):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Get required CSV files
    def get_file(name):
        fullname = os.path.join(directory, name)
        if not os.path.isfile(fullname):
            raise FileNotFoundError(fullname)
        return fullname

    data = get_file('allCountries.txt')
    countries = get_file('countryInfo.txt')
    admin1def = get_file('admin1CodesASCII.txt')
    admin2def = get_file('admin2Codes.txt')
    admin5col = get_file('adminCode5.txt')
    shapes = get_file('shapes_all_low.txt')

    # Get database file
    admins_db = os.path.join(os.path.dirname(__file__), 'admins.gpkg')
    if os.path.exists(admins_db):
        raise FileExistsError("Refusing to overwrite existing admins.gpkg")
    conn = sqlite3.connect(admins_db)
    conn.execute('PRAGMA cache_size=-1000000;')
    conn.execute('PRAGMA synchronous=OFF;')
    places_db = os.path.join(os.path.dirname(__file__), 'places.sqlite3')
    if os.path.exists(places_db):
        raise FileExistsError("Refusing to overwrite existing places.sqlite3")
    conn.execute('ATTACH DATABASE ? AS places;', [places_db])

    # Create schema
    # The 'admins' file/table contains only the places that are admin areas
    with open('schema.sql') as fp:
        conn.executescript(fp.read())
    # The 'places' file/table contains all places, with their admin area if
    # they are included in one
    conn.executescript(
        '''
        CREATE TABLE places.places(
            id INTEGER NOT NULL PRIMARY KEY,
            name TEXT NOT NULL CHECK (name <> ''),
            type TEXT NOT NULL CHECK (type <> ''),
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            continent CHAR(2) NULL CHECK (continent <> ''),
            country TEXT NULL CHECK (country <> ''),
            admin1 TEXT NULL CHECK (admin1 <> ''),
            admin2 TEXT NULL CHECK (admin2 <> ''),
            admin3 TEXT NULL CHECK (admin3 <> ''),
            admin4 TEXT NULL CHECK (admin4 <> ''),
            admin5 TEXT NULL CHECK (admin5 <> '')
        );
        CREATE TABLE places.names(
            name_id INTEGER NOT NULL PRIMARY KEY,
            id INTEGER NOT NULL,
            name TEXT NOT NULL CHECK (name <> '')
        );

        CREATE INDEX places.idx_places_name ON places(name);
        CREATE INDEX places.idx_places_continent ON places(continent);
        CREATE INDEX places.idx_places_country ON places(country);
        CREATE INDEX places.idx_places_admin1 ON places(admin1);
        CREATE INDEX places.idx_places_admin2 ON places(admin2);
        CREATE INDEX places.idx_places_admin3 ON places(admin3);
        CREATE INDEX places.idx_places_admin4 ON places(admin4);
        CREATE INDEX places.idx_places_admin5 ON places(admin5);

        CREATE INDEX places.idx_names_id ON names(id);
        CREATE INDEX places.idx_names_name ON names(name);
        ''',
    )

    # Attach temporary database to store the secondary CSV tables
    conn.executescript(
        '''
        ATTACH DATABASE '' AS alternate;

        CREATE TABLE alternate.countries(
            code TEXT NOT NULL,
            geoname_id INTEGER NOT NULL,
            continent CHAR(2) NOT NULL
        );
        CREATE INDEX alternate.idx_countries_code ON countries(code);

        CREATE TABLE alternate.admin1(
            code TEXT NOT NULL,
            geoname_id INTEGER NOT NULL
        );
        CREATE INDEX alternate.idx_admin1_code ON admin1(code);

        CREATE TABLE alternate.admin2(
            code TEXT NOT NULL,
            geoname_id INTEGER NOT NULL
        );
        CREATE INDEX alternate.idx_admin2_code ON admin2(code);

        CREATE TABLE alternate.admin5(
            code TEXT NOT NULL,
            geoname_id INTEGER NOT NULL
        );
        CREATE INDEX alternate.idx_admin5_id ON admin5(geoname_id);
        ''',
    )

    cursor = conn.cursor()

    # Import country definitions
    logger.info("Importing countries")
    with open(countries) as fp:
        # Skip lines until we get to the data
        while True:
            pos = fp.tell()
            line = fp.readline()
            if not line:
                break
            if not line.startswith('#'):
                # Rewind
                fp.seek(pos, 0)
                break

        reader = csv.reader(fp, delimiter='\t')
        cursor.executemany(
            '''
            INSERT INTO alternate.countries(code, geoname_id, continent)
            VALUES(?, ?, ?);
            ''',
            (
                (row[0] or None, row[16] or None, row[8] or None)
                for row in reader
            ),
        )

    # Import admin 1 and 2 definitions
    logger.info("Importing admin1")
    with open(admin1def) as fp:
        reader = csv.reader(fp, delimiter='\t')
        cursor.executemany(
            '''
            INSERT INTO alternate.admin1(code, geoname_id) VALUES(?, ?);
            ''',
            (
                (row[0] or None, row[3] or None)
                for row in reader
            ),
        )
    logger.info("Importing admin2")
    with open(admin2def) as fp:
        reader = csv.reader(fp, delimiter='\t')
        cursor.executemany(
            '''
            INSERT INTO alternate.admin2(code, geoname_id) VALUES(?, ?);
            ''',
            (
                (row[0] or None, row[3] or None)
                for row in reader
            ),
        )

    # Import admin 5 data
    logger.info("Importing separate admin5 column")
    with open(admin5col) as fp:
        reader = csv.reader(fp, delimiter='\t')
        cursor.executemany(
            '''
            INSERT INTO alternate.admin5(code, geoname_id) VALUES(?, ?);
            ''',
            (
                (row[1] or None, row[0] or None)
                for row in reader
            ),
        )

    # Import data
    logger.info("Importing data")
    with open(data) as fp:
        total_lines = sum(1 for _ in fp)
    report_every = total_lines // 20

    def gen():
        with open(data) as fp:
            reader = csv.reader(fp, delimiter='\t')
            for i, row in enumerate(reader):
                row = [e or None for e in row]  # '' to None
                if i % report_every == 0:
                    logger.info(
                        "%d / %d (%d%%)",
                        i, total_lines, round(i * 100 / total_lines),
                    )
                if not row[6] and not row[7]:
                    continue  # Location has no type
                yield dict(
                    id=row[0], name=row[1], type=row[7] or row[6],
                    latitude=row[4], longitude=row[5],
                    country=row[8], admin1=row[10], admin2=row[11],
                    admin3=row[12], admin4=row[13],
                )

    cursor.executemany(
        '''
        INSERT INTO places.places(
            id, name, type, latitude, longitude,
            continent,
            country, admin1, admin2, admin3, admin4, admin5
        )
        SELECT
            :id,
            :name,
            :type,
            :latitude,
            :longitude,
            (SELECT continent FROM alternate.countries WHERE code = :country),
            :country,
            :admin1,
            :admin2,
            :admin3,
            :admin4,
            (SELECT code FROM alternate.admin5 WHERE geoname_id = :id);
        ''',
        gen(),
    )

    # Insert all names
    logger.info("Importing alternate names from data")

    def gen():
        with open(data) as fp:
            reader = csv.reader(fp, delimiter='\t')
            name_id = 0
            for i, row in enumerate(reader):
                if i % report_every == 0:
                    logger.info(
                        "%d / %d (%d%%)",
                        i, total_lines, round(i * 100 / total_lines),
                    )
                if not row[6] and not row[7]:
                    continue  # Location has no type
                # Use a dictionary instead of set to preserve order
                names = {normalize(row[1]): True}
                if row[3]:
                    for name in row[3].split(','):
                        names[normalize(name)] = True
                for name in names:
                    yield dict(name_id=name_id, id=row[0], name=name)
                    name_id += 1

    cursor.executemany(
        '''
        INSERT INTO places.names(name_id, id, name)
        VALUES(:name_id, :id, :name);
        ''',
        gen(),
    )

    logger.info("Building admins table")

    # Insert countries into admins table
    cursor.execute(
        '''
        INSERT INTO admins(
            name, id, latitude, longitude, level,
            continent,
            country
        )
        SELECT p.name, c.geoname_id, p.latitude, p.longitude, 0,
            c.continent,
            c.code
        FROM
            alternate.countries c
            JOIN places.places p ON p.id = c.geoname_id;
        ''',
    )

    # Insert admin 1 into admins table
    cursor.execute(
        '''
        INSERT INTO admins(
            name, id, latitude, longitude, level,
            continent,
            country, admin1
        )
        SELECT p.name, p.id, p.latitude, p.longitude, 1,
            p.continent,
            p.country, p.admin1
        FROM
            alternate.admin1 a
            JOIN places.places p ON p.id = a.geoname_id;
        ''',
    )

    # Insert admin 2 into admins table
    cursor.execute(
        '''
        INSERT INTO admins(
            name, id, latitude, longitude, level,
            continent,
            country, admin1, admin2
        )
        SELECT p.name, p.id, p.latitude, p.longitude, 2,
            p.continent,
            p.country, p.admin1, p.admin2
        FROM
            alternate.admin2 a
            JOIN places.places p ON p.id = a.geoname_id;
        ''',
    )

    # Insert admin 3, 4, and 5 into admins table
    cursor.execute(
        '''
        INSERT INTO admins(
            name, id, latitude, longitude, level,
            continent,
            country, admin1, admin2, admin3, admin4, admin5
        )
        SELECT name, id, latitude, longitude, 3,
            continent,
            country, admin1, admin2, admin3, NULL, NULL
        FROM places.places
        WHERE type = 'ADM3'
        UNION ALL
        SELECT name, id, latitude, longitude, 4,
            continent,
            country, admin1, admin2, admin3, admin4, NULL
        FROM places.places
        WHERE type = 'ADM4'
        UNION ALL
        SELECT name, id, latitude, longitude, 5,
            continent,
            country, admin1, admin2, admin3, admin4, admin5
        FROM places.places
        WHERE type = 'ADM5';
        ''',
    )

    # Copy names
    logger.info("Copying admin names")

    cursor.execute(
        '''
        INSERT INTO names(name_id, id, name)
        SELECT name_id, id, name FROM places.names
        WHERE id IN (SELECT id FROM admins);
        ''',
    )

    # Import shapes
    def gen():
        with open(shapes) as fp:
            csv.field_size_limit(1 << 20)
            reader = csv.reader(fp, delimiter='\t')
            try:
                next(reader)
            except StopIteration:
                pass

            for row in reader:
                id, geojson = row
                df = geopandas.read_file(io.BytesIO(geojson.encode('utf-8')))
                shape = df.iloc[0, 0]
                yield dict(id=id, shape=wkb.dumps(shape))

    conn.executemany(
        '''
        UPDATE admins SET shape = :shape
        WHERE id = :id;
        ''',
        gen(),
    )

    conn.commit()


if __name__ == '__main__':
    main(*sys.argv[1:])
