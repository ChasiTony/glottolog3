"""
Language Description Status Browser
-----------------------------------

The description status of languages can be investigated in relation to the vitality (or
endangerment) of a language.
"""
from collections import defaultdict, namedtuple

from pyramid.view import view_config
from sqlalchemy.orm import aliased, joinedload
from clld.web.adapters.geojson import GeoJson
from clld.web.maps import Map, Layer, Legend
from clld.web.util.helpers import JS
from clld.web.util.htmllib import HTML
from clld.web.util.multiselect import MultiSelect
from clld.db.meta import DBSession
from clld.db.models import common
from clldutils.jsonlib import load
from clldutils.path import Path

import glottolog3
from glottolog3.models import (
    DOCTYPES, Languoid, Macroarea, Languoidmacroarea, LanguoidLevel,
)
from glottolog3.maps import Language


def ldstatus():
    return load(Path(glottolog3.__file__).parent.joinpath('static', 'ldstatus.json'))


@view_config(route_name='langdocstatus', renderer='langdocstatus/intro.mako')
def intro(req):
    return {
        'macroareas': DBSession.query(Macroarea).order_by(Macroarea.name),
        'families': family_query().options(joinedload(Languoid.macroareas)),
    }


SimplifiedDoctype = namedtuple('SimplifiedDoctype', 'ord name color')
SIMPLIFIED_DOCTYPES = [
    SimplifiedDoctype(i, *args) for i, args in enumerate([
        ('grammar', '00ff00'),
        ('grammar sketch', 'ff6600'),
        ('phonology/text', 'ff4400'),
        ('wordlist or less', 'ff0000'),
    ])
]
SIMPLIFIED_DOCTYPE_MAP = defaultdict(lambda: SIMPLIFIED_DOCTYPES[3])
for i, dt in enumerate(DOCTYPES):
    if i <= 1:
        SIMPLIFIED_DOCTYPE_MAP[i] = SIMPLIFIED_DOCTYPES[i]  # i.e. grammar or grammarsketch
        SIMPLIFIED_DOCTYPE_MAP[dt] = SIMPLIFIED_DOCTYPES[i]
    elif 1 < i < DOCTYPES.index('wordlist'):
        SIMPLIFIED_DOCTYPE_MAP[i] = SIMPLIFIED_DOCTYPES[2]
        SIMPLIFIED_DOCTYPE_MAP[dt] = SIMPLIFIED_DOCTYPES[2]

Endangerment = namedtuple('Endangerment', 'ord name shape')
ENDANGERMENTS = [
    Endangerment(i, *args) for i, args in enumerate([
        ('safe', 'c'),
        ('vulnerable', 'c'),
        ('definitely endangered', 's'),
        ('severely endangered', 'd'),
        ('critically endangered', 't'),
        ('extinct', 'f'),
    ])
]
ENDANGERMENT_MAP = defaultdict(
    lambda: ENDANGERMENTS[0], [(ed.name, ed) for ed in ENDANGERMENTS])


def src2dict(s):
    return dict(zip(['id', 'doctype', 'year', 'pages', 'name'], s))


class DescStatsGeoJson(GeoJson):
    def feature_iterator(self, ctx, req):
        return ctx

    def featurecollection_properties(self, ctx, req):
        return {'layer': 'desc'}

    def get_icon(self, req, type_, endangerment):
        return self.obj[0][endangerment.shape + SIMPLIFIED_DOCTYPE_MAP[type_].color]

    def feature_properties(self, ctx, req, feature):
        endangerment = ENDANGERMENT_MAP[feature.status.value]
        med, sources = self.obj[1].get(feature.id, (None, []))
        # augment the source dicts
        sources = [src2dict(v) for v in sources]
        for s in sources:
            s['icon'] = self.get_icon(req, s['doctype'], endangerment)
            s['sdt'] = SIMPLIFIED_DOCTYPE_MAP[s['doctype']].ord

        med = src2dict(med) if med else med
        return {
            'ed': endangerment.ord,
            'icon': self.get_icon(req, med['doctype'] if med else None, endangerment),
            'med': med['id'] if med else None,
            'sdt': SIMPLIFIED_DOCTYPE_MAP[med['doctype'] if med else None].ord,
            'info_query': {'source': med['id']} if med else {},
            'red_icon': self.get_icon(req, None, endangerment),
            'sources': sources}

    def get_language(self, ctx, req, feature):
        return Language(
            0, feature.name, feature.longitude, feature.latitude, feature.id)


class DescStatsMap(Map):
    def __init__(self, ctx, req, icon_map):
        self.ldstatus = ldstatus()
        self.icon_map = icon_map
        Map.__init__(self, ctx, req)

    def get_layers(self):
        yield Layer(
            'languoids',
            'Languoids',
            DescStatsGeoJson((self.icon_map, self.ldstatus)).render(self.ctx, self.req, dump=False))

    def get_options(self):
        return {
            'icon_size': 20,
            'hash': True,
            'max_zoom': 12,
            'on_init': JS('GLOTTOLOG3.LangdocStatus.update'),
            'no_showlabels': True}

    def get_legends(self):
        def img(spec):
            return HTML.img(
                src=self.icon_map[spec], height='20', width='20', style='margin-left: 0.5em;')

        def desc(text):
            return HTML.span(text, style='margin-left: 0.5em; margin-right: 0.5em;')

        values = [desc('Most extensive description is a ...')]
        for sdt in SIMPLIFIED_DOCTYPES:
            values.append((img('c' + sdt.color), desc(sdt.name)))
        values.append(desc('Language is ...'))
        for ed in ENDANGERMENTS:
            values.append((
                HTML.label(
                    HTML.input(
                        type='checkbox',
                        checked='checked',
                        id='marker-toggle-ed-' + str(ed.ord),
                        onclick='GLOTTOLOG3.LangdocStatus.toggleMarkers()'),
                    img(ed.shape + 'ffffff'),
                    desc(ed.name.lower()))))
        yield Legend(self, 'values', values, label='Legend')


def language_query(req=None):
    query = DBSession.query(common.Language) \
        .filter(common.Language.active == True) \
        .filter(common.Language.latitude != None) \
        .filter(Languoid.level == LanguoidLevel.language)
    if req:
        macroarea = req.params.get('macroarea')
        if macroarea:
            query = query.join(Languoidmacroarea).join(Macroarea)\
                .filter(Macroarea.name == macroarea)
        families = [f for f in req.params.get('family', '').split(',') if f]
        if families:
            family = aliased(Languoid)
            query = query.join(family, Languoid.family_pk == family.pk)\
                .filter(family.id.in_(families))

    return query


def family_query(req=None):
    query = DBSession.query(Languoid)\
        .filter(Languoid.father_pk == None)\
        .filter(common.Language.active == True)\
        .order_by(common.Language.name)
    if req:
        macroarea = req.params.get('macroarea')
        if macroarea:
            query = query.join(Languoidmacroarea).join(Macroarea)\
                .filter(Macroarea.name == macroarea)
    return query


def _get_families(req):
    families = [f for f in req.params.get('family', '').split(',') if f]
    if families:
        return DBSession.query(Languoid).filter(Languoid.id.in_(families)).all()
    return []


@view_config(route_name='langdocstatus.browser', renderer='langdocstatus/browser.mako')
def browser(req):
    ms = MultiSelect(
        req, 'families', 'msfamily', collection=family_query(req), selected=_get_families(req))

    icon_map = {}
    for color in [sdt.color for sdt in SIMPLIFIED_DOCTYPES] + ['ffffff']:
        for shape in [ed.shape for ed in ENDANGERMENTS]:
            spec = shape + color
            icon_map[spec] = req.static_url('clld:web/static/icons/%s.png' % spec)

    return {
        'families': ms,
        'macroareas': DBSession.query(Macroarea).all(),
        'map': DescStatsMap(language_query(req), req, icon_map),
        'icon_map': icon_map,
        'doctypes': SIMPLIFIED_DOCTYPES,
        'endangerments': ENDANGERMENTS}


@view_config(
    route_name='langdocstatus.languages', renderer='langdocstatus/language_table.mako')
def languages(req):
    """
    :param req:
    :return: list of (language, med) pairs with matching endangerment and doctype.
    """
    langs = []
    macroarea = req.params.get('macroarea')
    family = _get_families(req)
    year = req.params.get('year')

    label = 'Languages'
    try:
        ed = ENDANGERMENTS[int(req.matchdict['ed'])]
        label = HTML.em(ed.name) + ' languages'
    except IndexError:
        ed = None

    if family:
        label = label + ' of the %s families' % ', '.join(f.name for f in family)

    if macroarea:
        label = label + ' from ' + macroarea

    try:
        sdt = SIMPLIFIED_DOCTYPES[int(req.matchdict['sdt'])]
    except IndexError:
        sdt = None

    if sdt:
        label = label + ' whose most extensive description'

        if year:
            year = int(year)
            label = label + ' in %s' % year

        label = label + ' is a ' + sdt.name

    stats = ldstatus()
    for lang in language_query(req):
        if ed:
            _ed = lang.status.value
            if ed.name != _ed:
                continue

        med_, sources = stats.get(lang.id, (None, []))
        med = None
        if year:
            for s in sources:
                s = src2dict(s)
                if s['year'] <= year:
                    med = s
                    break
        else:
            med = med_

        if sdt:
            _sdt = SIMPLIFIED_DOCTYPE_MAP[med['doctype'] if med else None]
            if _sdt.ord != sdt.ord:
                continue

        langs.append((lang, med))

    return {'languages': sorted(langs, key=lambda l: l[0].name), 'label': label}
