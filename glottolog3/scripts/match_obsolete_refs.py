# -*- coding: utf-8 -*-
import json

import transaction
from clld.scripts.util import parsed_args
from clld.db.meta import DBSession
from clld.db.models.common import Config, Source

from glottolog3.scripts.util import match_obsolete_refs, get_obsolete_refs
from glottolog3.models import Ref


def main(args):
    #get_obsolete_refs(args)
    with transaction.manager:
        #match_obsolete_refs(args)

        #
        # TODO:
        # - create bibtex file containing all refs to be removed!
        # -
        #
        matched = args.data_file(args.version, 'obsolete_refs_matched.json')
        if matched.exists():
            with open(matched) as fp:
                matched = json.load(fp)
        else:
            matched = {}

        for id_, repl in matched.items():
            if not repl:
                continue
            ref = Ref.get(id_, default=None)
            if ref is None:
                continue
            Config.add_replacement(ref, repl, session=DBSession, model=Source)
            DBSession.delete(ref)


if __name__ == '__main__':  # pragma: no cover
    main(parsed_args((("--version",), dict(default=""))))