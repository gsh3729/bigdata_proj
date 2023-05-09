Data importing scripts
======================

This directory contains the scripts used to build the database. It is not distributed with the datamart-geo library: the library simply downloads the finished database.

The data is built around the [GeoNames data](http://download.geonames.org/export/dump/readme.txt) which is itself compiled from a variety of local sources. It contains both *administrative areas*, which are named regions recognized by governments and organized in levels 0 to 5 (where 0 is country and the rest is country-dependent, for example 1 might be a state or province, etc); and *places*, which are named locations of various importance that don't fit the administrative hierarchy (example: cities in most countries, rivers and lakes, parks, tunnels, airports, mountains, waterfalls, ...)

`import_geonames.py`
--------------------

This script imports the GeoNames data into SQLite3. It builds two databases:

* `admins.sqlite3` which contains only the administrative areas (with a separate table to store the alternate names of areas)
* `places.sqlite3` which contains the other places that are not administrative areas (but can lie in an area). It is assumed that those don't have shapes, only locations (single point).

It will import the shapes from `shapes_all_low.txt`, but very few shapes are available from GeoNames.

It takes about 5 minutes to import about 375,000 areas and 12,000,000 places.

`import_wikidata_osm.py`
------------------------

This script queries Wikidata to obtain the mapping of GeoNames ID (`property P1566` <https://www.wikidata.org/wiki/Property:P1566>`__) to OpenStreetMap Relation ID (`property P402 <https://www.wikidata.org/wiki/Property:P402>`__). This mapping is written to the CSV file ``osm_shapes.csv``.

`import_osm.py`
---------------

This goes over an OpenStreetMap XML dump and extracts the relation listed in ``osm_shapes.csv`` into a SQLite3 database.

To get OpenStreetMap dumps, `see their wiki <https://wiki.openstreetmap.org/wiki/Planet.osm>`__.

`osm_db_to_wkt.py`
------------------

This reads the SQLite3 databases built from the OpenStreetMap data and set the ``shape`` column of the main database, converting the relation->ways->nodes tables into simple multipolygon values in WKB format (with the additional header required by the GeoPackage format).

License
=======

GeoNames is CC-BY-4.0. Therefore you have to mention that the data comes from GeoNames (https://www.geonames.org/) and their sources (listed here: https://www.geonames.org/datasources/).

Wikidata is CC0 and can be used without restrictions.

OpenStreetMap is ODbL, which is both attribution and share-alike: https://www.openstreetmap.org/copyright. This means that, if including OpenStreetMap data, you resulting dataset has to be licensed under the terms of the ODbL and credit "© OpenStreetMap contributors and sources listed at https://www.openstreetmap.org/copyright" (since a lot of their sources require attribution).
