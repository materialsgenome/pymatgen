#!/usr/bin/env python

"""
Classes and methods related to the Structure Notation Language (SNL)
"""

__author__ = 'Anubhav Jain, Shyue Ping Ong'
__credits__ = 'Dan Gunter'
__copyright__ = 'Copyright 2013, The Materials Project'
__version__ = '0.1'
__maintainer__ = 'Anubhav Jain'
__email__ = 'ajain@lbl.gov'
__date__ = 'Feb 11, 2013'

import sys
import cStringIO
import re
import datetime
from collections import namedtuple
import json

from pymatgen.core.structure import Structure, Molecule
from pymatgen.serializers.json_coders import PMGJSONDecoder, PMGJSONEncoder
from pybtex.database.input import bibtex


MAX_HNODE_SIZE = 64000  # maximum size (bytes) of SNL HistoryNode
MAX_DATA_SIZE = 256000  # maximum size (bytes) of SNL data field
MAX_HNODES = 100  # maximum number of HistoryNodes in SNL file
MAX_BIBTEX_CHARS = 20000  # maximum number of characters for BibTeX reference


def is_valid_bibtex(reference):
    """
    Use pybtex to validate that a reference is in proper BibTeX format

    Args:
        reference:
            A String reference in BibTeX format

    Returns:
        Boolean indicating if reference is valid bibtex.
    """
    # str is necessary since pybtex seems to have an issue with unicode. The
    # filter expression removes all non-ASCII characters.
    sio = cStringIO.StringIO(str("".join(filter(lambda x: ord(x) < 128,
                                                reference))))
    parser = bibtex.Parser()
    bib_data = parser.parse_stream(sio)
    return len(bib_data.entries) > 0


class HistoryNode(namedtuple('HistoryNode', ['name', 'url', 'description'])):
    """
    A HistoryNode represents a step in the chain of events that lead to a
    Structure. HistoryNodes leave 'breadcrumbs' so that you can trace back how
    a Structure was created. For example, a HistoryNode might represent pulling
    a Structure from an external database such as the ICSD or CSD. Or, it might
    represent the application of a code (e.g. pymatgen) to the Structure, with
    a custom description of how that code was applied (e.g. a site removal
    Transformation was applied).

    A HistoryNode contains three fields:

    .. attribute:: name

        The name of a code or resource that this Structure encountered in
        its history (String)

    .. attribute:: url

        The URL of that code/resource (String)

    .. attribute:: description

        A free-form description of how the code/resource is related to the
        Structure (dict).
    """

    @property
    def to_dict(self):
        return dict(self._asdict())

    @staticmethod
    def from_dict(h_node):
        return HistoryNode(h_node['name'], h_node['url'],
                           h_node['description'])

    @staticmethod
    def parse_history_node(h_node):
        """
        Parses a History Node object from either a dict or a tuple.

        Args:
            h_node:
                A dict with name/url/description fields or a 3-element tuple.

        Returns:
            History node.
        """
        if isinstance(h_node, dict):
            return HistoryNode.from_dict(h_node)

        else:
            if len(h_node) != 3:
                raise ValueError("Invalid History node, "
                                 "should be dict or (name, version, "
                                 "description) tuple: {}".format(h_node))
            return HistoryNode(h_node[0], h_node[1], h_node[2])


class Author(namedtuple('Author', ['name', 'email'])):
    """
    An Author contains two fields:

    .. attribute:: name

        Name of author (String)

    .. attribute:: email

        Email of author (String)
    """

    def __str__(self):
        """
        String representation of an Author
        """
        return '{} <{}>'.format(self.name, self.email)

    @property
    def to_dict(self):
        return dict(self._asdict())

    @staticmethod
    def from_dict(d):
        return Author(d['name'], d['email'])

    @staticmethod
    def parse_author(author):
        """
        Parses an Author object from either a String, dict, or tuple

        Args:
            author:
                A String formatted as "NAME <email@domain.com>",
                (name, email) tuple, or a dict with name and email keys

        Returns:
            An Author object.
        """
        if isinstance(author, basestring):
            # Regex looks for whitespace, (any name), whitespace, <, (email),
            # >, whitespace
            m = re.match('\s*(.*?)\s*<(.*?@.*?)>\s*', author)
            if not m or m.start() != 0 or m.end() != len(author):
                raise ValueError("Invalid author format! {}".format(author))
            return Author(m.groups()[0], m.groups()[1])
        elif isinstance(author, dict):
            return Author.from_dict(author)
        else:
            if len(author) != 2:
                raise ValueError("Invalid author, should be String or (name, "
                                 "email) tuple: {}".format(author))
            return Author(author[0], author[1])


class StructureNL(object):
    """
    The Structure Notation Language (SNL, pronounced 'snail') is container
    for a pymatgen Structure/Molecule object with some additional fields for
    enhanced provenance. It is meant to be imported/exported in a JSON file
    format with the following structure:

    - about
        - created_at
        - authors
        - projects
        - references
        - remarks
        - data
        - history
    - lattice (optional)
    - sites
    """

    def __init__(self, struct_or_mol, authors, projects=None, references='',
                 remarks=None, data=None, history=None, created_at=None):
        """
        Args:
            struct_or_mol:
                A pymatgen.core.structure Structure/Molecule object
            authors:
                *List* of {"name":'', "email":''} dicts,
                *list* of Strings as 'John Doe <johndoe@gmail.com>',
                or a single String with commas separating authors
            projects:
                List of Strings ['Project A', 'Project B']
            references:
                A String in BibTeX format
            remarks:
                List of Strings ['Remark A', 'Remark B']
            data:
                A free form dict. Namespaced at the root level with an
                underscore, e.g. {"_materialsproject": <custom data>}
            history:
                List of dicts - [{'name':'', 'url':'', 'description':{}}]
            created_at:
                A datetime object
        """
        # initialize root-level structure keys
        self.structure = struct_or_mol

        # turn authors into list of Author objects
        authors = authors.split(',')\
            if isinstance(authors, basestring) else authors
        self.authors = [Author.parse_author(a) for a in authors]

        # turn projects into list of Strings
        projects = projects if projects else []
        self.projects = [projects] \
            if isinstance(projects, basestring) else projects

        # check that references are valid BibTeX
        if references and not is_valid_bibtex(references):
            raise ValueError("Invalid format for SNL reference! Should be "
                             "BibTeX string.")
        if len(references) > MAX_BIBTEX_CHARS:
            raise ValueError("The BibTeX string must be fewer than {} chars "
                             ", you have {}"
                             .format(MAX_BIBTEX_CHARS, len(references)))

        self.references = references

        # turn remarks into list of Strings
        remarks = remarks if remarks else []
        self.remarks = [remarks] if isinstance(remarks, basestring) \
            else remarks

        # check data limit
        self.data = data if data else {}
        if not sys.getsizeof(self.data) < MAX_DATA_SIZE:
            raise ValueError("The data dict exceeds the maximum size limit of"
                             " {} bytes (you have {})"
                             .format(MAX_DATA_SIZE, sys.getsizeof(data)))

        for k, v in self.data.items():
            if not k.startswith("_"):
                raise ValueError("data must contain properly namespaced data "
                                 "with keys starting with an underscore. The "
                                 "key {} does not start with an underscore.",
                                 format(k))

        # check for valid history nodes
        history = history if history else []  # initialize null fields
        if len(history) > MAX_HNODES:
            raise ValueError("A maximum of {} History nodes are supported, "
                             "you have {}!".format(MAX_HNODES, len(history)))
        self.history = [HistoryNode.parse_history_node(h) for h in history]
        if not all([sys.getsizeof(h) < MAX_HNODE_SIZE for h in history]):
            raise ValueError("One or more history nodes exceeds the maximum "
                             "size limit of {} bytes".format(MAX_HNODE_SIZE))

        self.created_at = created_at if created_at \
            else datetime.datetime.utcnow()

    @property
    def to_dict(self):
        d = self.structure.to_dict
        d["@module"] = self.__class__.__module__
        d["@class"] = self.__class__.__name__
        d["about"] = {"authors": [a.to_dict for a in self.authors],
                      "projects": self.projects,
                      "references": self.references,
                      "remarks": self.remarks,
                      "history": [h.to_dict for h in self.history],
                      "created_at": self.created_at}
        d["about"].update(json.loads(json.dumps(self.data,
                                                cls=PMGJSONEncoder)))
        return d

    @staticmethod
    def from_dict(d):
        a = d["about"]
        dec = PMGJSONDecoder()

        created_at = dec.process_decoded(a.get("created_at"))
        data = {k: v for k, v in d["about"].items()
                if k.startswith("_")}
        data = dec.process_decoded(data)

        structure = Structure.from_dict(d) if "lattice" in d \
            else Molecule.from_dict(d)
        return StructureNL(structure, a["authors"],
                           projects=a.get("projects", None),
                           references=a.get("references", ""),
                           remarks=a.get("remarks", None), data=data,
                           history=a.get("history", None),
                           created_at=created_at)

    def __str__(self):
        return "\n".join(["{}\n{}".format(k, getattr(self, k))
                          for k in ("structure", "authors", "projects",
                                    "references", "remarks", "data", "history",
                                    "created_at")])

    def __eq__(self, other):
        return all(map(lambda n: getattr(self, n) == getattr(other, n),
                       ("structure", "authors", "projects", "references",
                        "remarks", "data", "history", "created_at")))

    def __ne__(self, other):
        return not self.__eq__(other)