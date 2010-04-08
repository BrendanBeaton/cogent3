#!/usr/bin/env python
"""
This file defines a class for controlling the scope and heterogeneity of
parameters involved in a maximum-likelihood based tree analysis.
"""

from __future__ import with_statement
from cogent.core.tree import TreeError
from cogent.evolve import likelihood_calculation
from cogent.align import dp_calculation
from cogent.evolve.likelihood_function import LikelihoodFunction as _LF
from cogent.recalculation.scope import _indexed

import numpy
import pickle

from cogent.align.pairwise import AlignableSeq

__author__ = "Andrew Butterfield"
__copyright__ = "Copyright 2007-2009, The Cogent Project"
__credits__ = ["Andrew Butterfield", "Peter Maxwell", "Gavin Huttley",
                    "Helen Lindsay"]
__license__ = "GPL"
__version__ = "1.4.1"
__maintainer__ = "Gavin Huttley"
__email__ = "gavin.huttley@anu.ed.au"
__status__ = "Production"

def _category_names(dimension, specified):
    if type(specified) is int:
        cats = ['%s%s' % (dimension, i) for i in range(specified)]
    else:
        cats = tuple(specified)
    assert len(cats) >= 1, cats
    assert len(set(cats)) == len(cats), ("%s names must be unique" % dimension)
    return list(cats)

def load(filename):
    # first cut at saving pc's
    f = open(filename, 'rb')
    (version, info, pc) = pickle.load(f)
    assert version < 2.0, version
    pc.updateIntermediateValues()
    return pc

class _LikelihoodParameterController(_LF):
    """A ParameterController works by setting parameter rules. For each
    parameter in the model the edges of the tree are be partitioned into groups
    that share one value.
    
    For usage see the setParamRule method.
    """
    # Basically wrapper around the more generic recalulation.ParameterController
    # class, which doesn't know about trees.
    
    def __init__(self, model, tree, bins=1, loci=1,
            optimise_motif_probs=False, motif_probs_from_align=False, **kw):
        self.model = self._model = model
        self.tree = self._tree = tree
        self.seq_names = tree.getTipNames()
        self.locus_names  = _category_names('locus', loci)
        self.bin_names  = _category_names('bin', bins)
        self.posn_names = [str(i) for i in range(model.getWordLength())]
        self.motifs = self._motifs = model.getMotifs()
        self._mprob_motifs = list(model.getMprobAlphabet())
        defn = self.makeLikelihoodDefn(**kw)
        self.real_par_controller = defn.makeParamController()
        self.setDefaultParamRules()
        self.setDefaultTreeParameterRules()
        self.mprobs_from_alignment = motif_probs_from_align
        self.optimise_motif_probs = optimise_motif_probs
        self._name = ''
        self._format = {}
    
    def save(self, filename):
        f = open(filename, 'w')
        temp = {}
        try:
            for d in self.real_par_controller.defns:
                temp[id(d)] = d.values
                del d.values
            pickle.dump((1.0, None, self), f)
        finally:
            for d in self.real_par_controller.defns:
                if id(d) in temp:
                    d.values = temp[id(d)]
    
    def updateIntermediateValues(self):
        self.real_par_controller.update()
    
    def optimise(self, *args, **kw):
        return_calculator = kw.pop('return_calculator', False)
        lc = self.real_par_controller.makeCalculator()
        lc.optimise(*args, **kw)
        self.real_par_controller.updateFromCalculator(lc)
        if return_calculator:
            return lc
    
    def graphviz(self, **kw):
        lc = self.real_par_controller.makeCalculator()
        return lc.graphviz(**kw)
    
    def __repr__(self):
        return repr(self.real_par_controller)
    
    def setDefaultTreeParameterRules(self):
        """Lengths are set to the values found in the tree (if any), and
        free to be optimised independently.
        Other parameters are scoped based on the unique values found in the
        tree (if any) or default to having one value shared across the whole
        tree""" 
        with self.real_par_controller.updatesPostponed():
            edges = self.tree.getEdgeVector()
            for par_name in self.model.getParamList():
                try:
                    values = dict([(edge.Name, edge.params[par_name])
                            for edge in edges if not edge.isroot()])
                    (uniq, index) = _indexed(values)
                except KeyError:
                    continue  # new parameter
                for (u, value) in enumerate(uniq):
                    group = [edge for (edge, i) in index.items() if i==u]
                    self.setParamRule(par_name, edges=group, init=value)
            for edge in edges:
                if edge.Length is not None:
                    self.setParamRule('length', edge=edge.Name, init=edge.Length)
    
    def setMotifProbsFromData(self, align, locus=None, is_const=None, 
                include_ambiguity=False, is_independent=None, auto=False,
                pseudocount=None):
        counts = self.model.countMotifs(align, 
                include_ambiguity=include_ambiguity)
        if is_const is None:
            is_const = not self.optimise_motif_probs
        if pseudocount is None:
            if is_const:
                pseudocount = 0.0
            else:
                pseudocount = 0.5
        counts += pseudocount
        mprobs = counts/(1.0*sum(counts))
        self.setMotifProbs(mprobs, locus=locus, is_const=is_const, 
                is_independent=is_independent, auto=auto)
    
    def setMotifProbs(self, motif_probs, locus=None, bin=None, is_const=None, 
                is_independent=None, auto=False):
        motif_probs = self.model.adaptMotifProbs(motif_probs, auto=auto)
        if is_const is None:
            is_const = not self.optimise_motif_probs
        self.model.setParamControllerMotifProbs(self, motif_probs, 
            is_const=is_const, bin=bin, locus=locus, 
            is_independent=is_independent)
        if not auto:
            self.mprobs_from_alignment = False  # should be done per-locus
    
    def setExpm(self, expm):
        assert expm in ['pade', 'either', 'eigen', 'checked'], expm
        self.setParamRule('expm', is_const=True, value=expm)

    def makeCalculator(self, aligns):
        # deprecate
        self.setAlignment(aligns)
        if getattr(self, 'used_as_calculator', False):
            warnings.warn('PC used as two different calculators', stacklevel=2)
        self.used_as_calculator = True
        return self
    
    def _process_scope_info(self, edge=None, tip_names=None, edges=None,
            is_clade=None, is_stem=None, outgroup_name=None):
        """From information specifying the scope of a parameter derive a list of
         edge names"""
        
        if edges is not None:
            if tip_names or edge:
                raise TreeError("Only ONE of edge, edges or tip_names")
        elif edge is not None:
            if tip_names:
                raise TreeError("Only ONE of edge, edges or tip_names")
            edges = [edge]
        elif tip_names is None:
            edges = None # meaning all edges
        elif len(tip_names) != 2:
            raise TreeError("tip_names must contain 2 species")
        else:
            (species1, species2) = tip_names
            if is_stem is None:
                is_stem = False
            if is_clade is None:
                is_clade = not is_stem
            edges = self.tree.getEdgeNames(species1, species2,
                getstem=is_stem, getclade=is_clade, outgroup_name=outgroup_name)
        
        return edges
    
    def setParamRule(self, par_name, is_independent=None, is_const=False,
            value=None, lower=None, init=None, upper=None, **scope_info):
        """Define a model constraint for par_name. Parameters can be set
        constant or split according to tree/bin scopes.
        
        Arguments:
            - par_name: The model parameter being modified.
            - is_const, value: if True, the parameter is held constant at
              value, if provided, or the likelihood functions current value.
            - is_independent: whether the partition specified by scope/bin
              arguments are to be considered independent.
            - lower, init, upper: specify the lower bound, initial value and
              upper bound for optimisation. Can be set separately.
            - bin, bins: the name(s) of the bin to apply rule.
            - locus, loci: the name of the locus/loci to apply rule.
            - **scope_info: tree scope arguments
              
              - edge, edges: The name of the tree edge(s) affected by rule. ??
              - tip_names: a tuple of two tip names, specifying a tree scope
                to apply rule.
              - outgroup_name: A tip name that, provided along with tip_names,
                ensures a consistently specified tree scope.
              - is_clade: The rule applies to all edges descending from the most
                recent common ancestor defined by the tip_names+outgroup_name
                arguments.
              - is_stem: The rule applies to the edge preceding the most recent
                common ancestor defined by the tip_names+outgroup_name
                arguments.
        """
        par_name = str(par_name)
                
        scopes = {}
        for (single, plural) in [
                ('bin', 'bins'),
                ('locus', 'loci'),
                ('position', 'positions'),
                ('motif', 'motifs'),
                ]:
            if single in scope_info:
                v = scope_info.pop(single)
                if v:
                    assert isinstance(v, basestring), ('%s=, maybe?' % plural)
                    assert plural not in scope_info
                    scopes[single] = [v]
            elif plural in scope_info:
                v = scope_info.pop(plural)
                if v:
                    scopes[single] = v
                
        edges = self._process_scope_info(**scope_info)
        if edges:
            scopes['edge'] = edges
        
        if is_const:
            assert not (init or lower or upper)
        elif init is not None:
            assert not value
            value = init
        self.real_par_controller.assignAll(par_name, scopes, value, lower,
                upper, is_const, is_independent)
    
    def setLocalClock(self, tip1name, tip2name):
        """Constrain branch lengths for tip1name and tip2name to be equal.
        This is a molecular clock condition. Currently only valid for tips
        connected to the same node.
        
        Note: This is just a convenient interface to setParameterRule.
        """
        self.setParamRule("length", tip_names = [tip1name, tip2name],
                                is_clade = 1, is_independent = 0)
    
    def setConstantLengths(self, tree=None, exclude_list=[]):
        """Constrains edge lengths to those in the tree.
        
        Arguments:
            - tree: must have the same topology as the current model.
              If not provided, the current tree length's are used.
            - exclude_list: a list of edge names whose branch lengths
              will be constrained.
        """
        if tree is None:
            tree = self.tree
        
        with self.real_par_controller.updatesPostponed():
            for edge in tree.getEdgeVector():
                if edge.Length is None or edge.Name in exclude_list:
                    continue
                self.setParamRule("length", edge=edge.Name, is_const=1,
                                        value=edge.Length)
    

class AlignmentLikelihoodFunction(_LikelihoodParameterController):
    
    def setDefaultParamRules(self):
        try:
            self.real_par_controller.assignAll(
                'fixed_motif', None, value=-1, const=True, independent=True)
        except KeyError:
            pass
    
    def makeLikelihoodDefn(self, sites_independent=True):
        defns = self.model.makeParamControllerDefns(
                bin_names=self.bin_names)
        return likelihood_calculation.makeTotalLogLikelihoodDefn(
            self.tree, defns['align'], defns['psubs'], defns['word_probs'],
            defns['bprobs'], self.bin_names, self.locus_names,
            sites_independent)
    
    def setAlignment(self, aligns, motif_pseudocount=None):
        """set the alignment to be used for computing the likelihood."""
        if type(aligns) is not list:
            aligns = [aligns]
        assert len(aligns) == len(self.locus_names), len(aligns)
        tip_names = set(self.tree.getTipNames())
        for index, aln in enumerate(aligns):
            if len(aligns) > 1:
                locus_name = "for locus '%s'" % self.locus_names[index]
            else:
                locus_name = ""
            assert not set(aln.getSeqNames()).symmetric_difference(tip_names),\
                "Tree tip names %s and aln seq names %s don't match %s" % \
                                (self.tree.getTipNames(), aln.getSeqNames(),
                                locus_name)
            assert not "root" in aln.getSeqNames(), "'root' is a reserved name."
        with self.real_par_controller.updatesPostponed():
            for (locus_name, align) in zip(self.locus_names, aligns):
                self.real_par_controller.assignAll(
                        'alignment', {'locus':[locus_name]},
                        value=align, const=True)
                if self.mprobs_from_alignment:
                    self.setMotifProbsFromData(align, locus=locus_name, auto=True,
                            pseudocount=motif_pseudocount)
    

class SequenceLikelihoodFunction(_LikelihoodParameterController):
    def setDefaultParamRules(self):
        pass
    
    def makeLikelihoodDefn(self, sites_independent=None,
            with_indel_params=True, kn=True):
        assert sites_independent is None or not sites_independent
        assert len(self.locus_names) == 1
        return dp_calculation.makeForwardTreeDefn(
                self.model, self.tree, self.bin_names,
                with_indel_params=with_indel_params, kn=kn)
    
    def setSequences(self, seqs, locus=None):
        leaves = {}
        for (name, seq) in seqs.items():
            # if has uniq, probably already a likelihood tree leaf obj already
            if hasattr(seq, 'uniq'):
                leaf = seq # XXX more checks - same alphabet as model, name etc ...
            else:
                leaf = self.model.convertSequence(seq, name)
            leaf = AlignableSeq(leaf)
            leaves[name] = leaf
            assert name != "root", "'root' is a reserved name."
        self.setPogs(leaves, locus=locus)
    
    def setPogs(self, leaves, locus=None):
        with self.real_par_controller.updatesPostponed():
            for (name, pog) in leaves.items():
                self.setParamRule('leaf', edge=name, value=pog, is_const=True)
            if self.mprobs_from_alignment:
                counts = numpy.sum([pog.leaf.getMotifCounts()
                    for pog in leaves.values()], 0)
                mprobs = counts/(1.0*sum(counts))
                self.setMotifProbs(mprobs, locus=locus, is_const=True, auto=True)
    
