#!/usr/bin/env python

'''
This module provides classes to interface with the Materials Project http REST
interface to enable the creation of data structures and pymatgen objects using
Materials Project data. 
'''

from __future__ import division

__author__ = "Shyue Ping Ong"
__copyright__ = "Copyright 2012, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Shyue Ping Ong"
__email__ = "shyue@mit.edu"
__date__ = "Jun 8, 2012"

import urllib
import urllib2

from pymatgen.serializers.json_coders import PMGJSONDecoder
import json
from pymatgen.entries.compatibility import MaterialsProjectCompatibility


class MPRestAdaptor(object):
    """
    A class to conveniently interface with the Materials Project REST interface.
    """

    supported_properties = ("structure", "initial_structure", "final_structure",
                            "energy", "energy_per_atom",
                            "formation_energy_per_atom", "nsites", "formula",
                            "pretty_formula", "is_hubbard", "elements",
                            "nelements", "e_above_hull", "hubbards",
                            "is_compatible", "entry")

    def __init__(self, api_key, url="http://www.materialsproject.org:8080/rest"):
        """
        Args:
            api_key:
                A String API key for accessing the MaterialsProject REST
                interface. Please apply on the Materials Project website for
                one.
        """
        self.url = url
        self.api_key = api_key

    def get_data(self, chemsys_formula_id, prop=""):
        """
        Flexible method to get any data using the Materials Project REST
        interface. Generally used by other methods for more specific queries.
        
        Format of REST return is *always* a list of dict (regardless of the
        number of pieces of data returned. The general format is as follows:
        
        [{'material_id': material_id, 'property_name' : value}, ...]
        
        Args:
            chemsys_formula_id:
                A chemical system (e.g., Li-Fe-O), or formula (e.g., Fe2O3) or 
                materials_id (e.g., 1234).
            prop:
                Property to be obtained. Should be one of the
                MPRestAdaptor.supported_properties. Leave as empty string for a
                general list of useful properties.
        """
        url = "{}/{}/vasp/{}".format(self.url, chemsys_formula_id, prop)
        req = urllib2.Request(url, headers={"API_KEY":self.api_key})
        try:
            response = urllib2.urlopen(req)
            data = json.loads(response.read(), cls=PMGJSONDecoder)
            if data['valid_response']:
                return data['response']
        except urllib2.HTTPError as ex:
            data = json.loads(ex.read(), cls=PMGJSONDecoder)
            raise MPRestError(data['error'])

    def get_structure_by_material_id(self, material_id, final=True):
        """
        Get a Structure corresponding to a material_id.
        
        Args:
            material_id:
                Materials Project material_id (an int).
            final:
                Whether to get the final structure, or the initial
                (pre-relaxation) structure. Defaults to True.
        
        Returns:
            Structure object.
        """
        prop = "final_structure" if final else "initial_structure"
        data = self.get_data(material_id, prop=prop)
        return data[0][prop]

    def get_entry_by_material_id(self, material_id):
        """
        Get a ComputedEntry corresponding to a material_id.
        
        Args:
            material_id:
                Materials Project material_id (an int).
        
        Returns:
            ComputedEntry object.
        """
        data = self.get_data(material_id, prop="entry")
        return data[0]["entry"]

    def get_dos_by_material_id(self, material_id):
        """
        Get a ComputedEntry corresponding to a material_id.
        
        Args:
            material_id:
                Materials Project material_id (an int).
        
        Returns:
            A Dos object.
        """
        data = self.get_data(material_id, prop="dos")
        return data[0]["dos"]

    def get_bandstructure_by_material_id(self, material_id):
        """
        Get a ComputedEntry corresponding to a material_id.
        
        Args:
            material_id:
                Materials Project material_id (an int).
        
        Returns:
            A Bandstructure object.
        """
        data = self.get_data(material_id, prop="bandstructure")
        return data[0]["bandstructure"]

    def get_entries_in_chemsys(self, elements, compatible_only=True):
        """
        Get a list of ComputedEntries in a chemical system. For example,
        elements = ["Li", "Fe", "O"] will return a list of all entries in the
        Li-Fe-O chemical system, i.e., all LixOy, FexOy, LixFey, LixFeyOz, Li,
        Fe and O phases. Extremely useful for creating phase diagrams of entire
        chemical systems.
         
        Args:
            elements:
                List of element symbols, e.g., ["Li", "Fe", "O"].
        
        Returns:
            List of ComputedEntries.
        """
        data = self.get_data("-".join(elements), prop="entry")
        entries = [d['entry'] for d in data]
        if compatible_only:
            entries = MaterialsProjectCompatibility().process_entries(entries)
        return entries

    def get_exp_data(self, formula):
        """
        Get a list of ThermoData objects associated with a formula using the
        Materials Project REST interface.
        
        Args:
            formula:
                A formula to search for.
        
        Returns:
            List of ThermoData objects.
        """
        url = "{}/{}/exp?API_KEY={}".format(self.url, formula, self.api_key)
        req = urllib2.Request(url)
        response = urllib2.urlopen(req)
        data = response.read()
        data = json.loads(data, cls=PMGJSONDecoder)
        if data['valid_response']:
            return data['response']
        else:
            raise MPRestError(data['error'])

    def mpquery(self, criteria, properties):
        """
        Performs an advanced mpquery, which is a Mongo-like syntax for directly
        querying the Materials Project database via the mpquery rest interface.
        Please refer to the Moogle advanced help on the mpquery language and
        supported criteria and properties. Essentially, any supported properties
        within MPRestAdaptor should be supported in mpquery.
        
        Mpquery allows an advanced developer to perform queries which are
        otherwise too cumbersome to perform using the standard convenience
        methods.
        
        Args:
            criteria:
                Criteria of the query as a mongo-style dict. For example, 
                {'elements':{'$in':['Li', 'Na', 'K'], '$all': ['O']},
                'nelements':2} selects all Li, Na and K oxides
            properties:
                Properties to request for as a list. For example,
                ['formula', 'formation_energy_per_atom'] returns the formula
                and formation energy per atom.
        
        Returns:
            List of dict of data.
        """
        params = urllib.urlencode({'criteria': criteria, 'properties': properties, 'API_KEY':self.api_key})
        req = urllib2.Request("{}/mpquery".format(self.url), params)
        response = urllib2.urlopen(req)
        data = response.read()
        data = json.loads(data)
        return data


class MPRestError(Exception):
    '''
    Exception class for MPRestAdaptor.
    Raised when the query has problems, e.g., bad query format.
    '''

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "MPRestError Error : " + self.msg
