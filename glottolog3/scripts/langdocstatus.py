# -*- coding: utf-8 -*-
import transaction
from math import ceil

from sqlalchemy.orm import joinedload

from clld.scripts.util import parsed_args
from clld.db.models.common import LanguageSource, Language
from clld.db.models.common import Source as Source_
from clld.db.meta import DBSession
from clldutils.jsonlib import dump

from glottolog3.models import DOCTYPES, Ref
from glottolog3.langdocstatus import language_query


class Source(object):
    """Representation of a source amenable to computation of MEDs
    (Most Extensive Description)
    """
    def __init__(self, source):
        self.index = len(DOCTYPES)
        self.doctype = None

        for doctype in source.doctypes:
            doctype = doctype.id
            if doctype and DOCTYPES.index(doctype) < self.index:
                self.index = DOCTYPES.index(doctype)
                self.doctype = doctype

        # the number of pages is divided by number of doctypes times number of
        # described languages
        self.pages = int(ceil(
            float(source.pages_int or 0) / ((len(source.doctypes) or 1) * len(source.languages))))

        self.year = source.year_int
        self.id = source.id
        self.name = source.name

    def __json__(self):
        return [getattr(self, k) for k in 'id doctype year pages name'.split()]

    def __cmp__(self, other):
        """This is the algorithm:
        "more extensive" means: better doctype (i.e. lower index) or more pages or newer.

        Thus, a sorted list of Sources will have the MED as first element.
        """
        return cmp(
            (self.index, -self.pages, -(self.year or 0), int(self.id)),
            (other.index, -other.pages, -(other.year or 0), int(other.id)))


def main(args):  # pragma: no cover
    ldstatus = {}
    limit = 200
    q = language_query().order_by(Language.pk)
    offset = 0
    # we merge information about extinct languages from unesco and Harald.
    if 1:
        # loop over active, established languages with geo-coords
        while True:
            transaction.begin()
            langs = [l for l in q.offset(offset).limit(limit)]
            if not langs:
                break
            offset += limit
            # let's collect the relevant sources in a way that allows computation of med.
            # Note: we limit refs to the ones without computerized assignments.
            lsources = list(DBSession.query(Ref).join(LanguageSource)\
                .filter(LanguageSource.language_pk.in_([l.pk for l in langs])) \
                .filter(Ref.ca_doctype_trigger == None)\
                .filter(Ref.ca_language_trigger == None)\
                .options(joinedload(Ref.doctypes), joinedload(Source_.languages)))
            for l in langs:
                sources = [s for s in lsources if l in s.languages]
                sources = sorted(map(Source, sources))

                # keep the overall med
                # note: this source may not be included in the potential meds computed
                # below,
                # e.g. because it may not have a year.
                med = sources[0].__json__() if sources else None

                # now we have to compute meds respecting a cut-off year.
                # to do so, we collect eligible sources per year and then
                # take the med of this collection.
                potential_meds = []

                # we only have to loop over publication years within all sources, because
                # only in these years something better might have come along.
                for year in set(s.year for s in sources if s.year):
                    # let's see if something better was published!
                    eligible = [s for s in sources if s.year and s.year <= year]
                    if eligible:
                        potential_meds.append(sorted(eligible)[0])

                # we store the precomputed sources information as jsondata:
                ldstatus[l.id] = [
                    med,
                    [s.__json__() for s in
                     sorted(set(potential_meds), key=lambda s: -s.year)]]
            print(offset)
            transaction.abort()

    dump(ldstatus, 'glottolog3/static/ldstatus.json', indent=4)


if __name__ == '__main__':
    main(parsed_args())
