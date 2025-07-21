#####################################################
# items.py
######################################################
''' functions pertaining to items '''

from django.contrib.auth.decorators import login_required
import inspect  # to find the function that called a function

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

#from neo4j import GraphDatabase, basic_auth
from neomodel import db, DoesNotExist

from datetime import datetime, date
import pytz, time, os, pickle, uuid, re
from uuid import uuid4

from relix.forms import changeRelixForm, newShortlistItemForm, newGridGroupForm, GGassignForm

from relix.models import Notes, Group, Work_set, People, GridGroup
from . import es_sup, rutils, views
from multifactor.decorators import multifactor_protected

LOCKFILES = '/tau/dj313/relix3/lockfiles/'

DDX = 20

# ADD_QNOTE ########################################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def add_qnote(request):
    '''create a new top-level, parentless node'''
    rutils.starttime_reset(request)    
    newPMID = rutils.get_next_pmid(request)
    rutils.logThis(request, "adding new Qnote parentless node,  %s <<<<<<<<<" % (newPMID))
    note_new = Notes(pmid=newPMID, title="Qnote", noteText='', created_by=request.user.username)
    note_new.dtCreated = datetime.now(pytz.timezone('US/Pacific'))
    note_new.dtModified = note_new.dtCreated
    # .accessed is not set here
    note_new.tagged_page = True
    note_new.save()
    
    qnote_ws = Work_set.nodes.get_or_none(name='qnote',created_by=request.user.username)
    note_new.ws_belongs.connect(qnote_ws)

    # add to the recent list
    rutils.add_recent(request, note_new.pmid)
    
    # add record to Elasticsearch ES
    es_sup.EScreateDocument(request, note_new, None)
    rutils.logThis(request, "Qnote created: %s" % str(note_new.pmid))
    
    return newPMID

# SPLIT_NOTE ########################################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def split_note(request,target_id,uuid):
    '''Split the mother (target_id) note based on formatting delimiters.
       Line that begins with "@@" is the title, everything until the next @@ is body.
       Turn the new notes into daughters of the target note.'''
    
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: SPLIT_NOTE <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    remove_html_tags = re.compile('<.*?>')
    target_id = int(target_id)
    target_node = Notes.nodes.get(pmid=target_id)
    #get esnoteText ###################
    esNoteTextDict = es_sup.EStextNotesGet(request, [target_id])

    if int(target_id) in esNoteTextDict.keys():
        thisNoteText = esNoteTextDict[target_id]
    else:
        thisNoteText = ''
    if thisNoteText == '' or not '@@' in thisNoteText:
        rutils.message(request,"No notes to split for %s" % target_node.pmid)
        rutils.logThis(request, "No notes to split for %s" % target_node.pmid)
        return views.universal_return(request, 'split_note', target_id, False, uuid)
    else:
        rutils.logThis(request, "Splitting this text: %s" % thisNoteText)
   
    # example body text, as returned from ES
    vv='''<p>this note has a double at</p>\r\n\r\n<p>this one is a good one</p>\r\n\r\n<p>@@here&#39;s the subject with the double at</p>\r\n\r\n<p>here&#39;s another thing, the body of the note</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<p>and more mtext</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<p>@@here&#39;s another note</p>\r\n\r\n<p>with some spacing above. this continues the body text</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<p>@@last note is a title only.</p>\r\n\r\n<p>&nbsp;</p>'''

    # CKedit puts every line in a tag (p or h1, etc). Split on <open_tag>@@, and then replace the open_tag
    #split_body_text = thisNoteText.split('<p>@@')
    #mother_text_revised = '<p>'+split_body_text.pop(0)

    f=re.compile('^(<h[0-9]>|<p><strong>|<p>|)?@@',re.M)
    n=re.split(f,thisNoteText)
    mother_text_revised = n[0]
    # now build the output array, reconstituting the opening tags that re.split split, and obliterated
    split_body_text = [];
    # regex groups (n) alternates (what triggered the split),(text segment),(what triggered the split)...
    for subn in range(1,len(n),2):
        # reconstitutes the html tags that got split.
        split_body_text.append(n[subn]+n[subn+1])

    # this local function is used recursively
    def remove_leading_newline(ntext):
        if ntext.find('\r\n')==0:
            nix, ntext = ntext.split('\r\n',1)
            # but maybe there's another newline pair after the first            
            remove_leading_newline(ntext)
        return ntext
    
    new_notes = []
    # for each delimited element,
    #     the text up to the first \r\n is the title
    #     the remainder is the body of the note
    for sbt in split_body_text:
        if '\r\n' in sbt:
            titlex, bodyx = sbt.split('\r\n',1)
            bodyx = remove_leading_newline(bodyx)
        else:
            titlex = sbt
            bodyx = ''
        titlex = '<p>'+titlex

        ## could consider removing a whitespace-only note text block
        new_notes.append((titlex,bodyx))
    rutils.logThis(request, "new_notes: %s" % str(new_notes))

    # update mother (i.e., target_node note ############################################
    target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))
    if len(mother_text_revised) > 1:
        target_node.hasNote = True
    else:
        target_node.hasNote = False        
    # update mother in ES with mother's new notetext.
    status = es_sup.ESupdateDocument(request, target_node, mother_text_revised)
    ## ES is updated, so clear the noteText field on the node (well, it shouldn't be set in the first place)
    target_node.noteText = ''
    target_node.save()
    
    # create note for each split item, with mother as parent####################
    for titlex, bodyx in new_notes:
        new_PMID = rutils.get_next_pmid(request)
        rutils.logThis(request, "adding split daughter %s <<<<<<<<<" % new_PMID)
        titlex = re.sub(remove_html_tags, '', titlex)
        note_new = Notes(pmid=new_PMID, title=titlex, noteText=bodyx, created_by=request.user.username)
        # use the mother's created date
        note_new.dtCreated = target_node.dtCreated
        note_new.dtModified = datetime.now(pytz.timezone('US/Pacific'))
        note_new.save()
        # link to mother parent
        x = note_new.child_of.connect(target_node)
        # link to the Workset node        
        y = note_new.ws_belongs.connect(target_node.ws_belongs.all()[0])
        note_new.save()
        if len(bodyx) > 1:
            note_new.hasNote = True
            note_new.save()
        # add record to Elasticsearch ES
        #   2021-02-16 - erroneous indent for the next two lines removed
        es_status = es_sup.EScreateDocument(request, note_new, bodyx)
        rutils.logThis(request, "---- New daughter split out ---> %s" % str(note_new.pmid))
    
    # won't bother with possible images stored, at the moment
 
    rutils.logThis(request, "EXIT split_note >>>>>>>>>>>>>>>>")    
    return views.universal_return(request, 'split_note', target_id, False, uuid)
## end SPLIT_NOTE ####

###########################################################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def changeRel(request, target_id, linkToType, linkToID, uuid):
    '''generate form or process POST to 
       allow a relationship to be added, deleted, or changed'''
    # linkToID = 0 means it's an addition
    ##mode, relType, selectedLinkTo, pmidLinkTo, orig_linkto_pmid, orig_linkto_type, addToPendingMoves
    ##request.session['fetchType'] = 'changeRel'
    rutils.logThis(request, "ENTER: CHANGEREL %s <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" % target_id)
    return_target=request.session[uuid]['fetch_root']
    targetNode = Notes.nodes.get(pmid=target_id)
    if targetNode.created_by != request.user.username:
        rutils.message(request, "User %s not owner of node %s" % (request.user.username, target_id))
        return HttpResponseRedirect(reverse('relix:home'))

    if request.method == 'POST':
        Sform = changeRelixForm(request.POST)
        # check whether it's valid:#############################################
        if Sform.is_valid():
            mode = Sform.cleaned_data['mode'] 
            relType = Sform.cleaned_data['relType']
            selectedLinkTo = Sform.cleaned_data['selectedLinkTo']
            pmidLinkTo = Sform.cleaned_data['pmidLinkTo']
            origLinkToID = Sform.cleaned_data['origLinkToID']
            origRelType = Sform.cleaned_data['origRelType']
            addToTaggedPages = Sform.cleaned_data['addToTaggedPages']
            rutils.logThis(request, "       changeRelixForm: valid form: mode:%s relType:%s selectedLinkTo:%s pmidLinkTo:%s origLinkToID:%s  origRelType:%s addToTaggedPages:%s ======" % (mode, relType, selectedLinkTo, pmidLinkTo, origLinkToID, origRelType, addToTaggedPages))

            # selectedLinkTo should not be = 0, which gives it a parent = ROOT_NODE, which is not a valid value
            # trunk children have no parent, not parent.pmid=0 .  this happens if user SAVES a changrel form
            # without entering any values
            if selectedLinkTo != 0 or pmidLinkTo != 0:
                # don't allow "add" for child_of changes. (i.e., 1 parent only); not the most elegant, but it'll work
                if relType == 'child_of':
                    mode = 'replace'
                if addToTaggedPages == True:
                    targetNode.tagged_page = True
                    targetNode.save()
                else:
                    ## here: changeRel ==> change or add the relationship ##############
                    status = execute_changerel( request, targetNode, mode, relType, pmidLinkTo, \
                                                selectedLinkTo, origLinkToID, origRelType, \
                                                return_target)
                        ##  error handling should apply to any other changerel well
                    if status == "pmidLinkTo does not exist":
                        rutils.logThis(request, "FAILED: CHANGEREL, pmidLinkTo not found   %s %s %s => %s >>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % (relType, mode, targetNode.pmid, pmidLinkTo))
                        return views.universal_return(request, 'changerel', origLinkToID, False, uuid)

                rutils.message(request, "changeRel %s" % targetNode.pmid)
                #######################################################
                # return to view [changeRel]
                #######################################################
            else:
                rutils.logThis(request, "       changeRelixForm: selectedLinkTo=0 not permitted, form ignored for %s" % target_id)

            ## change done#########################

            
            ## I suspect just not changing the fetch_root at all will be best ##############################
            ##  DELETE THIS BLOCK LATER IF THAT'S TRUE ###################################################################
            if False:
                uuid=str(uuid4())
                #sdict = {'fetch_root':-9,'fetch_type':'changerel'}
                # 2021-09-06 let's try having it return to what I hope is the new parent ID. Hope there are no other cases to consider
                # if this fails, just delete these lines which overwrite target_id and return_target
                # more convenient to return to pmidLinkTo?  Plus deprecate return_target
                if pmidLinkTo != None:
                    # user entered a PMID
                    use_this_fetch_root = pmidLinkTo
                else:
                    # user used the pull-down list of tagged pages
                    use_this_fetch_root = selectedLinkTo
                sdict = {'fetch_root':use_this_fetch_root,'fetch_type':'changerel'}
                # set vsession
                rutils.vsession(request,'new',sdict,uuid)
                ##############################
            
            #return universal_return(request, 'changeRel', target_id, True, uuid)
            return views.universal_return(request, 'changeRel', return_target, True, uuid)
            
                
        else:
            ##form is invalid ########################################################
            erx = str(Sform.errors)
            rutils.logThis(request, "       ERROR!!!!!! changeRel INVALID form: %s" % erx)
            rutils.message(request, '%s' % erx)
            return HttpResponseRedirect('/relix/%s/%s/%s/changerel/%s/' % (target_id, linkToType, linkToID, 'nix'))
            
    else:
        # if a GET (or any other method: CHANGEREL) #############################################################
        # create form instance and  populate it with data from the request:
        rutils.logThis(request, "       changeRel - GET form ====== %s " % target_id)
        rutils.logThis(request, "                         linkToID provided: %s " % linkToID)        
        sform = changeRelixForm()

        # now using tagged_page for "select by item" dropdown, as well as tagged page table :-)
        tagged_page_items = Notes.nodes.filter(tagged_page=True, created_by=request.user.username)
        if linkToID in (0, '0'):
            link_to_node = None
        else:
            link_to_node = Notes.nodes.get_or_none(pmid=linkToID)
        if linkToType == 'rel_content' or linkToType == 'relates':
            # it's an addition. Instead of "replace", a user can "add" and then "delete" the old one. it's safer. 
            mode = "add"
            if link_to_node == None:            
                linkToTitle = '(None provided)'
            else:
                linkToTitle = link_to_node.title
        elif linkToType == 'myroot':
            # it's an addition
            mode = "add"
            linkToTitle = 'None'
        elif linkToType == 'child_of':
            mode = "replace"
            linkToTitle = link_to_node.title
        else:
            rutils.logThis(request, "       SHOULD NOT HAVE LINKTOTYPE = %s, ABORT" % linkToType)
            abort

        #get complete list of work_sets in use
        #  TEMP: unlike other such calls, this one previously didn't add "None" to the start
        all_worksets_list = rutils.get_all_worksets(request)
            
        rutils.logThis(request, "EXIT CHANGEREL:  pmid %s  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % targetNode )
        context = {'current_items':tagged_page_items, 'ix':targetNode, 'mode':mode, \
                   'workset_list':all_worksets_list,  \
                   'origRelType':linkToType, 'origLinkToID':linkToID, 'origLinkToTitle':linkToTitle,\
                   'tagged_pages':tagged_page_items,\
                   'titleCrumbBlurb':str(targetNode.pmid)+' changeRel',\
                   'uuid':uuid }
        return render(request, 'change_relix.html', context)
#end CHANGEREL ###################

############################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def execute_changerel(request, targetNode, mode, relType, pmidLinkTo, selectedLinkTo, origLinkToID, origRelType, return_target):
    '''guts of add or change relationships. 
       Externalized so that both the form handler and pending move mechanism can share the same logic'''
    # pmidLinkTo = user filled in pmid # for target, rather than
    # selectedLinkTo = select pop-up box used

    # get the linkto node, from pmid manual field or selected node
    if pmidLinkTo != None:
        rutils.logThis(request, "     ...using pmidLinkTo = %s" % pmidLinkTo)
        try:
            linkToNode = Notes.nodes.get(pmid=pmidLinkTo)
        except DoesNotExist:
            rutils.message(request, "pmidLinkTo = %s does not exist" % pmidLinkTo)
            rutils.logThis(request, "ERROR: pmidLinkTo does not exist: %s" % pmidLinkTo)
            return "pmidLinkTo does not exist"
    else:
        rutils.logThis(request, "     ...using selectedLinkTo = %s" % selectedLinkTo)
        linkToNode = Notes.nodes.get(pmid=selectedLinkTo)

    # don't allow a parent to be moved under its child ###
    if relType == 'child_of' and (linkToNode.descendant_of(targetNode.pmid) or targetNode.pmid == linkToNode.pmid):
        rutils.logThis(request, "    ABORT - MOVE IS RECURSION, child = %s, target = %s" % (targetNode.pmid, linkToNode.pmid))
        rutils.message(request, "RECURSION aborted, %s=>%s" % (targetNode.pmid, linkToNode.pmid))
        return "RECURSION, aborted"
    else:
        ## not a recursion ##########################################################################
        
        if mode == 'replace':
            ## if mode = replace, break the existing relationship ######################
            rutils.logThis(request, "       EXECUTE_CHANGEREL, replace: origRelType = %s, origLinkToID = %s, pmid = %s" % (origRelType, origLinkToID, targetNode.pmid))
            # if origLinkToID -9, it was a trunk node, so nothing to disconnect
            if origLinkToID != -9:
                origLinktoNode = Notes.nodes.get(pmid=origLinkToID)
                if origRelType == 'child_of':
                    targetNode.child_of.disconnect(origLinktoNode)
                elif origRelType == 'rel_content':
                    targetNode.rel_content.disconnect(origLinktoNode)
                elif origRelType == 'relates':
                    targetNode.relates.disconnect(origLinktoNode)
                elif origRelType == 'prev_instance':
                    targetNode.prev_instance.disconnect(origLinktoNode)
                else:
                    rutils.logThis(request, "Unsupported origRelType: %s" % relType)
                    rutils.message(request, "Unsupported origRelType: %s" % relType)
                targetNode.save()

        status = 'unknown'
        ###################################################################################
        # for both mode=replace and mode=add, create the new relationship
        rutils.logThis(request, "       EXECUTE_CHANGEREL, create new rel: relType = %s, linkToNode = %s, pmid = %s, mode = %s" % (relType, linkToNode.pmid, targetNode.pmid, mode))
        if relType == 'child_of' or relType == 'myroot':
            rutils.logThis(request, "       ...creating child_of: %s" % linkToNode.pmid)
            targetNode.child_of.connect(linkToNode)
            # clear tagged_page
            targetNode.tagged_page = False

            #################################################################
            # WORKSET 
            #########WORKSET IN EXECUTE_CHANGEREL############################
            # for move, if label of new parent is different from label of child, propagate the parent's workset label
            if targetNode.get_workset_name() != linkToNode.get_workset_name():
                new_workset_name = linkToNode.get_workset_name()
                # set_label_* sets node.work_set as the new label
                rutils.set_workset_with_descent(request, targetNode, new_workset_name)
                
            # for move, call status update ##################
            pmids_to_reindex  = rutils.check_and_archive(request, targetNode) # execute_changerel
            if relType != 'myroot' and origLinkToID != -9 :
                pmids_to_reindex += rutils.check_and_archive(request, origLinktoNode)
            if len(pmids_to_reindex) > 0:
                reindex_these_nodes = Notes.nodes.filter(pmid__in=pmids_to_reindex)
                (status, success) = es_sup.ESbulkItemsEditUpdate(request, reindex_these_nodes)
                rutils.logThis(request,"       execute_changerel reindex status=%s, success=%s" % (status, success))

        elif relType == 'rel_content':
            targetNode.rel_content.connect(linkToNode)
        elif relType == 'relates':
            targetNode.relates.connect(linkToNode)
        elif relType == 'prev_instance':
            targetNode.prev_instance.connect(linkToNode)
        else:
            rutils.logThis(request, "       Unsupported relType: %s" % relType)
            rutils.message(request, "       Unsupported relType: %s" % relType)
            status = "unsupported relType"

        if status == "unsupported relType":
            rutils.message(request, "Unknown relType! aborted!")
        else:
            targetNode.save()
            status = "normal"
            rutils.logThis(request, "       ...changerel completed  %s %s %s => %s" % (relType, mode, targetNode.pmid, linkToNode.pmid))
            rutils.message(request, "done:%s %s %s => %s" % (relType, mode, targetNode.pmid, linkToNode.pmid))

        ############ end EXECUTE CHANGEREL ############################################################
        return status
## END EXECUTE CHANGEREL #######################################################################################

#########################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def movetagged(request, target_id, newLinkTo, uuid):
    '''execute move of a tagged item. /movetagged/ URL target.'''
    # urls.py argument is always a string
    rutils.starttime_reset(request)    
    targetNode = Notes.nodes.get(pmid=target_id)
    # tagged item, when moved, is always for a new parent
    # "adopt child" mechanism

    #targetNode is Note getting new parent
    target_id = str(targetNode.pmid)
    targetTitle = targetNode.title
    mode = 'replace' 
    relType = 'child_of'
    pmidLinkTo = newLinkTo
    selectedLinkTo = 0
    if targetNode.parents(request.user.username) == []:
        ## needs to be -9 if it's a root node
        origLinkToID = -9
    else:
        parent_node = targetNode.parents(request.user.username)[0] 
        origLinkToID = parent_node.pmid

    origRelType = 'child_of'
    # movetagged ==> items.execute_changerel
    status = execute_changerel(request, targetNode, mode, relType, pmidLinkTo,\
                               selectedLinkTo, origLinkToID, origRelType, request.session[uuid]['fetch_root'])

    ##  error handling should apply to any other changerel well
    if status == "pmidLinkTo does not exist":
        logThis(request, "FAILED: MOVETAGGED, pmidLinkTo not found   %s %s %s => %s >>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % (relType, mode, targetNode.pmid, pmidLinkTo))
        return views.universal_return(request, 'movetagged', origLinkToID, False, uuid)
    
    if origLinkToID != -9:
        mp_to_reindex = rutils.check_and_archive(request, parent_node) # movetagged

    targetNode.tagged_page = False
    targetNode.save()

    target_parents = targetNode.parents(request.user.username)

    rutils.logThis(request, "EXIT: MOVETAGGED  %s %s %s => %s >>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % (relType, mode, targetNode.pmid, pmidLinkTo))
    return views.universal_return(request, 'movetagged',  target_parents[0].pmid, False, uuid)
    
########################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def adopt_item(request, target_id, uuid):
    '''draw the page where user can pick a child to adopt'''
    all_worksets_list = rutils.get_all_worksets(request)
    target_node = Notes.nodes.get(pmid=target_id)
    found_items = list(Notes.nodes.filter(tagged_page=True, created_by=request.user.username))
    context = {'workset_list':all_worksets_list,
               'tagged_pages':found_items,
               'parent_node':target_node,
               'titleCrumbBlurb':'Adopt '+str(target_node.pmid), 'uuid':uuid
    }
    return render(request, 'adopt.html', context)

#####################################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def add_meeting(request,mmaster_pmid, uuid):
    '''add meeting to a meeting_master'''
    rutils.starttime_reset(request)

    mmaster = Notes.nodes.get(pmid=mmaster_pmid)
    new_pmid = rutils.get_next_pmid(request)
    rutils.logThis(request, "ENTER: ADD_MEETING - adding new meeting %s to meeting_master %s <<<<<<<<<<<<<<<<" % (new_pmid, mmaster_pmid))
    if "meeting" in mmaster.title.lower():
        new_title = date.today().isoformat()+" "+mmaster.title[:-1]  # drop the final "s" in "meetings" for child
    else:
        new_title = date.today().isoformat()+" "+mmaster.title+ " meeting"
    # was new_notetext = '<p>'+date.today().strftime("%m/%d/%Y")+'</p>\n'
    new_notetext = '<p>'+date.today().strftime("%Y-%m-%d")+'</p>\n'
    meeting_new = Notes(pmid=new_pmid, title=new_title, created_by=request.user.username)
    meeting_new.dtCreated = datetime.now(pytz.timezone('US/Pacific'))
    meeting_new.dtModified = meeting_new.dtCreated
    meeting_new.tagged_page = False
    meeting_new.hasNote=True  # ok, a little premature, but it saves a db operation
    new_workset_name = mmaster.get_workset_name()
    meeting_new.save()
    # noteText is stored in ES, not the node
    es_sup.EScreateDocument(request, meeting_new, new_notetext)
    mmworkset_node = mmaster.ws_belongs.single()    

    # link to the Workset node ##################
    meeting_new.ws_belongs.connect(mmworkset_node)
    rutils.logThis(request,"       meeting workset: %s" % mmworkset_node.name)

    # create relationship to parent
    # find all direct kids of meeting_master, Depth=1
    mmaster_and_kids = mmaster.children_and_self_no_arc(request.user.username, 1)
    meeting_parent = 'nix'
    for m in mmaster_and_kids:
        # see if meeting_master has child with title=today's year
        if m.title == date.today().strftime("%Y"):
            meeting_parent=m
            break
    # meeting_parent = year header item ################################
    if meeting_parent == 'nix':
        # create a meeting_master child with title = today's year
        mp_pmid = rutils.get_next_pmid(request)
        meeting_parent = Notes(pmid=mp_pmid, title=date.today().strftime("%Y"), noteText='', created_by=request.user.username)
        meeting_parent.dtCreated = datetime.now(pytz.timezone('US/Pacific'))
        meeting_parent.dtModified = meeting_new.dtCreated
        meeting_parent.save()
        
        # set the "year parent" workset
        meeting_parent.ws_belongs.connect(mmworkset_node)
        meeting_parent.child_of.connect(mmaster)
        # index meeting_parent in ES
        es_sup.EScreateDocument(request, meeting_parent, None)
    #####################################################################

    meeting_new.child_of.connect(meeting_parent)
    meeting_new.save()

    # add to the recent list
    rutils.add_recent(request, meeting_new.pmid)
    
    rutils.logThis(request, "EXIT: ADD_MEETING       New item created: %s >>>>>>>>>>>>>>>>>>>" % str(meeting_new.pmid))    
    return HttpResponseRedirect('/relix/%s/qnote/%s' % (meeting_new.pmid,uuid) )


#####################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def new_shortlist_item(request):
    '''quick create new shortlist item, from shortview'''
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: NEW_SHORTLIST_ITEM  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        Sform = newShortlistItemForm(request.POST)
        # check whether it's valid:
        if Sform.is_valid():
            parent_pmid = Sform.cleaned_data['new_shortitem_parent_pmid']
            title = Sform.cleaned_data['new_shortitem_title']
            priority = Sform.cleaned_data['new_shortitem_priority']
            parent_node = Notes.nodes.get(pmid=parent_pmid)            
            parent_workset_node = parent_node.ws_belongs.single()
            new_pmid = rutils.get_next_pmid(request)
            rutils.logThis(request, "adding new shortlist item %s to parent %s, workset %s <<<<<<<<<" \
                           % (new_pmid, parent_pmid, parent_workset_node.name))

            note_new = Notes(pmid=new_pmid, title=title, noteText='', created_by=request.user.username, priority=priority)
            note_new.dtCreated = datetime.now(pytz.timezone('US/Pacific'))
            note_new.dtModified = note_new.dtCreated 
            note_new.save()
            x = note_new.child_of.connect(parent_node)
            
            # attach the parent Work_set to the node #######################
            #   ALTHOUGH.... Work_set.name should always be= "personal" for shortlist. 
            y = note_new.ws_belongs.connect(parent_workset_node )
            rutils.logThis(request, "       new shortlist node %s workset: %s <<<<<<<<<" % (new_pmid, note_new.ws_belongs.single()))
            # connect to shortlist_node, & set shortlist_marker = TRUE
            shortlist_node = Group.nodes.get(group_name="shortlist", created_by=request.user.username)            
            note_new.group_items.connect(shortlist_node)
            note_new.shortlist_marker = True
            note_new.save()

            # add to the recent list
            rutils.add_recent(request, note_new.pmid)            

            # add record to Elasticsearch ES
            es_sup.EScreateDocument(request, note_new, '')
            rutils.logThis(request, "            Done creating "+str(note_new.pmid))
            return HttpResponseRedirect(reverse('relix:shortview'))
        else:
            ##form is invalid
            rutils.message(request, '       invalid new_shortlist_item form')
            rutils.logThis(request, 'EXIT: NEW_SHORTLIST_ITEM  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')            
            return HttpResponseRedirect(reverse('relix:shortview'))
    # if a GET (or any other method) we'll create a blank form
    else:
        sform =  newShortlistItemForm()
        rutils.message(request, "       not a post to new_shortlist_item")
        rutils.logThis(request, 'EXIT: NEW_SHORTLIST_ITEM  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
        return HttpResponseRedirect(reverse('relix:shortview'))
    
##########################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def new_gridgroup(request):
    '''quick create new grid group, from grid group admin'''
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: NEW_GRIDGROUP ITEM CREATE  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        Sform = newGridGroupForm(request.POST)
        # check whether it's valid:
        if Sform.is_valid():
            rutils.logThis(request, "            sform keys: %s:"+ str(Sform.cleaned_data.keys()))
            name = Sform.cleaned_data['new_gridgroup_name']
            order = Sform.cleaned_data['new_gridgroup_order']
            color = Sform.cleaned_data['new_gridgroup_color']
            workset = Sform.cleaned_data['workset']
            
            rutils.logThis(request, "adding new gridgroup  %s, workset %s <<<<<<<<<" \
                           % (name, workset))
            existing_gg = GridGroup.nodes.get_or_none(grid_group_name=name,work_set=workset,created_by=request.user.username)
            if existing_gg == None:
                group_new = GridGroup(grid_group_name=name, grid_group_order=order, grid_group_color=color,\
                                      work_set=workset, \
                                      created_by=request.user.username)
                group_new.save()
                rutils.logThis(request, "            Done creating grid group:"+ name)
            else:
                existing_gg.grid_group_order=order
                existing_gg.grid_group_color=color
                existing_gg.save()
                rutils.logThis(request, "            Done updating existing grid group:"+ name)
                
            
            return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))
        else:
            ##form is invalid
            rutils.message(request, '       invalid newGridGroupForm')
            rutils.logThis(request, 'EXIT: NEW_GRIDGROUP  invalid form    <<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
            return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))
    else:
        # if a GET (or any other method) we'll redirect to gridgroups (shouldn't ever have GET request here, however...
        rutils.message(request, "       not a post of new_GridGroupForm")
        rutils.logThis(request, 'EXIT: NEW_GRIDGROUP  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
        return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))

# assign grid item notes to grid groups  ############################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def assign_gridgroup (request):
    '''receive post for item assignments to grid groups'''
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: ASSIGN_GRIDGROUP   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        Sform = GGassignForm(request.POST)
        
        # check whether it's valid:
        if Sform.is_valid():
            workset = Sform.cleaned_data['workset']
            ass_length = Sform.cleaned_data['ass_length']
            rutils.logThis(request, "     ...valid form,  workset=%s, ass_length=%s ..." % (workset, ass_length))            
            # assign grid items table can vary in # of rows

            # all items in the table get reassigned each time. So safe to drop all connections to the grid group.
            #  this must be done BEFORE new note-to-grid group assignments are made (i.e., not in the loop below)
            ws_ggs = GridGroup.nodes.filter(work_set=workset, created_by=request.user.username)
            for wsg in ws_ggs:
                wsg.gg_members.disconnect_all()
            
            for c in range(1,ass_length+1):
                note_pmid = Sform.cleaned_data['ass_pmid_'+str(c)]
                gg_order = Sform.cleaned_data['gg_order_'+str(c)]
                if gg_order != 0:
                    # don't try to use the work_set property on NOTES!
                    note_node = Notes.nodes.get(pmid=int(note_pmid),  created_by=request.user.username)
                    gg_node = GridGroup.nodes.get(grid_group_order=str(gg_order), work_set=workset, created_by=request.user.username   )
                    note_node.gg_belongs.disconnect_all()
                    note_node.gg_belongs.connect(gg_node)
                    gg_node.gg_members.connect(note_node)
                    note_node.save()
                    gg_node.save()
                    rutils.logThis(request, "     %s : Note %s added to GG %s  <<<<<<<<<"  % (c, note_node.pmid, gg_node.grid_group_name))

            rutils.logThis(request, "            Done assigning")
            return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))
        else:
            ##form is invalid
            rutils.message(request, '       invalid newGridGroupForm')
            rutils.logThis(request, 'EXIT: ASSIGN_GRIDGROUP  invalid form    <<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
            return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))
    else:
        # if a GET (or any other method) we'll redirect to gridgroups (shouldn't ever have GET request here, however...
        rutils.message(request, "       not a post of new_GridGroupForm")
        rutils.logThis(request, 'EXIT: ASSIGN_GRIDGROUP  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
        return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))

    rutils.logThis(request, 'EXIT: ASSIGN_GRIDGROUP   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
    return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':workset}))


#delete grid group #########################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def delete_gridgroup(request, grid_group_name, gworkset):
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: DELETE_GRIDGROUP   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    delete_node = GridGroup.nodes.first(grid_group_name=grid_group_name, work_set=gworkset,created_by=request.user.username)
    delete_node.gg_members.disconnect_all()
    delete_node.delete()
    # seems to automatically do the right thing with the incoming gg_belongs relationship
        
    rutils.logThis(request, 'EXIT: DELETE_GRIDGROUP   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
    return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':gworkset}))

    
    
#move grid group#########################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def move_gridgroup(request, grid_group_name, gworkset, direction):
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: MOVE_GRIDGROUP   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    # to start, make sure the set of grid groups are numbered consecutively
    ws_ggroup = GridGroup.nodes.filter(work_set=gworkset, created_by=request.user.username).order_by('grid_group_order')
    
    move_nodes = GridGroup.nodes.filter(grid_group_name=grid_group_name, work_set=gworkset,created_by=request.user.username)
    # b/c we don't have a unique ID on grid groups, we might very rarely have two with identical names. 
    for mn in move_nodes:
        if direction=='up':
            # swap order with the grid group above  (i.e., has a lower number) than you
            orig_order = int(mn.grid_group_order)
            if orig_order != 1:
                above_me = GridGroup.nodes.get( work_set=gworkset,created_by=request.user.username, grid_group_order = str(orig_order-1))
                above_me.grid_group_order = str(orig_order)
                above_me.save()
                mn.grid_group_order = str(orig_order-1)
                mn.save()
        elif direction=='down':
            # swap order with the grid group above  (i.e., has a lower number) than you
            orig_order = int(mn.grid_group_order)
            if orig_order != len(ws_ggroup):
                below_me = GridGroup.nodes.get( work_set=gworkset,created_by=request.user.username, grid_group_order = str(orig_order+1))
                below_me.grid_group_order = str(orig_order)
                below_me.save()
                mn.grid_group_order = str(orig_order+1)
                mn.save()
            
    rutils.logThis(request, 'EXIT: MOVE_GRIDGROUP   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
    return HttpResponseRedirect(reverse('relix:gridgroups',kwargs={'workset':gworkset}))

    
# add root node #########################################################################


@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def addRootNode(request):
    '''create a new top-level, parentless node'''
    newPMID = rutils.get_next_pmid(request)
    rutils.logThis(request, "adding new top level node,  %s <<<<<<<<<" % (newPMID))
    note_new = Notes(pmid=newPMID, title="NewItem", noteText='', created_by=request.user.username)
    note_new.dtCreated = datetime.now(pytz.timezone('US/Pacific'))
    note_new.dtModified = note_new.dtCreated

    note_new.save()

    # add to the recent list
    rutils.add_recent(request, note_new.pmid)
    
    # add record to Elasticsearch ES
    es_sup.EScreateDocument(request, note_new, None)

    return HttpResponseRedirect('/relix/%s/edit/n/-15' % note_new.pmid)

##############################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def addNote(request, parent_id, uuid):
    '''create a new note, child_of parentID'''
    #not add_note
    newPMID = rutils.get_next_pmid(request)
    rutils.logThis(request, "adding child %s to parent %s <<<<<<<<<" % (newPMID, parent_id))
    parentNode = Notes.nodes.get(pmid=parent_id)
    note_new = Notes(pmid=newPMID, title='', noteText='', created_by=request.user.username)
    note_new.dtCreated = datetime.now(pytz.timezone('US/Pacific'))
    note_new.dtModified = note_new.dtCreated 
    note_new.save()

    # add to the recent list
    rutils.add_recent(request, note_new.pmid)
    
    x = note_new.child_of.connect(parentNode)
    if parentNode.ws_belongs.all() != []:
        y = note_new.ws_belongs.connect(parentNode.ws_belongs.all()[0])
    
    note_new.save()
    # add record to Elasticsearch ES
    es_sup.EScreateDocument(request, note_new, '')
    
    rutils.logThis(request, "New item pmID:"+str(note_new.pmid))
    #return HttpResponseRedirect('/relix/%s/edit/n/%s/' % (note_new.pmid, request.session[uuid]['fetch_root']))
    return HttpResponseRedirect('/relix/%s/edit/n/%s' % (note_new.pmid, uuid))

###################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def deleteNote(request, target_id, uuid):
    target_id = int(target_id)
    '''delete an item, return to then view fetchRoot or parent'''

    targetNode = Notes.nodes.get(pmid=target_id)
    kid_pmids = targetNode.children_ids_w_arc()

    if kid_pmids != []:
        warn_string = "ERROR. %s has children, cannot delete." % target_id        
        rutils.logThis(request, warn_string + " <<<<<<<<<" )
        rutils.message(request, warn_string)
        utemp = request.session['umessage'] 
        request.session['umessage'] = utemp + warn_string
        # lockfile is set when you enter notes_edit, i.e., where the "delete" link is offered
    else:    
        rutils.logThis(request, "deleting  %s and removing from ES <<<<<<<<<" % target_id)
        # once you delete the node, you can't do logic on the node?
        
        # BLH 4/11/2018 ES delete requires a delay, I suspect. Deleting a searched-for item can lead to
        #  "PMID not found error", probably b/c the re-submitted search finds the item in ES before it
        #  is deleted. Status is immediately "successful", however. Maybe just log such errors (ES_sup, 434)
        resp = es_sup.ESdeleteDocument(request, target_id)
        rutils.logThis(request, "ES deletion of %s: %s" % (target_id, resp))
        targetNode.delete_me_and_relationships(request.user.username)
        
        rutils.message(request, "deleted %s" % target_id)
        rutils.logThis(request, "DELETED ====>  %s <================ " % target_id)

    # either way, delete the lockfile
    lockfile = request.user.username+'_'+str(target_id)+'.lck'
    if os.path.isfile(LOCKFILES+lockfile):
        os.remove(LOCKFILES+lockfile)

    #######################################################
    # return to view [deleteNote]
    #######################################################
    return views.universal_return(request, 'deleteNote', target_id, True, uuid)


########################################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def deleteRel(request, target_id, relatedID, relType, uuid='no_uuid_passed'):
    '''delete a specific relationship'''
    targetNode = Notes.nodes.get(pmid=target_id)
    relatedNode = Notes.nodes.get(pmid=relatedID)
    if relType == 'child_of':
        targetNode.child_of.disconnect(relatedNode)
    elif relType == 'rel_content':
        targetNode.rel_content.disconnect(relatedNode)
    elif relType == 'relates':
        targetNode.relates.disconnect(relatedNode)
    elif relType == 'prev_version':
        targetNode.prev_version.disconnect(relatedNode)
    else:
        rutils.logThis(request, "Unsupported relationship type: %s" % relType)
    targetNode.save()
    rutils.logThis(request, "relationship deleted: %s = %s => %s" % (target_id, relType, relatedID))

    return views.universal_return(request, 'deleteRel',  target_id, True, uuid)

#############################################################################
