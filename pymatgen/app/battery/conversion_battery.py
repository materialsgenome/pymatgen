#!/usr/bin/env python

'''
Created on Feb 1, 2012
'''

from __future__ import division

__author__ = "Shyue Ping Ong"
__copyright__ = "Copyright 2012, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Shyue Ping Ong"
__email__ = "shyue@mit.edu"
__date__ = "Feb 1, 2012"

from pymatgen.core.periodic_table import Element
from pymatgen.core.physical_constants import ELECTRON_TO_AMPERE_HOURS
from pymatgen.analysis.reaction_calculator import BalancedReaction
from pymatgen.core.structure import Composition

from pymatgen.app.battery.battery_abc import AbstractElectrode, AbstractVoltagePair, composition_to_multi_dict
from pymatgen.phasediagram.pdmaker import PhaseDiagram
from pymatgen.phasediagram.pdanalyzer import PDAnalyzer


class ConversionElectrode(AbstractElectrode):

    def __init__(self, element_profile, entry_ion, initial_comp):
        self._composition = initial_comp
        self._entry_ion = entry_ion
        self._working_ion = self._entry_ion.composition.elements[0].symbol
        normalization_els = {}
        for el, amt in self._composition.items():
            if el != Element(self._working_ion):
                normalization_els[el] = amt
        self._vpairs = [ConversionVoltagePair(element_profile[i], element_profile[i + 1], normalization_els) for i in xrange(len(element_profile) - 1)]
        self._el_profile = element_profile
        self._vpairs = tuple(self._vpairs)

    @staticmethod
    def from_composition_and_pd(comp, pd, working_ion_symbol="Li"):
        working_ion = Element(working_ion_symbol)
        entry = None
        entry_ion = None
        for e in pd.stable_entries:
            if e.composition.reduced_formula == comp.reduced_formula:
                entry = e
            elif e.is_element and e.composition.reduced_formula == working_ion_symbol:
                entry_ion = e

        if not entry:
            raise ValueError("Not stable compound found at composition {}.".format(comp))

        analyzer = PDAnalyzer(pd)

        profile = analyzer.get_element_profile(working_ion, comp)
        profile.reverse() #Need to reverse because voltage goes form most charged to most discharged
        if len(profile) < 2:
            return None
        return ConversionElectrode(profile, entry_ion, comp)

    @staticmethod
    def from_composition_and_entries(comp, entries_in_chemsys, working_ion_symbol="Li"):
        pd = PhaseDiagram(entries_in_chemsys)
        return ConversionElectrode.from_composition_and_pd(comp, pd, working_ion_symbol)

    def sub_electrodes(self, adjacent_only=True, include_myself=True):
        '''
        If this electrode contains multiple voltage steps, then it is possible
        to use only a subset of the voltage steps to define other electrodes.
        For example, an LiTiO2 electrode might contain three subelectrodes:
        [LiTiO2 --> TiO2, LiTiO2 --> Li0.5TiO2, Li0.5TiO2 --> TiO2]
        This method can be used to return all the subelectrodes with some
        options
        
        Args:
            adjacent_only:
                Only return electrodes from compounds that are adjacent on the
                convex hull, i.e. no electrodes returned will have multiple
                voltage steps if this is set true
            include_myself:
                Include this identical electrode in the list of results
        
        Returns:
            A list of ConversionElectrode objects
        '''

        if adjacent_only:
            return [ConversionElectrode(self._el_profile[i:i + 2], self._entry_ion, self._composition) for i in xrange(len(self._el_profile) - 1)]

        sub_electrodes = []
        for i in xrange(len(self._el_profile) - 1):
            for j in xrange(i + 1, len(self._el_profile)):
                sub_electrodes.append(ConversionElectrode(self._el_profile[i:j + 1], self._entry_ion, self._composition))

        return sub_electrodes

    @property
    def composition(self):
        return self._composition

    @property
    def working_ion(self):
        '''
        The working ion as an Element object
        '''
        return self._entry_ion.composition.elements[0]

    @property
    def entry_ion(self):
        return self._entry_ion

    @property
    def voltage_pairs(self):
        return self._vpairs

    def is_super_electrode(self, conversion_electrode):
        for pair1 in conversion_electrode:
            found = False
            rxn1 = pair1.rxn
            all_formulas1 = set([rxn1.all_comp[i].reduced_formula for i in xrange(len(rxn1.all_comp)) if abs(rxn1.coeffs[i]) > 1e-5 ])
            for pair2 in self:
                rxn2 = pair2.rxn
                all_formulas2 = set([rxn2.all_comp[i].reduced_formula for i in xrange(len(rxn2.all_comp)) if abs(rxn2.coeffs[i]) > 1e-5 ])
                if all_formulas1 == all_formulas2:
                    found = True
                    break
            if not found:
                return False
        return True

    def is_same_electrode(self, conversion_electrode):

        if len(self) != len(conversion_electrode):
            return False

        for pair1 in conversion_electrode:
            found = False
            rxn1 = pair1.rxn
            all_formulas1 = set([rxn1.all_comp[i].reduced_formula for i in xrange(len(rxn1.all_comp)) if abs(rxn1.coeffs[i]) > 1e-5 ])
            for pair2 in self:
                rxn2 = pair2.rxn
                all_formulas2 = set([rxn2.all_comp[i].reduced_formula for i in xrange(len(rxn2.all_comp)) if abs(rxn2.coeffs[i]) > 1e-5 ])
                if all_formulas1 == all_formulas2:
                    found = True
                    break
            if not found:
                return False
        return True

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        output = ['Conversion electrode with formula {} and nsteps {}'.format(self._composition.reduced_formula, self.num_steps)]
        output.append('Average voltage {} V, min voltage {} V, max voltage {} V'.format(self.average_voltage(), self.min_voltage, self.max_voltage))
        output.append('Capacity (grav.) {} mAh/g, capacity (vol.) {} Ah/l'.format(self.capacity_grav(), self.capacity_vol()))
        output.append('Specific energy {} Wh/kg, energy density {} Wh/l'.format(self.specific_energy(), self.energy_density()))
        return "\n".join(output)


class ConversionVoltagePair(AbstractVoltagePair):

    def __init__(self, step1, step2, normalization_els):

        self._entry_ion = step1['element_reference']
        working_ion = self._entry_ion.composition.elements[0].symbol
        self._voltage = -step1['chempot'] + self._entry_ion.energy_per_atom
        self._mAh = (step2['evolution'] - step1['evolution']) * ELECTRON_TO_AMPERE_HOURS * 1000
        self._vol_charge = 0
        self._vol_discharge = 0
        licomp = Composition.from_formula(working_ion)
        prev_rxn = step1['reaction']
        reactants = {comp:abs(prev_rxn.get_coeff(comp)) for comp in prev_rxn.products if comp != licomp}
        curr_rxn = step2['reaction']
        products = {comp:abs(curr_rxn.get_coeff(comp)) for comp in curr_rxn.products if comp != licomp}
        reactants[licomp] = (step2['evolution'] - step1['evolution'])

        rxn = BalancedReaction(reactants, products)

        for el, amt in normalization_els.items():
            if rxn.get_el_amount(el) != 0:
                rxn.normalize_to_element(el, amt)
                break

        prev_mass_discharge = sum([prev_rxn.all_comp[i].weight * abs(prev_rxn.coeffs[i]) for i in xrange(len(prev_rxn.all_comp))]) / 2
        self._vol_charge = sum([abs(prev_rxn.get_coeff(e.composition)) * e.structure.volume for e in step1['entries'] if e.composition.reduced_formula != working_ion])
        mass_discharge = sum([curr_rxn.all_comp[i].weight * abs(curr_rxn.coeffs[i]) for i in xrange(len(curr_rxn.all_comp))]) / 2
        self._mass_charge = prev_mass_discharge
        self._mass_discharge = mass_discharge
        self._vol_discharge = sum([abs(curr_rxn.get_coeff(e.composition)) * e.structure.volume for e in step2['entries'] if e.composition.reduced_formula != working_ion])

        totalcomp = Composition({})
        for comp in prev_rxn.products:
            if comp.reduced_formula != working_ion:
                totalcomp += comp * abs(prev_rxn.get_coeff(comp))
        self._frac_charge = totalcomp.get_atomic_fraction(Element(working_ion))

        totalcomp = Composition({})
        for comp in curr_rxn.products:
            if comp.reduced_formula != working_ion:
                totalcomp += comp * abs(curr_rxn.get_coeff(comp))
        self._frac_discharge = totalcomp.get_atomic_fraction(Element(working_ion))

        self._rxn = rxn
        self._working_ion = working_ion
        self._entries_charge = step2['entries']
        self._entries_discharge = step1['entries']

    @property
    def working_ion(self):
        return self._working_ion

    @property
    def entries_charge(self):
        return self._entries_charge

    @property
    def entries_discharge(self):
        return self._entries_discharge

    @property
    def frac_charge(self):
        return self._frac_charge

    @property
    def frac_discharge(self):
        return self._frac_discharge

    @property
    def rxn(self):
        return self._rxn

    @property
    def voltage(self):
        return self._voltage

    @property
    def mAh(self):
        return self._mAh

    @property
    def mass_charge(self):
        return self._mass_charge

    @property
    def mass_discharge(self):
        return self._mass_discharge

    @property
    def vol_charge(self):
        return self._vol_charge

    @property
    def vol_discharge(self):
        return self._vol_discharge

    @property
    def entry_ion(self):
        return self._entry_ion

    def __repr__(self):
        output = ["Conversion voltage pair with working ion {}".format(self._entry_ion.composition.reduced_formula)]
        output.append("Reaction : {}".format(self._rxn))
        output.append("V = {}, mAh = {}".format(self.voltage, self.mAh))
        output.append("mass_charge = {}, mass_discharge = {}".format(self.mass_charge, self.mass_discharge))
        output.append("vol_charge = {}, vol_discharge = {}".format(self.vol_charge, self.vol_discharge))
        return "\n".join(output)
