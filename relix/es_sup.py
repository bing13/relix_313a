#####################################################
# es_sup.py
#
# main ElasticSearch support functions
#
# 2021-09-18 migration to ES hosted ES search
#   MAJOR CHANGES:
#     no empty clauses; can't begin clause w/array; no double array brackets;
#     changes in REST APIs for _search, _update, etc. Yikes!
######################################################
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse
from django.utils import timezone, html
from datetime import datetime, date
import pytz

from django.urls import reverse
from relix.forms import  quickSearchForm, advancedSearchForm, idSearchForm
from relix.models import Notes, Work_set, People, Group

#from neo4j import GraphDatabase, basic_auth
from neomodel import db, DoesNotExist

import json, requests
import urllib.parse as urlparse
import re
from uuid import uuid4
from . import rutils
from multifactor.decorators import multifactor_protected

ES_URL = 'https://relix3b.es.us-west-1.aws.found.io:9243'  #ElasticSearch service
#ES_UNM = ES_URL+'/notes/'
ES_UNM = ES_URL+'/notes2/'
ES_TERMX = ES_URL+'/terms/'
with open('/home/ubuntu/other_config_files/d_settings/elastic_cd.txt') as f:
    UX, PX = f.readline().strip().split(',')

MIN_SCORE = 0.5

#######################################################.
@login_required
# commenting MFA line below, b/c if MFA prompts during save, it crashes 8/23/2023
#@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def EStextNotesGet (request,pmidList,uuid='no_uuid_provided'):
    '''grab the noteText from ES
       supports multi-PMID lists, so uses search instead of direct doc access'''
    
    if len(pmidList) > 0:
        pmidListDicts = [ {'match': {'pmid': x}} for x in pmidList]
        queryx = { 'size': 400, 'query': {'bool': {'should': pmidListDicts }}, \
                   '_source': ['pmid','noteText']}

        rx = requests.get(ES_UNM+'_search',params={},json=queryx, auth=(UX, PX))
        rv = json.loads(rx.text)
        # dict keys: hits, _shards, took, timed_out
        resultDict = {}

        # If, ex., gunicorn gets restarted ("r3"), the uuid present in the calling URL won't be in the store. So treat it like
        #   a missing UUID, and avoid a crashed window.
        if uuid not in request.session.keys():
            uuid = 'no_uuid_provided'
        
        for hx in rv['hits']['hits']:
            if 'noteText' in hx['_source'].keys():
                #re.sub adds hotlinking to strings like "#12345"  2024-09-29.  Must to avoid trigering on color="#664433"> etc
                # This function gets called by Note Edit, as well as Shownote, etc,
                #   This logic avoids hotlinking PMIDs in the HTML returned by ES if it's a note edit. 
                if uuid == 'no_uuid_provided' or 'editing_note' not in request.session[uuid].keys() or request.session[uuid]['editing_note'] == False:
                    resultDict[hx['_source']['pmid']] = re.sub(r"(#)(\d{5})(\D)",'<a href="/relix/\g<2>/view/">\g<1>\g<2></a>\g<3>',hx['_source']['noteText'])
                else:
                    # resultDict is just {pmid1:noteText,pmid2:noteText}
                    resultDict[hx['_source']['pmid']] = hx['_source']['noteText']
    else:
        resultDict = {}
    
    return(resultDict)
#######################################################.
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESfastGet(request, pmid):
    '''goes directly for the document node, in case a new record
       hasn't been indexed in time. seems to be the case with meetings'''
    fx = requests.get(ES_UNM+'_doc/'+str(pmid), auth=(UX, PX))
    if '_source' in fx.json():
        return fx.json()['_source']['noteText']
    else:
        # catches error from note creation crash, network drop, etc.
        return 'ESfastGet_no_source_found'

########################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESgrabWholeNote(pmid):
    '''goes directly for the document node, returns all data.
       Good for debugging, doesn't need REQUEST
       REQUIRES:
         1)  ES_URL, ES_UNM, requests, UX, PX
         2)  COPY THIS FUNCTION W/O THE DECORATORS @login_required and @multifactor
    '''

    fx = requests.get(ES_UNM+'_doc/'+str(pmid), auth=(UX, PX))
    if '_source' in fx.json():
        return fx.json()['_source']
    else:
        # catches error from note creation crash, network drop, etc.
        return 'ESgrabWholeNote_no_source_found'


########################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def EScreateDocument(request, targetNode, newText):
    '''create (or overwrite) ES document'''
    #q = '/notes/p1/%s' % targetNode.pmid
    dx = tojson(targetNode, newText)
    lx = ES_UNM+'_doc/'+str(targetNode.pmid)
    rutils.logThis(request,"       ESx create  %s " % lx)
    # NOTE: this is a 'PUT'
    rx = requests.put(lx,params={'pretty':""}, json=tojson(targetNode, newText), auth=(UX, PX))
    rutils.logThis(request,"       EsX rx: %s" % rx.text)
    if json.loads(rx.text)['_shards']['successful'] > 0:
        return ('success')
    else:
        rutils.logThis(request,"       EScreateD FAIL:%s" % str(json.loads(rx.text)))
        rutils.message(request, "       EScreateD FAIL:%s" % str(json.loads(rx.text)))
        return ('failure, see logs')


########################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESupdateDocument(request, targetNode, newText):
    '''modify ES document. can add fields.'''

    # tojson is where newText='no_text_update' is flagged
    dx = tojson(targetNode, newText)
    #rutils.logThis(request,"       dx=%s %s ..." % (dx['pmid'],dx['title']))
    rutils.logThis(request,"       dx=%s " % dx )
    
    UPDATE_URL = ES_UNM+'_update/'+str(targetNode.pmid)
    rutils.logThis(request,"       ESupdateDocument: %s " % UPDATE_URL )

    # NOTE: this is a 'POST'; and data= requires an enclosing "doc":{ ...}  element
    rx = requests.post(UPDATE_URL,params={'pretty':""}, json={ "doc":dx}, auth=(UX, PX))
    #rutils.logThis(request,"RX=%s" % rx.text)

    if '_shards' in json.loads(rx.text).keys():
        if json.loads(rx.text)['_shards']['successful'] > 0:
            rutils.logThis(request,"       ESupdateD Success:%s" % str(json.loads(rx.text)))
            return ('success')
        else:
            if json.loads(rx.text)['_shards']['failed'] > 0:
                rutils.logThis(request,"       ESupdateD ERROR FAIL:%s" % str(json.loads(rx.text)))
                rutils.message(request, "       ESupdateD ERROR FAIL:%s" % str(json.loads(rx.text)))
                return ('failure, see logs')                
            else:
                rutils.logThis(request,"       ESupdateD NOOP: no success, no fail:%s" % str(json.loads(rx.text)))
                rutils.logThis(request,"       ====> NOOP data: %s" % dx )
                rutils.message(request, "       **NOOP:%s" % str(targetNode.pmid))                
                return ('NOOP, see logs')
    else:
        rutils.message(request, "       ESupdateD ERROR:%s, ES may not have had this note. Creating...." % targetNode.pmid )
        rutils.logThis(request, "       ESupdateD ERROR:%s, ES may not have had this note. Creating...." % targetNode.pmid )
        create_result = EScreateDocument(request, targetNode, "       ESupdateDocument: Error recovery, this text inserted. ")
        return (create_result)

########################################################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESbulkWorksetUpdate(request, bunch_of_nodes):
    '''bulk update workset for a set of nodes '''
    #https://www.elastic.co/guide/en/elasticsearch/reference/7.14/docs-bulk.html
    # dx = json.dumps( { "work_set" : new_label } )
    dx = 'error undefined ESbWS'
    bulk_update = ''
    for target_node in bunch_of_nodes:
        bulk_update += '{"update":{"_id":"%s"}\n{"doc": { "work_set":"%s"} }\n' % (target_node.pmid, target_node.get_workset_name())
    bulk_update += '\n'  # required by bulk update API
    rutils.logThis(request,"Bulk workset update %s" % (bulk_update))

    # can't post as JSON, b/c \n is row delimiter
    rx = requests.post(ES_UNM+'_bulk',params={'pretty':""}, headers={'Content-Type':'application/x-ndjson'}, data=bulk_update, auth=(UX, PX) )
    rutils.logThis(request,"RX=%s" % str(json.loads(rx.text)))
    
    # '_shards' returned in a different part of the result for BULK update, it seems
    RX = json.loads(rx.text)
    status = []
    success = 0
    for this_result in RX['items']:
        if '_shards' in this_result['update'].keys():
            if this_result['update']['_shards']['successful'] > 0:
                success += 1
                #rutils.logThis(request,"ESupdateWkst Success:%s" %  this_result['update']['_id'] )
            else:
                if this_result['update']['_shards']['failed'] > 0:
                    status.append("failure")
                    rutils.logThis(request,"       ESbulkWkst FAIL:%s" % this_result['update']['_id'])
                else:
                    status.append("noop")
                    rutils.logThis(request,"       ESbulkWkst NOOP:%s" % this_result['update']['_id'])
        else:
            status.append("result not parseable")
            rutils.logThis(request, "       ESbulkWkst error:%s" % this_result['update']['_id'] )
            rutils.logThis(request,"           ====> error data: %s" % dx )

    return status, success
#######################################################################

@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESbulkItemsEditUpdate(request, bunch_of_nodes):
    '''bulk update ItemsEdit fields for a provided set of nodes '''

    dx = 'error not defined EBIEu'
    bulk_update = ''
    for target_node in bunch_of_nodes:
        if target_node.dtModified == None:
            dmodtemp = int(datetime.timestamp(datetime.now(pytz.timezone('UTC')))*1000)
        else:
            dmodtemp = int(datetime.timestamp(target_node.dtModified)*1000)

        assigned_to = ','.join([ x.nickname for x in target_node.assigned_to.all() ])
        involves = ','.join([ x.nickname for x in target_node.involves.all() ])
        if assigned_to == '': assigned_to = None
        if involves == '': involves = None
        if target_node.archived == True:
            arch_es = 'true'
        else:
            arch_es = 'false'
        
        # why only index these fields?
        #    time is modified above
        #    assigned/involved are modified above
        #    arch is modified above
        #    priority/status is updated from JS, not clear why it's here as well
        #    workset is stashed in ES by rutils.set_workset_with_descent , when *individual* notes are edited.
        #       (workset is searched as SCOPE (a list of PMIDs), but is indexed in ES by name for data security & integrity)
        bulk_update += '{"update":{"_id":"%s"}\n{"doc": {"dtModified":"%s", "archived":"%s", "priority":"%s", "status":"%s", "assigned_to":"%s", "involves":"%s"} }\n' % (target_node.pmid, dmodtemp, arch_es, target_node.priority, target_node.status, assigned_to, involves )
    rutils.logThis(request,"       ESbulkItemsEdit %s" % (bulk_update))
    
    ## SUBMIT ELASTICSEARCH BULK UPDATE REQUEST ######################################################
    rx = requests.post(ES_UNM+'_bulk',params={'pretty':""}, data=bulk_update, headers={'Content-Type':'application/x-ndjson'},auth=(UX, PX) )
    rutils.logThis(request,"       ESBulkItemsEdit RX=%s" % str(json.loads(rx.text)))
    
    # '_shards' returned in a different part of the result for BULK update, it seems
    RX = json.loads(rx.text)
    status = []
    success = 0
    for this_result in RX['items']:
        if '_shards' in this_result['update'].keys():
            if this_result['update']['_shards']['successful'] > 0:
                success += 1
                #rutils.logThis(request,"ESupdateWkst Success:%s" %  this_result['update']['_id'] )
            else:
                if this_result['update']['_shards']['failed'] > 0:
                    status.append("failure")
                    rutils.logThis(request,"       ESbulkIE FAIL:%s" % this_result['update']['_id'])
                else:
                    status.append("noop")
                    rutils.logThis(request,"       ESbulkIE NOOP:%s" % this_result['update']['_id'])
        else:
            status.append("result not parseable")
            rutils.logThis(request, "       ESbulkIE error:%s" % this_result['update']['_id'] )
            rutils.logThis(request,"        ====> error data: %s" % dx )

    return status, success

########################################################
def es_refresh_document_no_text(request, target_id):
    '''for rinteract ==> refresh ES for any given PMID, skipping noteText'''
    target_node = Notes.nodes.get(pmid=int(target_id))
    rutils.logThis(request,"       es_refresh_doc_no_text for pmid=%s" % target_id)
    statusx = ESupdateDocument(request, target_node, 'no_text_update')
    return HttpResponse("exiting es_refresh_document_no_text")
    
########################################################
def ESpushScope(request, scope_array):
    '''push a scope array to the terms/scopex index'''

    # "terms" is index; "scopex" is mapping
    #q = '/terms/scopex/'
    rutils.logThis(request,"       ESpushScope scope_array=%s" % scope_array)
    rx = requests.post(ES_TERMX+'_doc',params={'pretty':""}, json=scope_array, auth=(UX, PX))
    
    rutils.logThis(request,"       ESpushScope result=%s" % json.loads(rx.text))
    if json.loads(rx.text)['_shards']['successful'] > 0:
        return ('success', json.loads(rx.text)['_id'])
    else:
        return ('failure', '')
    
    
#######################################################
def ESdeleteScope(request, sid):
    '''delete a scope array doc in terms/scopex index'''
    rutils.logThis(request,"       ESdeleteScope sid=%s" % sid)
    rx = requests.delete(ES_TERMX+'_doc/'+sid,params={'pretty':""}, auth=(UX, PX))
    rutils.logThis(request,"       ESdeleteScope result:=%s" % rx.json())
    return (rx.text)
    
#######################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESdeleteDocument(request, pmid):
    ''' delete ES document'''
    rutils.logThis(request,"       ESdeleteDocument pmid=%s" % pmid)
    rx = requests.delete(ES_UNM+'_doc/'+str(pmid),params={'pretty':""}, auth=(UX, PX))
    rutils.logThis(request,"       ESdeleteDocument result:=%s" % rx.json())
    return (rx.text)

########################################################

def tojson(nodex, newText):
    '''pass a node, get a json object for the node.
       used for creating, updating document.
       flag values supported for newText, see below'''
    
    if nodex.dtModified == None:
        dmodtemp = None
    else:
        dmodtemp = int(datetime.timestamp(nodex.dtModified)*1000)
        
    if nodex.dtAccessed == None:
        dacctemp = None
    else:
        dacctemp = int(datetime.timestamp(nodex.dtAccessed)*1000)

    if nodex.reminder_date == None:
        dremind = None
    else:
        #dremind = int(datetime.timestamp(nodex.reminder_date)*1000)
        # nope, it's date, not a datetime. So convert it first
        dremind = int(datetime.timestamp(datetime(nodex.reminder_date.year, nodex.reminder_date.month, nodex.reminder_date.day, 0,0,0,0))*1000)

    # get any people assignments/involvements ######
    #    ES will index Nickname like a text attribute.
    assigned_to = ','.join([ x.nickname for x in nodex.assigned_to.all() ])
    involves = ','.join([ x.nickname for x in nodex.involves.all() ])

    # avoid case problems with archived
    if nodex.archived == True:
        arch_es = 'true'
    else:
        arch_es = 'false'

    # create indicator for shortlist membership
    #  note, this is not the genralized solution. There can be an arbitrary # of lists
    shortlist_group_node = Group.nodes.get(group_name="shortlist", created_by=nodex.created_by)
    if nodex in shortlist_group_node.group_items:
        shortlist_flag = True
    else:
        shortlist_flag = False

    # build the python object, then dump as JSON string        
    # even the most minimal update requires these:
    j1 = { "pmid" : nodex.pmid,\
           "dtModified" : dmodtemp,\
           "dtAccessed":dacctemp,\
           "priority" : nodex.priority, \
           "status" : nodex.status }

    # 2021-02-15 these terms used to be set to "none"..  changed to elide 
    # 2024-03-17 uh-oh. Eliding results in no ES update when a person is removed from a task
    #       Now will try setting to '' when person is removed.  
    
    if assigned_to != '':
         j1.update({ "assigned_to" : assigned_to } )
    else:
        j1.update({ "assigned_to" : '' } )
    if involves != '': 
        j1.update( { "involves" : involves } )
    else:
        j1.update( { "involves" : '' } )
        
    # 2025-09-14 added adorn, jumpcolor,start_folded, reminder_date, tagged_page,shortlist,meeting_master, gridItem,grid_order
    j2 = { "created_by" : nodex.created_by, \
           "title" : nodex.title, \
           "dtCreated" : int(datetime.timestamp(nodex.dtCreated)*1000), \
           "archived" : arch_es, \
           "topSort" : nodex.topSort, \
           "sectionhead" : nodex.sectionhead, \
           "webpage_set":nodex.webpage_set, \
           "jumplink" : nodex.jumplink, \
           "jumplabel" : nodex.jumplabel, \
           "jumpcolor" : nodex.jumpcolor, \
           "image_list" : nodex.image_list, \
           "work_set" : nodex.get_workset_name(), \
           "start_folded":nodex.start_folded,\
           "adorn":nodex.adorn, \
           "hasNote":nodex.hasNote, \
           "reminder_date":dremind, \
           "tagged_page":nodex.tagged_page, \
           "shortlist":shortlist_flag, \
           "meeting_master":nodex.meeting_master, \
           "gridItem":nodex.gridItem, \
           "grid_order":nodex.grid_order
          }
    
    j3 = {"noteText" : newText }

    #  can't easily differentiate when a user request had no noteText field vs
    #  when the user request was trying to delete (null out) existing noteText text.
    #  so explicit "signal" string now supported for various purposes
    
    jfinal = j1
    if newText != 'priority_status_update':
        jfinal.update(j2)
    if newText != 'no_text_update' and newText != 'priority_status_update':
        jfinal.update(j3)
    ## this is what was previously output. With switch to ES_es, and using json= instead of data=
    ##   in the requests, we'll now traffick in json, not strings.
    #jout = json.dumps(jfinal)

    return(jfinal)


###################################################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESquick (request, uuid):
    ''' Creates searchpacket for MULTIFIELDED quicksearch, sends it to runESadvSearch'''
    rutils.logThis(request, "        ESquick...........................")
    #analyze search string
    #searchString = urlparse.unquote(searchString)
    searchString = request.session[uuid]['searchFx']
    # searchString='noSearch'
    phrase_match = []
    should_terms = []
    multifield_query = []
    if 'title:' in searchString:
        ## it's a title quick search
        field, searchString = searchString.split(':')
        multifield_query = { "query": \
                                 { \
                                       "multi_match": \
                                         { \
                                         "query": searchString, \
                                         "fields": [ "title", "title.english" ], \
                                         "type": "most_fields" \
                                         } \
                                   } \
                            } 
    else:
        ## it's not title fielded
         multifield_query = { "query": \
                                 { \
                                       "multi_match": \
                                         { \
                                         "query": searchString, \
                                         "fields": [ "title", "title.english", "noteText","noteText.english","assigned_to","involves" ], \
                                         "type": "most_fields" \
                                         } \
                                   } \
                            } 
   
    searchpacket = [ should_terms, [], [], [{"created_by": request.user.username} ], phrase_match, [], [0], [], [multifield_query] ]
    request.session[uuid]['search_packet'] = searchpacket
    rutils.vsession(request,'update',{},uuid)
    
    rutils.logThis(request, "       ESquick passing search to runESadv: %s " % searchpacket)
    return HttpResponseRedirect('/relix/runESadvSearch/%s' % (uuid) )    
  
#####################################################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def ESreiterateSearch (request, uuid='no_uuid_passed', sort_order='same'):
    ''' gets the search query from session variables, builds the searchpacket, and resubmits it 
        used by notes_edit to return to search list after editing item.
        also used to resubmit search w/dtModified vs relevance sort order'''

    if 'search_packet' not in request.session[uuid]:
        # ex., multi-pmid "search", followed by item edit, returns you here. But there is no real search packet.
        rutils.logThis(request, "    No search packet for this type of search. ")
        rutils.message(request, "no search packet" )
        return HttpResponseRedirect(reverse('relix:home'))
    
    sp = request.session[uuid]['search_packet']    
    rutils.logThis(request, "       Reiterating, sort_order=%s,  search_packet: %s" % (sort_order, sp))
    #e = eval(sp)
    if sort_order == 'date_mod':
        sp[7] = [{"dtModified": {"order" : "desc"}}]
    elif sort_order == 'priority':
        sp[7] = [{"priority": {"order": "asc"}}]
    elif sort_order == 'relev':
        sp[7] = []
        
    request.session[uuid]['search_packet'] = sp
    rutils.vsession(request,'update',{},uuid)
    #sp = str(e) 
    return HttpResponseRedirect('/relix/runESadvSearch/%s' % (uuid) )

#####################################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def runESadvSearch(request, uuid):
    rutils.logThis(request, "ENTER runESadvSearch uuid=%s <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"  % uuid)
    # form is built in views.advancedSearch
    # targetID is passed to populate the "reload with archived" etc links
    # searchList = [ { term: value}, { term: value } ] ...
    if uuid not in request.session.keys():
        rutils.logThis(request, "SEARCH: uuid %s missing, aborting " % uuid )
        rutils.message(request, "Search:uuid missing" % uuid )
        return HttpResponseRedirect(reverse('relix:home'))

    rutils.vsession(request,'dump_to_log',{},uuid)
    if request.session[uuid]['searchFx']=='hotSearch':
        orig_of_hotSearch = request.session[uuid]['fetch_root']
        is_hotSearch = True
    else:
        orig_of_hotSearch = -9
        is_hotSearch = False

    searchpacket = request.session[uuid]['search_packet']
    
    rutils.logThis(request,"       runESadvSearch, searchpacket: %s, uuid: %s" % (searchpacket, uuid))
    rutils.logThis(request,"       searchpacket is of type %s, len=%s" % (type(searchpacket), len(searchpacket)))

    #should_terms, must_terms, must_not_terms, filter_terms, phrase_match, range_query, scope_list, sort_terms, multi_field_query = eval(str(searchpacket))

    searchpacket=eval(str(searchpacket))
    should_terms = searchpacket[0]
    must_terms = searchpacket[1]
    must_not_terms = searchpacket[2]
    filter_terms = searchpacket[3]
    phrase_match = searchpacket[4]
    range_query = searchpacket[5]
    scope_list = searchpacket[6]
    sort_terms = searchpacket[7]
    multi_field_query = searchpacket[8]

    needs_search_term = False
    ##### handle if search has only filter terms. needs search term or results are incomplete #####
    if should_terms == [] and must_terms == [] and must_not_terms == [] and phrase_match == [] and multi_field_query == []:
        needs_search_term = True
        ## I *think* you can't do a filter-only search. So here's a dummy search that finds all notes
        must_not_terms = { "term": {"pmid": 1 } }
        
        #should_terms = [{'pmid': 5900}] # works    # gotta remove size and min_score
    
    if 'searchFx' in request.session[uuid]:
        # searchFx may equal "hotSearch" in the request
        temp_searchFx = request.session[uuid]['searchFx']
    else:
        temp_searchFx = ''

    # when a hotSearch result item is editied, search sort was lost upon return.; busted again 2024-01-27
    #   This restores it, but note that it also imposes its value on any hotSearch (which is OK but confused troubleshooting)
    if temp_searchFx == "hotSearch":
        # values were in enclosing quotes, removed them 2021-01-18
        sort_terms = [{"priority": {"order" : "asc"}}]



    ### SCOPE #####################################################
    #####################################################################################################
    # TERMS LOOKUP IN ES:
    #     https://www.elastic.co/guide/en/elasticsearch/reference/7.7/query-dsl-terms-query.html#query-dsl-terms-lookup
    #####################################################################################################

    if scope_list != 'no_scope_specified':
        # https://www.elastic.co/guide/en/elasticsearch/reference/5.5/docs-index_.html#_automatic_id_generation
        # use POST notes/scopex
        # scope_list (scopex) contains EITHER a PMID, or a Work_set name, or nothing, in an array
        if type(scope_list[0]) == int:
            scopeNode = Notes.nodes.get_or_none(pmid=scope_list[0])
            if scopeNode != None:
                scopeIDs = [ f.pmid for f in scopeNode.descendants()]
                scopeIDs.append(scope_list[0])
            else:
                rutils.message(request, "       Scope PMID %s not found." % (scope_list[0]))
                rutils.logThis(request, "       ERROR:  Scope PMID %s not found." % (scope_list[0]))
                rutils.logThis(request, 'EXIT:  runESadvSearch <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
                return HttpResponseRedirect(reverse('relix:home'))
                
        else:
            # must be a Work_set #####
            work_set_node = Work_set.nodes.get(name=scope_list[0], created_by=request.user.username)
            scopeIDs = [ f.pmid for f in work_set_node.ws_belongs.all()]
            
        # now push scopeIDs into the /notes/scopex index#########
        scope_element = { "scope" : scopeIDs }
        ##status, scopexID = ESpushScope(request, json.dumps(data))
        status, scopexID = ESpushScope(request, scope_element)
        #########################################################
        ##filter_terms_lookup_dict_list =  { "terms": { "pmid": { "index" : "terms", "type" : "scopex", "id" : scopexID, "path" : "scope" } } }
        filter_terms_lookup_dict_list =  { "terms": { "pmid": { "index" : "terms", "id" : scopexID, "path" : "scope" } } }
    else:
        filter_terms_lookup_dict_list = []

    # date queries
    # https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html#_date_format_in_range_queries

    if should_terms != []:
        should_dict_list = [ { "term": dx }  for dx in should_terms ]
    else:
        should_dict_list = []

    # regular, not lookup, filter terms
    filter_dict_list = []
    if filter_terms != []:
        for fx in filter_terms:
            if isinstance(fx,list):
                if len(fx) == 1:
                    fx=fx[0]
            if 'terms' not in fx:
                rutils.logThis(request,"         --> terms appending: %s" % fx)
                filter_dict_list.append( { "term": fx } )
            else:
                filter_dict_list.append(  fx  )
                
    must_dict_list = []                
    if isinstance(must_terms,list):
        if len(must_terms) > 1:        
            must_dict_list = [ { "term": fx }  for fx in must_terms ]
        elif len(must_terms) == 1:
            must_dict_list = must_terms

    must_not_dict_list = []
    if isinstance(must_not_terms,list):
        if len(must_not_terms) > 1:
            must_not_dict_list = [ { "term": fx }  for fx in must_not_terms ]
        elif len(must_not_dict_list) == 1:
            must_not_dict_list =  must_not_terms[0]
    else:
        must_not_dict_list =  must_not_terms # must be a string

    if range_query != []:
        range_query_dict_list = [ { "range": fx }  for fx in range_query ]
    else:
        range_query_dict_list = []


    if must_dict_list == [] and should_dict_list == [] and needs_search_term == False:
        use_score = 0
    else:
        use_score = MIN_SCORE

    if needs_search_term:
        # must doesn't like size or min_score, it appears
        fin_query = { "size": 50, "query" : {  "bool" : { "filter": range_query_dict_list + filter_dict_list  } }  }
    else:
        fin_query = { "size": 50, 'min_score': use_score, "query" : {  "bool" : { "filter":  range_query_dict_list + filter_dict_list  } }  }
            
    if should_dict_list != []:
        fin_query['query']['bool']['should'] = should_dict_list
        if "assigned_to" in str(should_dict_list):
            fin_query['query']['bool']['minimum_should_match'] = 1;
            # these two seem incompatible with minimum_should_match
            del fin_query['min_score']
            # 2019-01-08 The next line was also commented out, but restricted Person search to returning only 10 results
            # Don't know what other "should" searches could be affected. Monitor.
            #del fin_query['size'] 
        
    if must_dict_list != []:
        fin_query['query']['bool']['must'] = must_dict_list

    if must_not_dict_list != []:
        fin_query['query']['bool']['must_not'] = must_not_dict_list


    if phrase_match != []:
        # if there's a quote mark, the string generation is different and requires the eval
        # fin_query['query']['bool']['must']['match_phrase'] = eval(phrase_match[0])
        # 2021-02-26 was broken with the eval, removed it.
        fin_query['query']['bool']['must'] = {}
        fin_query['query']['bool']['must']['match_phrase'] = phrase_match[0]
    if filter_terms_lookup_dict_list != []:
        #fin_query['query']['bool']['filter'].append([filter_terms_lookup_dict_list])
        fin_query['query']['bool']['filter'].append(filter_terms_lookup_dict_list)
    if sort_terms != []:
        fin_query['sort'] = sort_terms[0] # was eval()
    if multi_field_query != []:
        ## it's a multi-field search (from quicksearch)########################################
        # not sure what MIN_SCORE/use_score makes sense
        # filter picks up created_by crit

        # seed the query string, including w/created_by (via filter_dict_list)
        ##fin_query = { "size": 50, 'min_score': use_score, "query" : {  "bool" : { "filter": [ filter_dict_list ] } }  }
        fin_query = { "size": 50, 'min_score': use_score, "query" : {  "bool" : { "filter": filter_dict_list  } }  }

        ## need to account for sort, might not be right here ###
        if sort_terms != []:
            fin_query['sort'] = sort_terms[0] # was eval()
        
        #blend  the multi field query clause into the fin_query query clause
        # MULTI-MATCH should be within bool, but after "must" (or maybe other such clauses;  Look it up.)
        fin_query['query']['bool']['must'] = multi_field_query[0]['query']

        
    ###############################################################################################  RUN
    ######  LOG IT and RUN THE QUERY  #######################################################################  RUN
    ###############################################################################################  RUN
    rutils.logThis(request,"       runESadvSearch2: fin_query=%s" % json.dumps(fin_query) )
    rx = requests.get(ES_UNM+'_search',params={'pretty':""},json=fin_query, auth=(UX, PX))
    rv = rx.json()
    # dict keys: hits, _shards, took, timed_out
    scoreDict = {}
    resultOrder = []  # dict keys don't preserve order, and order of results matters
    # _score is available at, ex., rkv['hits']['hits'][29]['_score']

    # DEBUG RESULTS LOGGING   ################################
    # rutils.logThis(request,"RESULT=%s" % rx.text )

    for hx in rv['hits']['hits']:
        #resultDict[hx['_source']['pmid']] = hx['_source']['noteText']
        scoreDict[hx['_source']['pmid']] = hx['_score']
        resultOrder.append(hx['_source']['pmid'])
    
    ## now test for scope
    ## scope can be a list, but let's start with one value only
    if scope_list != 'no_scope_specified':
        # clear the scope terms document
        statusText = ESdeleteScope(request, scopexID)

    # get the Notes that correspond to the returned ES hits
    #foundItems = [ Notes.nodes.get(pmid=ox) for ox in resultOrder ]
    foundItems = []
    for ox in resultOrder:
        try:
            n = Notes.nodes.get(pmid=ox)
            # TEMPORARY. DO NOT SAVE. Just for passing to template
            n.work_set = n.get_workset_name()
            foundItems.append(n)
        except:
            rutils.logThis(request, "       ERROR ===> returned ES result PMID=%s not found!  " % ox )
            rutils.message(request, "ES PMID=%s not found!  " % ox )

    #for new session var's
    sdict = {}
    sdict['search_packet'] = searchpacket
    sdict['fetch_type'] = 'search'
    sdict['searchQuery'] = fin_query
    sdict['searchField'] = '---'
    sdict['fetch_root'] = -9
    sdict['search_decoded'] = search_decode(searchpacket)
    if temp_searchFx == 'hotSearch':
        sdict['searchFx'] = 'hotSearch'
    else:
        sdict['searchFx'] = ''

    jlist_result = rutils.rebuild_jumplinks(request)
    #all_worksets_list = [None] + rutils.get_all_worksets(request)
    all_worksets_list = rutils.get_all_worksets(request)

    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
    
    if len(foundItems) > 0:
         # get ancestorlist for each foundItem
        ancestors = {}
        for fi in foundItems:
            anc_list = fi.ancestorList(request.user.username)
            anc_list.reverse()
            ancestors[str(fi.pmid)] = anc_list
            # itemlist template now expects (node, pathlength) tuple, so dummy for the latter

        rutils.logThis(request, "       advSearch # of results found: "+str(len(foundItems)))

        lf_display, lf_list = rutils.locked_file_pmids(request)
        rutils.logThis(request, "EXIT: ADVSEARCH  %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(foundItems))
        context = {'current_items':foundItems, 'parent_id':-9, \
                   'ancestors':ancestors, \
                   'esScoreDict':scoreDict, \
                   'PCHX':Notes.PRIORITY_CHOICES, 'SCHX':Notes.STATUS_CHOICES, \
                   'workset_list':all_worksets_list, 'return_me_to':-13, \
                   'shortlist_ids':rutils.get_shortlist_ids(request), \
                   'umessage':umessage, \
                   'lock_file_list':lf_list, \
                   'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))), \
                   'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
                   'uuid':uuid, \
                   'titleCrumbBlurb':'%s search results' % len(foundItems), \
                   'orig_of_hotSearch':orig_of_hotSearch, 'is_hotSearch':is_hotSearch}
        ## render runESadSearch view ##
        return render(request, 'flat.html', context)
    else:
        rutils.message(request, 'no search results found' )
        #return HttpResponseRedirect(reverse('relix:advanced-search-get'))
        request.session[uuid]['search_packet'] = searchpacket
        rutils.vsession(request,'update',{},uuid)
        rutils.logThis(request,  "      No results, passing to -get_no-hit.  empty_search set 'True'" )
        return HttpResponseRedirect(reverse('relix:get_no-hit', kwargs={'empty_search':'True','uuid':uuid } ))
        
    ## END runESadvSearch view##############################
    
#########################################################################################

def search_decode(search_packet):
    '''take the search packet, and return an HTML representation for
       display on the itemlist'''
    sp = search_packet #was eval()

    #order of terms
    #should_terms, must_terms, must_not_terms, filter_terms, phrase_match, range_query, scope_list, sort_terms, multi_field_query

    terms = {}
    terms['should'] = sp[0]
    terms['must'] = sp[1]
    terms['must_not'] = sp[2]
    terms['filter'] = sp[3]
    terms['phrase'] = sp[4]
    terms['range'] = sp[5]
    terms['scope'] = sp[6]
    terms['sort'] = sp[7]
    terms['multi'] = sp[8]    
    
    #k = terms.keys()
    #multi shouldn't come last, let's force the order
    k = ['multi','should','must','must_not','filter','phrase','range','scope','sort']
    finals = []
    #rutils.logThis(request,"Terms=%s" % str(terms))
    for i in k:
        if terms[i] != []:

            if i == 'scope':
                if terms['scope'] != 'no_scope_specified':
                    if type(terms['scope']) == int:
                        scope_node = Notes.nodes.get(pmid=terms['scope'])
                        finals.append('<strong>scope</strong>: %s %s' % (scope_node.pmid, scope_node.title))
                    else:
                        # must be a Work_set
                        finals.append('<strong>scope</strong>: work_set %s' % terms['scope'])
                else:
                    finals.append('<strong>scope</strong>: all')
            else:
                t = "<strong>"+i+"</strong>: "
                c = 0
                for j in terms[i]:
                    if i == 'range':
                        w = terms[i][0]
                        datetype = list(w.keys())[0]
                        startd = date.fromtimestamp(int(w[datetype]['gte'].split('|')[0])/1000).isoformat()
                        endd = date.fromtimestamp(int(w[datetype]['lte'].split('|')[0])/1000).isoformat()
                        t = "<strong>date range</strong>: %s to %s" % (startd, endd)
                    elif i== 'multi':
                        #w = eval(terms[i][0])
                        #t += terms[i][0]['query']['bool']['must']['multi_match']['query']
                        t += '<span class="search_result">'+terms[i][0]['query']['multi_match']['query']+'</span>'
                    elif i== 'filter':
                        #aug19 t += str(j[1:-1])+'&nbsp; &nbsp;'
                        t += str(j)
                    else:
                        #aug19 t += j[1:-1]+';  '
                        if type(j) == dict:
                            #it's a date range
                            t += list(j.keys())[0]+":"+str(list(j.values())[0])+';  '
                        else:
                            t += list(j.keys())[0]+":"+list(j.values())[0]+';  '
                        
                    c += 1
                finals.append(t)
                t = ''
    return(finals)

##############################################################################################
#### S E A R C H #############################################################################srch
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def quickSearch(request):
    ''' form creation and processing for embedded quicksearch feature. 
        search is executed in ESquick.'''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: QUICKSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")

    uuid = str(uuid4())
    
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        Sform = quickSearchForm(request.POST)
        # check whether it's valid:
        if Sform.is_valid():
            searchFx = Sform.cleaned_data['searchFx'].lower()
            sdict = { 'fetch_type':'search','searchFx':searchFx }
            # set vsession
            rutils.vsession(request,'new',sdict,uuid)

            is_digit_string = False
            # if there's a comma in search term, it may be a multi-PMID search
            if ',' in searchFx:
                if False not in [x.strip().isdigit() for x in searchFx.split(',')]:
                    is_digit_string = True
            #  test if search term is one or string of PMIDs 
            if is_digit_string or searchFx.isdigit():
                pmid_list = searchFx.split(',')
                foundItems = list(Notes.nodes.filter(pmid__in=pmid_list).filter(created_by=request.user.username))

                #get complete list of work_sets in use
                all_worksets_list = rutils.get_all_worksets(request)
                #
                sdict = { 'fetch_type':'search','searchFx':'qpmid'}
                # set vsession
                rutils.vsession(request,'new',sdict,uuid)
                context = {'current_items':foundItems, 'target_id':-9,
                           'workset_list':all_worksets_list, \
                           'PCHX':Notes.PRIORITY_CHOICES, \
                           'SCHX':Notes.STATUS_CHOICES, \
                           'shortlist_ids':rutils.get_shortlist_ids(request), \
                           'scrollTo':0,\
                           #'return_me_to':-17,\
                           'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))),\
                           'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
                           'titleCrumbBlurb':'Quicksearch',\
                           'uuid':uuid }
                return render(request, 'flat.html', context)

            rutils.logThis(request, "   Searching for: %s" % searchFx)
            return HttpResponseRedirect('/relix/ESquick/%s' % (uuid))

        else:
            ##form is invalid
            rutils.message(request, 'invalid qsearch')
            return render(request, 'home.html')
    # if a GET (or any other method) we'll create a blank form
    else:
        sform = quickSearchForm()

        return render(request, 'home.html', {'form': sform})

##############################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def advancedSearch(request,empty_search='False',uuid='nix'):
    # this is where the form is built & processed; 
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: Advanced Search <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    rutils.logThis(request,  "       empty_search=%s, uuid=%s" % (empty_search,uuid))
    
    ######## POST ################################################
    if request.method == 'POST':
        ### advancedSearch GET starts the UUID, so UUID is already defined
        
        # create a form  instance and populate it with data from the request:
        Sform = advancedSearchForm(request.POST)
        # check whether it's valid:
        searchField = 'nix'
        if Sform.is_valid():
            rutils.logThis(request, "       Advanced Search: valid form====== %s" % str(Sform.cleaned_data))
            submitted_fields = []

            # the following are form field names
            for x in  ['startDate', 'pmid', 'title', 'priority', 'status', 'noteText', 'people']:
                if Sform.cleaned_data[x] not in [ '',  None, 'None']:
                    searchField = x
                    searchFx = Sform.cleaned_data[searchField]
                    if searchField in ['title', 'noteText', 'people']:
                        searchFx = searchFx.lower()
                    elif searchField == 'pmid':
                        searchFx = str(searchFx)
                    if searchField == 'startDate':
                        # so submitted_fields here = ( dtCreated|dtModified,(startd, endd))
                        submitted_fields.append((Sform.cleaned_data['whichDate'], \
                                                     (Sform.cleaned_data['startDate'], \
                                                          Sform.cleaned_data['endDate'])))
                    else:
                        submitted_fields.append((searchField, searchFx))

            scopex = 'no_scope_specified'
            if Sform.cleaned_data['scope'] not in [ None ]:
                # scope on form is jumplink PMID
                scopex = [Sform.cleaned_data['scope']]
            elif Sform.cleaned_data['scope_manual'] not in [ None ]:
                # scope_manual is text field
                scopex = [Sform.cleaned_data['scope_manual']]
            elif Sform.cleaned_data['work_set'] not in ['None']:
                # workset is STRING workset
                scopex = [Sform.cleaned_data['work_set']]
                
            if scopex == 0: scopex = 'no_scope_specified'
            rutils.logThis(request,"scopex=%s" % scopex)
            ## assign search terms to ES query parts
            must_match = []
            must_not_match = []
            should_match = []
            #aug19filter_match = ['{"created_by"'+':'+'"'+request.user.username+'"}']
            filter_match = [{"created_by":request.user.username}]            
            range_query = []
            phrase_match = []

            ##it must be date, not datetime.date, and is why we have two date imports.
            # https://stackoverflow.com/questions/16151402/python-how-can-i-check-whether-an-object-is-of-type-datetime-date
            for searchField, searchFx in submitted_fields:
                rutils.logThis(request,"       searchfield:%s, searchFx:%s" % (searchField, searchFx))
                #isinstance(searchFx, date):
                if searchField == 'dtCreated' or searchField == 'dtModified':
                    # searchFx[0] is a datetime.date
                    startstamp = int(datetime(searchFx[0].year,searchFx[0].month,searchFx[0].day,0,0,0).timestamp()*1000)
                    if searchFx[1] == None or searchFx[0]==searchFx[1]:
                        endstamp = int(datetime(searchFx[0].year,searchFx[0].month,searchFx[0].day,23,59,59).timestamp()*1000)
                    else:
                        endstamp = int(datetime(searchFx[1].year,searchFx[1].month,searchFx[1].day,23,59,59).timestamp()*1000)
                    ## round down start date, round "up" end date
                    ##   https://www.elastic.co/guide/en/elasticsearch/reference/current/common-options.html
                    ##range_query.append({ searchField:{"gte" : str(startstamp)+"||", "lte" : str(endstamp)+"||" } } )
                    range_query.append({ searchField:{"gte" : str(startstamp), "lte" : str(endstamp) } } )
                    
                elif searchField not in ['priority', 'status', 'pmid'] and \
                  searchFx is not None and ('"' in searchFx or '-' in searchFx):
                    #quote seems to come in with pop-up select for priority and status
                    ### might need to be %s to avoid the quote problem on es_sup
                    ###########################################                    
                    if '"' in searchFx:
                        ### this turns "mx-5" into "x-" which crashes eval() in es_sup line 563
                        phrase_match.append({searchField : searchFx[1:-1].lower()})
                    else:
                        phrase_match.append({searchField : searchFx.lower()})

                elif searchFx is not None and ' ' in searchFx:
                    for sfx in searchFx.split(' '):
                        should_match.append({searchField : sfx.lower()})
                        
                elif searchField == "priority" or searchField == "status":
                    if searchFx != "-99":
                        filter_match.append({searchField:searchFx.lower()})
                elif searchField == 'people':
                    # people search should be against both people fields
                    # can use "must" or "filter" for both, b/c no one has both roles. 
                    should_match.append({'assigned_to':searchFx.lower()})
                    should_match.append({'involves':searchFx.lower()})
                else:
                    should_match.append({searchField:searchFx.lower()})

            if Sform.cleaned_data['include_archived'] == False:
                #must_match.append('{"archived":"false"}')
                filter_match.append({"archived":"false"})
                
            if Sform.cleaned_data['webpage_set'] == True:
                filter_match.append({"webpage_set":"true"})

            sdict = {'searchFx':searchFx,'fetch_type':'search'}
            sort_terms = []
            search_packet = str([should_match, must_match, must_not_match, filter_match, phrase_match, range_query, scopex, sort_terms, []])
            sdict['search_packet']=search_packet
            rutils.vsession(request,'update',sdict,uuid)
            rutils.logThis(request, "       ==> advSearch search_packet=%s" % search_packet)
            return HttpResponseRedirect('/relix/runESadvSearch/%s' % (uuid))
        else:
            ##form is invalid#############################################
            rutils.logThis(request, "       EXIT: Advanced Search invalid form >>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            rutils.message(request, 'invalid advanced search')
            return HttpResponseRedirect('/relix/advsearch/%s' % (uuid))
    else:
        ###################### GET ##################################################
        # if a GET (or any other method) we'll create a blank form ##
        rutils.logThis(request, "       Advanced Search - GET form ======")
        if uuid == 'nix':
            uuid = str(uuid4())
            rutils.vsession(request,'new',{'fetch_type':'search'},uuid)
        sform = advancedSearchForm()

        #get complete list of work_sets in use
        all_worksets_list = rutils.get_all_worksets(request)
        #get people list
        peeples=People.nodes.filter(created_by=request.user.username).order_by('nickname')
        
        # "None" gets translated to "All"
        rutils.logThis(request, "       EXIT: Advanced Search GET form >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")        
        ## from ADVANCED SEARCH ######################################
        return render(request, 'adv_search.html',\
                      {
                          'form':sform, 'PCHX':Notes.PRIORITY_CHOICES, 'SCHX':Notes.STATUS_CHOICES, \
                          'workset_list':all_worksets_list, \
                          'titleCrumbBlurb':'Advanced search', 'uuid':uuid,\
                          'people':peeples, 'empty_search':empty_search
                      } )

#############################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def hotSearch(request, uuid, target_id=-9):
    rutils.starttime_reset(request)
    rutils.logThis(request, "hotSearch====== %s" % target_id)
    filter_terms = [{"terms": {"priority" : ["1", "2", "3", "4"] }}, {"terms": {"status" : ["0", "1", "2", "3", "4", "5", "8"]}}, {"archived": "false"}]
    orig_filter_terms = ['{"terms": {"priority" : ["1", "2", "3", "4"] }}', '{"archived": "false"}']
    if int(target_id) > 0:
        scope_list = [int(target_id)]
        # should_terms, must_terms,must_not_terms, filter_terms, phrase_match, range_query, scope_list, multi_ = eval(searchpacket)
        sort_terms = [{"priority": {"order" : "asc"}}] 
        search_packet = [[], [], [], filter_terms, [], [], scope_list, sort_terms, []]
        request.session[uuid]['search_packet'] = search_packet
        request.session[uuid]['searchFx'] = 'hotSearch'

        rutils.logThis(request,"       HOTSEARCHx search_packet: %s, uuid: %s" % (search_packet, uuid))
    else:
        # otherwise it's probably a return from a note_edit off a hotlist.
        # Hopefully search packet session var is still intact. 
        search_packet = request.session[uuid]['search_packet']

    return HttpResponseRedirect('/relix/runESadvSearch/%s' % (uuid))

###########################################################################
    
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def id_fetch(request):
    # aka idSearch
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: IDSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        Sform = idSearchForm(request.POST)
            
        # check whether it's valid:
        if Sform.is_valid():
            ## exception if PMID not found
            try:
                targetNode = Notes.nodes.get(pmid=Sform.cleaned_data['fetchID'])
            except DoesNotExist:
                rutils.message(request, "       PMID %s not found." % (Sform.cleaned_data['fetchID']))
                rutils.logThis(request, 'EXIT: IDSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
                return HttpResponseRedirect(reverse('relix:home'))
            #####
            if targetNode.created_by != request.user.username:
                rutils.message(request, "       User %s not owner of node %s" % (request.user.username, targetNode.pmid))
                rutils.logThis(request, "       User %s not owner of node %s" % (request.user.username, targetNode.pmid))
                rutils.logThis(request, 'EXIT: IDSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
                return HttpResponseRedirect(reverse('relix:home'))
            rutils.logThis(request, 'EXIT: IDSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
            return HttpResponseRedirect(reverse('relix:viewTree', kwargs={'target_id':targetNode.pmid}))
        else:
            ##form is invalid
            rutils.message(request, '       invalid ID search')
            rutils.logThis(request, 'EXIT: IDSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')            
            return HttpResponseRedirect(reverse('relix:home'))
    # if a GET (or any other method) we'll create a blank form
    else:
        sform = idSearchForm()
        rutils.message(request, "       not a post to idSearch")
        rutils.logThis(request, 'EXIT: IDSEARCH  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
        return HttpResponseRedirect(reverse('relix:home'))
