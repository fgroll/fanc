'''
Created on May 12, 2015

@author: kkruse1
'''

from __future__ import division

import numpy as np
np.seterr(all='warn')
import warnings
import kaic.genome.genomeTools as gt
from hiclib import highResBinnedData
from kaic.tools.hic import getChromosomeMatrix 
from kaic.tools.matrix import removeSparseRows, restoreSparseRows

import logging
logger = logging.getLogger('matrix_balancing')
logger.setLevel(logging.DEBUG)

def correct(hicFile,genome,resolution,output=None,perChromosome=False):
    genome_db = gt.loadGenomeObject(genome)
    hic = highResBinnedData.HiResHiC(genome_db,resolution)
    hic.loadData(hicFile)
    
    if perChromosome:
        hic.biases = {}
        for chrm in genome_db.label2idx:
            M = getChromosomeMatrix(hic,genome,chrm)
            x = getBiasVector(M)
            hic.biases[chrm] = x
            Mn = x*M*x
            hic.data[(chrm,chrm)].setData(Mn)
    else:
        M = hic.getCombinedMatrix(force=True)
                
        hasErrors = True
        iterations = 0
        removed_rows = []
        while hasErrors or iterations > 50:
            hasErrors = False
            
            try:
                x = getBiasVector(M)
            except ValueError:
                logger.info("Matrix balancing failed (this can happen!)",
                            " removing sparsest rows to try again")
                M, ixs = removeSparseRows(M)
                removed_rows.append(ixs)
                hasErrors=True
            
            iterations += 1
        
        Mn = x*M*x
        
        # restore zero rows
        for idx in reversed(removed_rows):
            Mn = restoreSparseRows(Mn, idx)
        
        hic.biases = x
        
        # save back to original
        for chr1, chr2 in hic.data:
            beg1, end1 = hic.genome.chrmStartsBinCont[chr1], hic.genome.chrmEndsBinCont[chr1]
            beg2, end2 = hic.genome.chrmStartsBinCont[chr2], hic.genome.chrmEndsBinCont[chr2]
            hic.data[(chr1, chr2)].setData(Mn[beg1:end1, beg2:end2])
    
    if output:
        print "Saving to file %s" %output
        hic.export(output)

def getCorrectedMatrix(A,x0=None,tol=1e-06,delta=0.1,Delta=3,fl=0):
    x = getBiasVector(A, x0, tol, delta, Delta, fl)
    return x*A*x
    
    

def getBiasVector(A,x0=None,tol=1e-06,delta=0.1,Delta=3,fl=0):
    
    with warnings.catch_warnings():
        warnings.filterwarnings('error')
        
        # basic variables
        #n=size_(A,1)
        if not isinstance(A,np.ndarray):
            A = np.array(A)
        n = A.shape[0]
        #e=ones_(n,1)
        e = np.ones(n)
        if not x0:
            x0 = np.ones(n)
        res=np.array([])
        g=0.9
        etamax=0.1
        eta=etamax
        stop_tol=tol * 0.5
        x=x0.copy()
        rt=tol ** 2
        #v=x.dot((A * x))
        v=x*A.dot(x)
        rk=1 - v
        #rho_km1=rk.T * rk
        rho_km1=rk.T.dot(rk)
        rout=rho_km1
        rho_km2=rho_km1
        rold=rout
        MVP=0
        i=0
            
        
        if fl == 1:
            print "it    in. it    res\n"
        print "starting iterations\n"
        while rout > rt:
    
            i+=1
            k=0
            y=e.copy()
            innertol=max(eta ** 2 * rout, rt)
            while rho_km1 > innertol:
    
                k+=1
                if k == 1:
                    try:
                        Z=rk / v
                    except Warning:
                        raise ValueError("v=0; Remove zero or sparse rows")
                    p=Z.copy()
                    rho_km1=rk.T.dot(Z)
                else:
                    beta=rho_km1 / rho_km2
                    p=Z + beta * p
                #w = x.*(A*(x.*p)) + v.*p;
                w=x*A.dot(x*p) + v*p
                alpha=rho_km1 / p.T.dot(w)
                ap=alpha * p
                ynew=y + ap
                if min(ynew) <= delta:
                    if delta == 0:
                        break
                    ind=np.where(ap < 0)[0]
                    # gamma = min((delta  - y(ind))./ap(ind));
                    gamma=min((delta-y[ind])/ap[ind])
                    y=y + gamma * ap
                    break
                if max(ynew) >= Delta:
                    ind=np.where(ynew > Delta)[0]
                    gamma=min((Delta-y[ind])/ap[ind])
                    y=y + gamma * ap
                    break
                y=ynew.copy()
                rk=rk - alpha * w
                rho_km2=rho_km1.copy()
                Z=rk / v
                rho_km1=rk.T.dot(Z)
            
            x=x*y
            v=x*A.dot(x)
            rk=1 - v
            rho_km1=rk.T.dot(rk)
            rout=rho_km1.copy()
            MVP=MVP + k + 1
            rat=rout / rold
            rold=rout.copy()
            res_norm=np.sqrt(rout)
            eta_o=eta
            eta=g * rat
            if g * eta_o ** 2 > 0.1:
                eta=max(eta,g * eta_o ** 2)
            eta=max(min(eta,etamax),stop_tol / res_norm)
            if fl == 1:
                print "%d %d   %.3e %.3e %.3e \n" % (i,k,res_norm,min(y),min(x))
                res=np.array([[res],[res_norm]])
    
        print "Matrix-vector products = %d\n" % MVP
    return x
