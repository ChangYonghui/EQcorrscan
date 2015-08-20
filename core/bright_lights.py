#!/usr/bin/python
"""
Code to determine the birghtness function of seismic data according to a three-\
dimensional travel-time grid.  This travel-time grid should be generated using\
the grid2time function of the NonLinLoc package by Anthony Lomax which can be\
found here: http://alomax.free.fr/nlloc/ and is not distributed within this\
package as this is a very useful stand-alone library for seismic event location.

This code is based on the method of Frank & Shapiro 2014

Part of the EQcorrscan module to integrate seisan nordic files into a full\
cross-channel correlation for detection routine.\
EQcorrscan is a python module designed to run match filter routines for\
seismology, within it are routines for integration to seisan and obspy.\
With obspy integration (which is necessary) all main waveform formats can be\
read in and output.

This main section contains a script, LFE_search.py which demonstrates the usage\
of the built in functions from template generation from picked waveforms\
through detection by match filter of continuous data to the generation of lag\
times to be used for relative locations.

The match-filter routine described here was used a previous Matlab code for the\
Chamberlain et al. 2014 G-cubed publication.  The basis for the lag-time\
generation section is outlined in Hardebeck & Shelly 2011, GRL.\

Code generated by Calum John Chamberlain of Victoria University of Wellington,\
2015.


.. rubric:: Note
Pre-requisites:
    - gcc             - for the installation of the openCV correlation routine
    - python-cv2      - Python bindings for the openCV routines
    - python-joblib   - used for parallel processing
    - python-obspy    - used for lots of common seismological processing
                        - requires:
                            - numpy
                            - scipy
                            - matplotlib
    - NonLinLoc       - used outside of all codes for travel-time generation

Copyright 2015 Calum Chamberlain

This file is part of EQcorrscan.

    EQcorrscan is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    EQcorrscan is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with EQcorrscan.  If not, see <http://www.gnu.org/licenses/>.

"""
import numpy as np
def _read_tt(path, stations, phase, phaseout='S', ps_ratio=1.68):
    """
    Function to read in .csv files of slowness generated from Grid2Time (part
    of NonLinLoc by Anthony Lomax) and convert this to a useful format here.

    It should be noted that this can read either P or S travel-time grids, not
    both at the moment.

    :type path: str
    :param path: The path to the .csv Grid2Time outputs
    :type stations: list
    :param stations: List of station names to read slowness files for.
    :type phaseout: str
    :param phaseout: What phase to return the lagtimes in
    :type ps_ratio: float
    :param ps_ratio: p to s ratio for coversion

    :return: list stations, list of lists of tuples nodes, \
    :class: 'numpy.array' lags station[1] refers to nodes[1] and \
    lags[1] nodes[1][1] refers to station[1] and lags[1][1]\
    nodes[n][n] is a tuple of latitude, longitude and depth
    """

    import glob, sys, csv

    # Locate the slowness file information
    gridfiles=[]
    stations_out=[]
    for station in stations:
        gridfiles+=(glob.glob(path+'*.'+phase+'.'+station+'.time.csv'))
        if glob.glob(path+'*.'+phase+'.'+station+'*.csv'):
            stations_out+=[station]
    if not stations_out:
        print 'No slowness files found'
        sys.exit()
    # Read the files
    allnodes=[]
    for gridfile in gridfiles:
        print '     Reading slowness from: '+gridfile
        f=open(gridfile,'r')
        grid=csv.reader(f, delimiter=' ')
        traveltime=[]
        nodes=[]
        for row in grid:
            nodes.append((row[0],row[1],row[2]))
            traveltime.append(float(row[3]))
        traveltime=np.array(traveltime)
        if not phase == phaseout:
            if phase == 'S':
                traveltime=traveltime/1.68
            else:
                traveltime=traveltime*1.68
        lags=traveltime-min(traveltime)
        if not 'alllags' in locals():
            alllags=[lags]
        else:
            alllags=np.concatenate((alllags,[lags]), axis=0)
        allnodes=nodes  # each element of allnodes should be the same as the
                        # other one, e.g. for each station the grid must be the
                        # same, hence allnodes=nodes
        f.close()
    return stations_out, allnodes, alllags

def _resample_grid(stations, nodes, lags, mindepth, maxdepth, corners, resolution):
    """
    Function to resample the lagtime grid to a given volume.  For use if the
    grid from Grid2Time is too large or you want to run a faster, downsampled
    scan.

    :type stations: list
    :param stations: List of station names from in the form where stations[i]\
    refers to nodes[i][:] and lags[i][:]
    :type nodes: list, tuple
    :param nodes: List of node points where nodes[i] referes to stations[i] and\
    nodes[:][:][0] is latitude in degrees, nodes[:][:][1] is longitude in\
    degrees, nodes[:][:][2] is depth in km.
    :type lags: :class: 'numpy.array'
    :param lags: Array of arrays where lags[i][:] refers to stations[i].\
    lags[i][j] should be the delay to the nodes[i][j] for stations[i] in seconds\
    :type mindepth: float
    :param mindepth: Upper limit of volume
    :type maxdepth: float
    :param maxdepth: Lower limit of volume
    :type corners: matplotlib.Path
    :param corners: matplotlib path of the corners for the 2D polygon to cut to\
    in lat and long

    :return: list stations, list of lists of tuples nodes, :class: \
    'numpy.array' lags station[1] refers to nodes[1] and lags[1]\
    nodes[1][1] refers to station[1] and lags[1][1]\
    nodes[n][n] is a tuple of latitude, longitude and depth.
    """
    import sys
    resamp_nodes=[]
    resamp_lags=[]
    # Cut the volume
    for i in xrange(0,len(nodes)):
        # If the node is within the volume range, keep it
        if mindepth < float(nodes[i][2]) < maxdepth and\
           corners.contains_point(nodes[i][0:2]):
                resamp_nodes.append(nodes[i])
                resamp_lags.append([lags[:,i]])
    # Reshape the lags
    print np.shape(resamp_lags)
    resamp_lags=np.reshape(resamp_lags,(len(resamp_lags),len(stations))).T
    # Resample the nodes - they are sorted in order of size with largest long
    # then largest lat, then depth.
    print 'Grid now has '+str(len(resamp_nodes))+' nodes'
    return stations, resamp_nodes, resamp_lags

def _rm_similarlags(stations, nodes, lags, threshold):
    """
    Function to remove those nodes that have a very similar network moveout
    to another lag.

    Will, for each node, calculate the difference in lagtime at each station
    at every node, then sum these for each node to get a cumulative difference
    in network moveout.  This will result in an array of arrays with zeros on
    the diagonal.

    :type stations: list
    :param stations: List of station names from in the form where stations[i]\
    refers to nodes[i][:] and lags[i][:]
    :type nodes: list, tuple
    :param nodes: List of node points where nodes[i] referes to stations[i] and\
    nodes[:][:][0] is latitude in degrees, nodes[:][:][1] is longitude in\
    degrees, nodes[:][:][2] is depth in km.
    :type lags: :class: 'numpy.array'
    :param lags: Array of arrays where lags[i][:] refers to stations[i].\
    lags[i][j] should be the delay to the nodes[i][j] for stations[i] in seconds
    :type threhsold: float
    :param threshold: Threshold for removal in seconds

    :returns: list stations, list of lists of tuples nodes, :class: \
    'numpy.array' lags station[1] refers to nodes[1] and lags[1]\
    nodes[1][1] refers to station[1] and lags[1][1]\
    nodes[n][n] is a tuple of latitude, longitude and depth.
    """
    import sys
    netdif=abs((lags.T-lags.T[0]).sum(axis=1).reshape(1,len(nodes)))>threshold
    for i in xrange(len(nodes)):
        netdif=np.concatenate((netdif, \
                               abs((lags.T-lags.T[i]).sum(axis=1).reshape(1,len(nodes)))>threshold),\
                              axis=0)
        sys.stdout.write("\r"+str(float(i)/len(nodes)*100)+"% \r")
        sys.stdout.flush()
    nodes_out=[nodes[0]]
    node_indeces=[0]
    print "\n"
    print len(nodes)
    for i in xrange(1,len(nodes)):
        if np.all(netdif[i][node_indeces]):
            node_indeces.append(i)
            nodes_out.append(nodes[i])
    lags_out=lags.T[node_indeces].T
    print "Removed "+str(len(nodes)-len(nodes_out))+" duplicate nodes"
    return stations, nodes_out, lags_out


def _node_loop(stations, lags, stream, i=0, mem_issue=False, instance=0):
    """
    Internal function to allow for parallelisation of brightness

    :type stations: list
    :type lags: list
    :type stream: :class: `obspy.Stream`

    :return: (i, energy (np.array))
    """
    from par import bright_lights_par as brightdef
    import warnings
    for tr in stream:
        j = [k for k in xrange(len(stations)) if stations[k]==tr.stats.station]
        # Check that there is only one matching station
        if len(j)>1:
            warnings.warn('Too many stations')
            j=[j[0]]
        if len(j)==0:
            warnings.warn('No station match')
            continue
        lag=lags[j[0]]
        pad=np.zeros(int(round(lag*tr.stats.sampling_rate)))
        lagged_energy=np.square(np.concatenate((tr.data, pad)))[len(pad):]
        # Clip energy
        lagged_energy=np.clip(lagged_energy, 0, brightdef.clip_level*np.mean(lagged_energy))
        if not 'energy' in locals():
            energy=(lagged_energy/np.sqrt(np.mean(np.square(lagged_energy)))).reshape(1,len(lagged_energy))
        else:
            norm_energy=(lagged_energy/np.sqrt(np.mean(np.square(lagged_energy)))).reshape(1,len(lagged_energy))
            # Apply lag to data and add it to energy - normalize the data here
            energy=np.concatenate((energy,norm_energy), axis=0)
    energy=np.sum(energy, axis=0).reshape(1,len(lagged_energy))
    if not mem_issue:
        return (i, energy)
    else:
        np.save('tmp'+str(instance)+'/node_'+str(i), energy)
        return (i, 'tmp'+str(instance)+'/node_'+str(i))

def _cum_net_resp(node_lis, instance):
    """
    Function to compute the cumulative network response by reading the saved
    energy .npy files

    :type node_lis: np.ndarray
    :param node_lis: List of nodes (ints) to read from

    :returns: :class: np.ndarray cum_net_resp, list of indeces used
    """
    import os
    cum_net_resp=np.load('tmp'+str(instance)+'/node_'+str(node_lis[0])+'.npy')[0]
    os.remove('tmp'+str(instance)+'/node_'+str(node_lis[0])+'.npy')
    indeces=np.ones(len(cum_net_resp))*node_lis[0]
    for i in node_lis[1:]:
        node_energy=np.load('tmp'+str(instance)+'/node_'+str(i)+'.npy')[0]
        updated_indeces=np.argmax([cum_net_resp, node_energy], axis=0)
        temp=np.array([cum_net_resp, node_energy])
        cum_net_resp=np.array([temp[updated_indeces[j]][j] \
                               for j in xrange(len(updated_indeces))])
        del temp, node_energy
        updated_indeces[updated_indeces==1]=i
        indeces=updated_indeces
        os.remove('tmp'+str(instance)+'/node_'+str(i)+'.npy')
    return cum_net_resp, indeces



def _find_detections(cum_net_resp, nodes, threshold, thresh_type, samp_rate, realstations):
    """
    Function to find detections within the cumulative network response according
    to Frank et al. (2014).

    :type cum_net_resp: np.array
    :param cum_net_resp: Array of cumulative network response for nodes
    :type nodes: list of tuples
    :param nodes: Nodes associated with the source of energy in the cum_net_resp
    :type threshold: float
    :type thresh_type: str
    :type samp_rate: float
    :type realstations: list of str

    :return: detections as class DETECTION
    """
    from utils import findpeaks
    from par import template_gen_par as defaults
    from core.match_filter import DETECTION
    cum_net_resp = np.nan_to_num(cum_net_resp) # Force no NaNs
    if np.isnan(cum_net_resp).any():
        raise ValueError("Nans present")
    print 'Mean of data is: '+str(np.median(cum_net_resp))
    print 'RMS of data is: '+str(np.sqrt(np.mean(np.square(cum_net_resp))))
    print 'MAD of data is: '+str(np.median(np.abs(cum_net_resp)))
    if thresh_type=='MAD':
        thresh=(np.median(np.abs(cum_net_resp))*threshold) # Raise to the power
    elif thresh_type=='abs':
        thresh=threshold
    elif thresh_type=='RMS':
        thresh=(np.sqrt(np.mean(np.square(cum_net_resp))))*threshold
    print 'Threshold is set to: '+str(thresh)
    print 'Max of data is: '+str(max(cum_net_resp))
    peaks=findpeaks.find_peaks2(cum_net_resp, thresh,
                    defaults.length*samp_rate, debug=0)
    detections=[]
    if peaks:
        for peak in peaks:
            node=nodes[peak[1]]
            detections.append(DETECTION(node[0]+'_'+node[1]+'_'+node[2],
                                         peak[1]/samp_rate,
                                         len(realstations), peak[0], thresh,
                                         'brightness', realstations))
    else:
        detections=[]
    print 'I have found '+str(len(peaks))+' possible detections'
    return detections

def coherance(stream):
    """
    Function to determine the average network coherance of a given template or
    detection.  You will want your stream to contain only signal as noise
    will reduce the coherance (assuming it is incoherant random noise).

    :type stream: obspy.Stream
    :param stream: The stream of seismic data you want to calculate the
                    coherance for.

    :return: float - coherance
    """
    # First check that all channels in stream have data of the same length
    maxlen=np.max([len(tr.data) for tr in stream])
    for tr in stream:
        if not len(tr.data) == maxlen:
            warnings.warn(tr.statsstation+'.'+tr.stats.channel+\
                          ' is not the same length, padding')
            pad=np.zeros(maxlen-len(tr.data))
            if tr.stats.starttime.hour == 0:
                tr.data=np.concatenate(pad, tr.data)
            else:
                tr.data=np.concatenate(tr.data, pad)
    coherance=0.0
    from match_filter import normxcorr2
    # Loop through channels and generate a correlation value for each
    # unique cross-channel pairing
    for i in xrange(len(stream)):
        for j in xrange(i+1,len(stream)):
            coherance+=np.abs(normxcorr2(stream[i].data, stream[j].data))[0][0]
    coherance=2*coherance/(len(stream)*(len(stream)-1))
    return coherance

def brightness(stations, nodes, lags, stream, threshold, thresh_type,
        coherance_thresh, instance=0):
    """
    Function to calculate the brightness function in terms of energy for a day
    of data over the entire network for a given grid of nodes.

    Note data in stream must be all of the same length and have the same
    sampling rates.

    :type stations: list
    :param stations: List of station names from in the form where stations[i]\
    refers to nodes[i][:] and lags[i][:]
    :type nodes: list, tuple
    :param nodes: List of node points where nodes[i] referes to stations[i] and\
    nodes[:][:][0] is latitude in degrees, nodes[:][:][1] is longitude in\
    degrees, nodes[:][:][2] is depth in km.
    :type lags: :class: 'numpy.array'
    :param lags: Array of arrays where lags[i][:] refers to stations[i].\
    lags[i][j] should be the delay to the nodes[i][j] for stations[i] in seconds.
    :type stream: :class: `obspy.Stream`
    :param data: Data through which to look for detections.
    :type threshold: float
    :param threshold: Threshold value for detection of template within the\
    brightness function
    :type thresh_type: str
    :param thresh_type: Either MAD or abs where MAD is the Median Absolute\
    Deviation and abs is an absoulte brightness.
    :type coherance_thresh: float
    :param coherance_thresh: Threshold for removing incoherant peaks in the\
            network response, those below this will not be used as templates.

    :return: list of templates as :class: `obspy.Stream` objects
    """
    from core.template_gen import _template_gen
    from par import template_gen_par as defaults
    from par import match_filter_par as matchdef
    from par import bright_lights_par as brightdef
    if brightdef.plotsave:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.ioff()
    # from joblib import Parallel, delayed
    from multiprocessing import Pool, cpu_count
    from utils.Sfile_util import PICK
    import sys, os
    from copy import deepcopy
    from obspy import read as obsread, Stream
    import matplotlib.pyplot as plt
    # Check that we actually have the correct stations
    realstations=[]
    for station in stations:
        st=stream.select(station=station)
        if st:
            realstations+=station
    del st
    # Convert the data to float 16 to reduce memory consumption, shouldn't be
    # too detrimental
    stream_copy=stream.copy()
    for i in xrange(len(stream)):
        stream[i].data=stream[i].data.astype(np.float16)
    detections=[]
    detect_lags=[]
    parallel=True
    plotvar=True
    mem_issue=True
    # Loop through each node in the input
    # Linear run
    print 'Computing the energy stacks'
    if not parallel:
        for i in xrange(0,len(nodes)):
            print i
            if not mem_issue:
                energy[i], j=_node_loop(stations, lags[:,i], stream)
            else:
                j, filename=_node_loop(stations, lags[:,i], stream, i, mem_issue)
    else:
        # Parallel run
        num_cores=brightdef.cores
        if num_cores > len(nodes):
            num_cores=len(nodes)
        if num_cores > cpu_count():
            num_cores=cpu_count()
        pool=Pool(processes=num_cores, maxtasksperchild=None)
        results=[pool.apply_async(_node_loop, args=(stations,\
                                                    lags[:,i], stream, i,\
                                                    mem_issue, instance))\
                                  for i in xrange(len(nodes))]
        pool.close()
        if not mem_issue:
            print 'Computing the cumulative network response from memory'
            energy=[p.get() for p in results]
            pool.join()
            energy.sort(key=lambda tup: tup[0])
            energy = [node[1] for node in energy]
            energy=np.concatenate(energy, axis=0)
            print energy.shape
        else:
            pool.join()
    # Now compute the cumulative network response and then detect possible events
    if not mem_issue:
        indeces=np.argmax(energy, axis=0) # Indeces of maximum energy
        cum_net_resp=np.array([np.nan]*len(indeces))
        cum_net_resp[0]=energy[indeces[0]][0]
        peak_nodes=[nodes[indeces[0]]]
        for i in xrange(1, len(indeces)):
            cum_net_resp[i]=energy[indeces[i]][i]
            peak_nodes.append(nodes[indeces[i]])
        del energy, indeces
    else:
        print 'Reading the temp files and computing network response'
        node_splits=len(nodes)/num_cores
        indeces=[range(node_splits)]
        for i in xrange(1,num_cores-1):
            indeces.append(range(node_splits*i, node_splits*(i+1)))
        indeces.append(range(node_splits*(i+1), len(nodes)))
        pool=Pool(processes=num_cores, maxtasksperchild=None)
        results=[pool.apply_async(_cum_net_resp, args=(indeces[i], instance))\
                                  for i in xrange(num_cores)]
        pool.close()
        results=[p.get() for p in results]
        pool.join()
        responses=[result[0] for result in results]
        print np.shape(responses)
        node_indeces=[result[1] for result in results]
        cum_net_resp=np.array(responses)
        indeces=np.argmax(cum_net_resp, axis=0)
        print indeces.shape
        print cum_net_resp.shape
        cum_net_resp=np.array([cum_net_resp[indeces[j]][j]\
                               for j in xrange(len(indeces))])
        peak_nodes=[nodes[node_indeces[indeces[i]][i]] \
                          for i in xrange(len(indeces))]
        del indeces, node_indeces
    if plotvar:
        cum_net_trace=deepcopy(stream[0])
        cum_net_trace.data=cum_net_resp
        cum_net_trace.stats.station='NR'
        cum_net_trace.stats.channel=''
        cum_net_trace.stats.network=''
        cum_net_trace.stats.location=''
        cum_net_trace=Stream(cum_net_trace)
        cum_net_trace+=stream.select(channel='*N')
        cum_net_trace+=stream.select(channel='*1')
        if not brightdef.plotsave:
            cum_net_trace.plot(size=(800,600), equal_scale=False)
        else:
            cum_net_trace.plot(size=(800,600), equal_scale=False,\
                               outfile='NR_timeseries.png')

    # Find detection within this network response
    print 'Finding detections in the cumulatve network response'
    detections=_find_detections(cum_net_resp, peak_nodes, threshold, thresh_type,\
                     stream[0].stats.sampling_rate, realstations)
    del cum_net_resp
    templates=[]
    nodesout=[]
    j=0
    if detections:
        print 'Converting detections in to templates'
        for detection in detections:
            print 'Converting for detection '+str(j)+' of '+str(len(detections))
            j+=1
            copy_of_stream=deepcopy(stream_copy)
            # Convert detections to PICK type - name of detection template
            # is the node.
            node=(detection.template_name.split('_')[0],\
                    detection.template_name.split('_')[1],\
                    detection.template_name.split('_')[2])
            print node
            nodesout+=[node]
            # Look up node in nodes and find the associated lags
            index=nodes.index(node)
            detect_lags=lags[:,index]
            i=0
            picks=[]
            for detect_lag in detect_lags:
                station=stations[i]
                st=copy_of_stream.select(station=station)
                if len(st) != 0:
                    for tr in st:
                        picks.append(PICK(station=station,
                                          channel=tr.stats.channel,
                                          impulsivity='E', phase='S',
                                          weight='3', polarity='',
                                          time=tr.stats.starttime+detect_lag+detection.detect_time,
                                          coda='', amplitude='', peri='',
                                          azimuth='', velocity='', AIN='', SNR='',
                                          azimuthres='', timeres='',
                                          finalweight='', distance='',
                                          CAZ=''))
                i+=1
            print 'Generating template for detection: '+str(j)
            template=(_template_gen(picks, copy_of_stream, defaults.length, 'all'))
            template_name=defaults.saveloc+'/'+\
                    str(template[0].stats.starttime)+'.ms'
                # In the interests of RAM conservation we write then read
            # Check coherancy here!
            if coherance(template) > coherance_thresh:
                template.write(template_name,format="MSEED")
                print 'Written template as: '+template_name
                coherant=True
            else:
                print 'Template was incoherant'
                coherant=False
            del copy_of_stream, tr, template
            if coherant:
                templates.append(obsread(template_name))
            else:
                print 'No templates for you'
    nodesout=list(set(nodesout))
    return templates, nodesout

