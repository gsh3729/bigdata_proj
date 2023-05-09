import unittest

import datamart_geo


class TestGeoData(unittest.TestCase):
    def setUp(self):
        self.geo_data = datamart_geo.GeoData('data')

    def test_get_area(self):
        # Search for an administrative area
        a_france = self.geo_data.resolve_name('France')
        assert repr(a_france) == (
            '<datamart_geo.Area "Republic of France" (3017382) type=Type.ADMIN_0>'
        )
        self.assertEqual(a_france.type, datamart_geo.Type.ADMIN_0)
        self.assertEqual(a_france.type, datamart_geo.Type.COUNTRY)
        self.assertEqual((a_france.latitude, a_france.longitude), (46.0, 2.0))

        # Other area
        a_cuers = self.geo_data.resolve_name('Cuers')
        self.assertEqual(
            repr(a_cuers),
            '<datamart_geo.Area "Cuers" (6451482) type=Type.ADMIN_4>',
        )
        self.assertEqual(a_cuers.type, datamart_geo.Type.ADMIN_4)
        self.assertEqual((a_cuers.latitude, a_cuers.longitude), (43.2375, 6.07083))

        self.assertEqual(
            a_cuers.names,
            {'Cuers', 'cuers', 'ker', 'kjuers', 'qu ai er', 'кер', 'кюерс', '屈埃尔'},
        )

    def test_get_parent(self):
        a_cuers = self.geo_data.resolve_name('Cuers')

        a_toulon = a_cuers.get_parent_area()
        self.assertEqual(
            repr(a_toulon),
            '<datamart_geo.Area "Arrondissement de Toulon" (2972326) type=Type.ADMIN_3>',
        )
        self.assertEqual(a_toulon.type, datamart_geo.Type.ADMIN_3)
        self.assertEqual((a_toulon.latitude, a_toulon.longitude), (43.1837, 6.04692))

        a_france = a_cuers.get_parent_area(datamart_geo.Type.COUNTRY)
        self.assertEqual(
            repr(a_france),
            '<datamart_geo.Area "Republic of France" (3017382) type=Type.ADMIN_0>',
        )
        self.assertEqual(a_france.type, datamart_geo.Type.COUNTRY)

        self.assertEqual(
            tuple(round(c, 4) for c in a_france.bounds),
            (-178.3874, 172.3057, -50.2187, 51.3056),
        )

    def test_get_all(self):
        self.assertEqual(
            [
                (repr(a), repr(a.get_parent_area(datamart_geo.Type.ADMIN_1)))
                for a in self.geo_data.resolve_name_all('Var')
            ],
            [
                (
                    '<datamart_geo.Area "Var" (2970749) type=Type.ADMIN_2>',
                    '<datamart_geo.Area "Provence-Alpes-Côte d\'Azur" (2985244) type=Type.ADMIN_1>',
                ),
                (
                    '<datamart_geo.Area "Vars" (6427887) type=Type.ADMIN_4>',
                    '<datamart_geo.Area "Nouvelle-Aquitaine" (11071620) type=Type.ADMIN_1>',
                ),
                (
                    '<datamart_geo.Area "Vars" (6442138) type=Type.ADMIN_4>',
                    '<datamart_geo.Area "Bourgogne-Franche-Comté" (11071619) type=Type.ADMIN_1>',
                ),
            ],
        )

    def test_fuzzy(self):
        # Fuzzy search for an area
        hits = self.geo_data.resolve_name_fuzzy('cuerss')
        score, area = hits[0]
        self.assertAlmostEqual(score, 0.6666667)
        self.assertEqual(area.id, 6451482)
        self.assertEqual(
            [(round(s, 4), repr(a)) for s, a in hits],
            [
                (0.6667, '<datamart_geo.Area "Cuers" (6451482) type=Type.ADMIN_4>'),
                (0.4000, '<datamart_geo.Area "Cusio" (6536540) type=Type.ADMIN_3>'),
                (0.3636, '<datamart_geo.Area "Cura Carpignano" (6543766) type=Type.ADMIN_3>'),
                (0.3333, '<datamart_geo.Area "Cuevas" (11770784) type=Type.ADMIN_4>'),
                (0.3333, '<datamart_geo.Area "Cuélas" (6431899) type=Type.ADMIN_4>'),
                (0.3333, '<datamart_geo.Area "Cuerva" (6361715) type=Type.ADMIN_3>'),
                (0.3333, '<datamart_geo.Area "Cuevas" (11157503) type=Type.ADMIN_5>'),
                (0.3333, '<datamart_geo.Area "Kuurne" (2793858) type=Type.ADMIN_4>'),
                (0.3077, '<datamart_geo.Area "Cureggio" (6543423) type=Type.ADMIN_3>'),
                (0.3077, '<datamart_geo.Area "Cuerden" (7295341) type=Type.ADMIN_4>'),
                (0.3000, '<datamart_geo.Area "Roses" (6534115) type=Type.ADMIN_3>'),
                (0.3000, '<datamart_geo.Area "Cue" (7839494) type=Type.ADMIN_2>'),
            ],
        )


if __name__ == '__main__':
    unittest.main()
