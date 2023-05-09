import argparse
import logging

from . import __version__ as VERSION, GeoData


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Download the data",
    )
    parser.add_argument(
        '--version',
        action='version',
        version='datamart-geo %s' % VERSION,
    )
    parser.add_argument(
        'directory',
        action='store',
        nargs=argparse.OPTIONAL,
    )
    parser.add_argument(
        '--update',
        action='store_true',
        default=False,
    )
    args = parser.parse_args()
    GeoData.download(args.directory, update=args.update)
