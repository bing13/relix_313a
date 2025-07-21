##### VIEWS.PY   [  RELIX   ]             ######################################################
# 2020-05-30: initial port to django3
# 2021-03-23: port to new VM, ubuntu 20.04
# 2021-09-06: death to return_me_to, return_target
# 2021-11-20: split out many functions to items.py, rutils.py, es_sup.py
# 2023-10-08: updated OS, django, neomodel, etc. (not neo4j db, yet)
# 2023-12-23  updates related to neo4j v5, django upgrade
#############################################################################
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.utils import timezone, html
from django.db.models.functions import Lower
from django.urls import reverse_lazy, reverse
#from django.db import transaction

from datetime import datetime, date
import pytz, time, json, requests,glob, pickle, os, re, collections
from uuid import uuid4
import urllib.parse as urlparse
from operator import itemgetter, attrgetter

# https://pypi.org/project/django-multifactor/
# to add token, visit
#     https://relix.bernardhecker.com/admin/multifactor/

from multifactor.decorators import multifactor_protected

#from neo4j import GraphDatabase, basic_auth
from neomodel import db, DoesNotExist

from relix.forms import LoginForm, itemEditForm, todayForm, NotesStandardForm, newShortlistItemForm
from relix.models import Notes, Group, Work_set, People, GridGroup, Team

from . import es_sup, rutils, items, rinteract

##this is not a comment:
#pylint: disable=line-too-long, trailing-whitespace, invalid-name

LOCKFILES = '/tau/dj313/relix3/lockfiles/'
PMID_COUNTER_FILE = '/tau/dj313/relix3/pmid_counter.txt'
DDX = 20 # default depth traversal
RELATIONSHIP_TYPES = ["child_of", "relates", "prev_instance", "rel_content"]

#RETURN_CODES = {'-10':'recent', '-11':'grid', '-12':'today', '-13':'search', '-14':'list tagged', '-15':'my root', '-16':'qnote', '-17':'quicksearch', '-18':'people', '-19':'lock files list','-20':'shortview', '-21':'meeting view'}

#GRID_ORDER_LIST = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

############### A U T H ################################################
# now in settings.py #'bolt://USR:PWD@localhost:7687'
########################################################################

### BEGIN >>multiple<< ITEMS EDIT FORM #################################################
@login_required()
#@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def items_edit(request):
    '''receive display list multiple items form to process edits'''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: ITEMS_EDIT  <<<<<<<<<<<<<<<<<<<<<<<<<<<")
    ###handle moves#######
    if request.method == 'POST':
        # receive POST and create a form instance and populate it with data from the request:
        Sform = itemEditForm(request.POST)
        # check whether it's valid:
        if Sform.is_valid():
            rutils.logThis(request, "       itemsUpdate: valid form======")
            ie_to_reindex = []
            #don't know why request.POST.getlist['itemSelect'] didn't work
            # shoulda been request.POST.getlist('itemSelect')?
            for z in request.POST.lists():
                #rutils.logThis(request, ">>>> PASSED: %s " % str(z) )
                #find selected items - common to all operations
                if z[0] == 'itemSelect':
                    selected_items = z[1]
            selected_target_nodes = list(Notes.nodes.filter(pmid__in=selected_items))
            uuid = Sform.cleaned_data['uuid']
            
            ################################################
            ## execute the actions:
            ################################################
            
            ## move action ####################################################
            if Sform.cleaned_data['pmid_manual'] != None:
                moveTarget = Sform.cleaned_data['pmid_manual']
            else:
                moveTarget = Sform.cleaned_data['grab']

            if moveTarget != None:
                ## valid move action ##
                rutils.logThis(request, "       moving %s to %s" % (str(selected_items), moveTarget))
                for target_node in selected_target_nodes:
                    mode = 'replace'
                    relType = 'child_of'
                    pmidLinkTo = moveTarget
                    selectedLinkTo = 'nix'
                    
                    ##careful fetchRoot= -9 is used for both searches, and for trunk.  ( items_edit )
                    # if request.session.setdefault('fetchRoot',-9) != -9 or request.session['fetchType'] == 'search':
                    if request.session[uuid].setdefault('fetch_root',-9) != -9 or request.session[uuid]['fetch_type'] == 'search':
                        if len(target_node.parents(request.user.username)) > 0:
                            origLinkToID = target_node.parents(request.user.username)[0].pmid
                        else:
                            #target_node is a trunk node and has no parents
                            origLinkToID = -9
                    else:
                        # we're moving an item off the trunk
                        origLinkToID = -9
                    origRelType = 'child_of'

                    #####################################
                    # [here:items_edit] items.execute_changerel (triggers isort rebuild, etc) #################
                    ## Note: items.execute_changerel does the updating of workset
                    status = items.execute_changerel(request, target_node, mode, relType, pmidLinkTo, \
                                               selectedLinkTo, origLinkToID, origRelType, \
                                               request.session[uuid]['fetch_root'] )
                    target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))
                    target_node.save()
                    ie_to_reindex += rutils.check_and_archive(request, target_node)  #items_edit 0
                    
                    # need to check if status should be updated on original parent
                    if origLinkToID != -9:
                        old_parent_node = Notes.nodes.get(pmid=origLinkToID)
                        # needed, since old_parent won't be picked up below b/c it's not related
                        #      to the target node any more
                        ie_to_reindex += rutils.check_and_archive(request, old_parent_node)  #items_edit 1
                    
            ## priority_change action ###############################################
            ## '-99', string value, is correct for no change in priority and status
            if Sform.cleaned_data['priority_change'] != '-99':
                for target_node in selected_target_nodes:
                    target_node.priority = str(Sform.cleaned_data['priority_change'])
                    target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))                    
                    target_node.save()
                rutils.message(request, 'Priority changed to %s on %s' %  (Sform.cleaned_data['priority_change'], str(selected_items)))
            ## status_change action ################################################
            if Sform.cleaned_data['status_change'] != '-99':
                for target_node in selected_target_nodes:
                    target_node.status = str(Sform.cleaned_data['status_change'])
                    target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))
                    target_node.save()
                    ie_to_reindex += rutils.check_and_archive(request, target_node) #items edit 2
                rutils.message(request, 'Status changed to %s on %s' % (Sform.cleaned_data['status_change'], str(selected_items)))

            ##   REFRESH ELASTICSEARCH, w/ node properties;
            ##    Note: itemsEdit actions may change: dtModified, parent, priority, and/or status AND ARCHIVED
            ##       BUT... we want the refresh action to catch PEOPLE as well....
            ##          of these, archvie, priority & status matter to ES.
            ##          In search, parentage is handled via scope
            
            # ES_SUP BULK UPDATE OF ALL SELECTED NODES plus ANY FROM CHECK_AND_ARCHIVE ######################
            pmids_to_reindex = set()
            for x in selected_target_nodes:
                pmids_to_reindex.add(x.pmid)
            for y in ie_to_reindex:
                pmids_to_reindex.add(y)
            reindex_these_nodes = Notes.nodes.filter(pmid__in=list(pmids_to_reindex))
            (status, success) = es_sup.ESbulkItemsEditUpdate(request, reindex_these_nodes)
            rutils.logThis(request,"       IEbulk status=%s, success=%s" % (status, success))
            rutils.message(request, "       items_edit saved: %s" % str(selected_items))
            
            #######################################################
            # RETURN TO VIEW [items_edit]
            #######################################################
        
            if moveTarget != None:
                scrollItem = moveTarget
            else:
                scrollItem = -9

            rutils.logThis(request, "EXIT: ITEMS_EDIT >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            # the 'True' parameter on the end forces a refresh
            return universal_return(request, 'items_edit', scrollItem, True, uuid)

        else:
            ##form is invalid ##############################
            erx = str(Sform.errors)
            rutils.logThis(request, "       ERROR in items_edit form: %s" % erx)
            rutils.message(request, 'ERROR:%s' % (erx))
            # (items_edit) 
            #PROBLEM: if for is invalid, we don't have the passed UUID
            return HttpResponseRedirect(reverse('relix:home'))

    ## END ITEMS_EDIT #########################################################################
        
#######################################################################################################        
### NOTES_EDIT via  record_edit.html                ###################################################
#######################################################################################################
@login_required()
#@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def notes_edit(request, target_id, qnote='n',return_target="-9", uuid='no_ne_uuid'):
    '''custom form for notes mods. 
       return_target is a former URL argument, now vestigial. Most often set to fetchroot (below))

      UI is same as QNote. Will return to fetch_root unless FETCH_TYPE = 'popup' when it's a pop edit
        which simply closes the popup window, and doesn't "return" anywhere
    '''
    # notes_edit, not note_edit
    
    rutils.starttime_reset(request)    
    rutils.logThis(request, "ENTER: NOTES_EDIT <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")

    try:
        target_node = Notes.nodes.get(pmid=target_id)
    except:
        rutils.logThis(request, "ERROR - PMID not found: %s" % target_id)
        rutils.message(request, "ERROR - PMID not found: %s" % target_id)
        rutils.logThis(request, "EXIT: NOTES_EDIT >>>>>>>>>>>>>>>>>>>>>>>>>> ")        
        return universal_return(request, 'notes_edit', target_id, True)

    rutils.add_recent(request, target_id)
    
    if target_node.created_by != request.user.username:
        rutils.message(request, "User %s not owner of node %s, edit aborted" % (request.user.username, target_id))
        rutils.logThis(request, "      ERROR: User not owner of record. ")
        rutils.logThis(request, "EXIT: NOTES_EDIT >>>>>>>>>>>>>>>>>>>>>>>>>> ")        
        return HttpResponseRedirect(reverse('relix:home'))
    
    if request.method == 'POST':
        # create a form instance and populate it with data from the request
        #Sform = NotesModelForm(request.POST, instance=target_node)
        Sform = NotesStandardForm(request.POST)
        # ModelForm didn't seem to agree with neomodel 3.2.9, and the advice seemed to be
        #   don't roll back.  So back to manual form handling.
        #   Pull the cleaned_data, then populate the node
        
        # check whether it's valid:
        if Sform.is_valid() and Sform.cleaned_data['pmid'] == target_node.pmid:
            rutils.logThis(request, "      notesUpdate: valid form======")
            # fields not edited: pmid, dtCreated, dtModified, created_by, isort

            ##bh3 no idea what this was for, unless to sense a totally blank form?
            if Sform.cleaned_data['adorn'] == '': Sform.cleaned_data='0'
            
            # https://docs.djangoproject.com/en/1.11/topics/forms/modelforms/#the-save-method
            #bh3 Sform.save() 
            
            target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))
            target_node.title = Sform.cleaned_data['title']
            target_node.priority = Sform.cleaned_data['priority']
            target_node.status = Sform.cleaned_data['status']
            target_node.topSort = Sform.cleaned_data['topSort']
            target_node.sectionhead = Sform.cleaned_data['sectionhead']
            # removed 2 lines 2021-02-14, people now assigned on list views
            #target_node.assigned_to_peoples = Sform.cleaned_data['assigned_to_peoples']
            #target_node.involves_peoples = Sform.cleaned_data['involves_peoples']
            target_node.jumplink = Sform.cleaned_data['jumplink']
            target_node.jumplabel = Sform.cleaned_data['jumplabel']            
            target_node.jumpcolor = Sform.cleaned_data['jumpcolor']
            target_node.gridItem = Sform.cleaned_data['gridItem']
            #target_node.grid_order = Sform.cleaned_data['grid_order']
            submitted_work_set = Sform.cleaned_data['work_set']
            target_node.is_qnote = Sform.cleaned_data['is_qnote']
            target_node.tagged_page = Sform.cleaned_data['tagged_page']
            target_node.shortlist_marker = Sform.cleaned_data['shortlist_marker']
            target_node.start_folded = Sform.cleaned_data['start_folded']
            target_node.meeting_master = Sform.cleaned_data['meeting_master']            
            target_node.adorn = Sform.cleaned_data['adorn']
            target_node.reminder_date = Sform.cleaned_data['remind_date']
            target_node.webpage_set = Sform.cleaned_data['webpage_set']            

            # Attempting to deflate property 'reminder' on <Notes: reminder dates> of class 'Notes':
            #     datetime object expected, got <class 'datetime.date'>.
            
            
            ###################
            uuid = Sform.cleaned_data['uuid']
            return_me_to = Sform.cleaned_data['return_me_to']

            ##############################
            # Mobile handling 5/21/2023
            window_width = Sform.cleaned_data['windowsize']
            mobile_input = Sform.cleaned_data['mobile_input']
            #rutils.logThis(request, "      width:%s  mobile_input:%s" % (window_width,mobile_input))

            ### NOTETEXT | MOBILE_INPUT switching  ################
            #target_node.noteText = Sform.cleaned_data['noteText']
            if window_width > 700:
                externalized_noteText = Sform.cleaned_data['noteText']
            else:
                externalized_noteText = mobile_input
            #
            target_node.image_list = Sform.cleaned_data['image_list']


            
            ## ERROR CHECKING ###################################
            if uuid not in list(request.session.keys()):
                uuid = str(uuid4())
                # best we can do if we want to avoid an error
                # set vsession
                sdict = {'fetch_root':-9, 'fetch_type':'tree'}
                rutils.vsession(request,'new',sdict,uuid)
            if 'fetch_type' not in list(request.session[uuid].keys()):
                rutils.vsession(request,'update',{'fetch_type':'tree'},uuid)
                rutils.logThis(request, "      ERROR: fetch_type not defined(ne)")
                rutils.message(request, "fetch_type not defined")                
            if 'fetch_root' not in list(request.session[uuid].keys()):
                rutils.vsession(request,'update',{'fetch_root':-9},uuid)
                rutils.logThis(request, "      ERROR: fetch_root not defined(ne)")
                rutils.message(request, "fetch_root not defined")
            ######################################################
                
            if return_me_to == '-16':
                # it's a pop-up edit window, and needs to be closed by universal_return.
                return_target = return_me_to
            elif return_target == '-9':
                if request.session[uuid]['fetch_type'] == 'search':
                    return_target = '-13'
                else:
                    return_target = request.session[uuid]['fetch_root']
            rutils.logThis(request, "      === target_id=>%s, return_me_to=>%s, return_target=>%s, fetch_root=>%s, fetch_type=>%s" % (target_id, return_me_to, return_target,request.session[uuid]['fetch_root'],request.session[uuid]['fetch_type'] ))

            ## put display_workset into the vsession
            request.session[uuid]['display_workset']=submitted_work_set 
            rutils.vsession(request,'update',{},uuid) # don't need dict for update

            ## HASNOTE FIELD ###########################################################
            if len(externalized_noteText) > 1 or len(Sform.cleaned_data['image_list']) > 8:
                target_node.hasNote = True
            else:
                target_node.hasNote = False



            ##### STASH TEXT FROM THE NODE #############################
            rinteract.stash_note(request,target_node.pmid,externalized_noteText)
            
            ##### SAVE TO DB ALL FIELDS FROM THE NODE ##########################
            # noteText is externalized above
            target_node.save()
                                            
            #########################################################################
            ## shortlist_marker updating
            
            shortlist_node = Group.nodes.get(group_name="shortlist", created_by=request.user.username)
            # check to see if relationships reflect checkbox submitted
            if target_node.shortlist_marker and not target_node.group_items.is_connected(shortlist_node):
                target_node.group_items.connect(shortlist_node)
            elif target_node.shortlist_marker == False and target_node.group_items.is_connected(shortlist_node):
                target_node.group_items.disconnect(shortlist_node)

            
            ## WORK_SET ######in notes_edit ########################################################
            #    Qnote should not still be set by the time an item is moved. ( pathologcial case, if it occurs)
            #       also tried: target_node.parents(request.user.username) != []:
            #           but this prevented changing workset on a trunk node

            # so fresh qnotes bypass this? what if user enters a workset in the notes edit form? Qvd
            
            if qnote != 'q':
                total_changed = rutils.set_workset_with_descent(request, target_node, submitted_work_set )
                rutils.logThis(request, "       Work_set rel changed: %s" % total_changed)
                if total_changed != 'no workset change':
                    rutils.message(request, "       %s" % total_changed )

            ## misc ###################################################################
            nix = rutils.rebuild_jumplinks(request)
            
            #archive processing #######################################################
            #   check if node status is done, pending done, or canceled; include ancestors
            ne_to_reindex = rutils.check_and_archive(request, target_node) # notes_edit

            
            ## ES updating #########################################################################
            # for the note_edit target_node
            status = es_sup.ESupdateDocument(request, target_node, externalized_noteText)
            # for any nodes from check_and_archive processing,
            #    i.e., bang-on archived, priority, or status changes, like items_edit
            #          (no note_text, title, etc changes)
            #

            # this attempts to safely invoke an MFA prompt if it is needed, to prevent an error in the steps below.
            #   Not clear exactly where the error is triggered, if MFA has expired.
            rutils.safe_mfa_check(request)
            caa_nodes = Notes.nodes.filter(pmid__in=ne_to_reindex)
            #  # THROWS AN ERROR on next line if MFA hits during Update  2023-08-13 # #
            if len(caa_nodes) != 0:
                (status, success) = es_sup.ESbulkItemsEditUpdate(request, caa_nodes)
            
            # qnote ################################################################################
            # if it's a qnote, add it to pending moves session var (now that we have the real title)
            # safe, b/c qnote == 'q' only when the qnote is first created
            if qnote == 'q':
                # add to tagged_pages
                target_node.tagged_page = True
            target_node.save()

            #### remove the lockfile!  #########################################
            lockfile = LOCKFILES+request.user.username+'_'+str(target_id)+'.lck'
            if os.path.isfile(lockfile):
                os.remove(lockfile)
            else:
                rutils.logThis(request, "notes_edit ERROR! lockfile did not exist! ID: %s" % target_id)
                rutils.message(request, 'Lockfile did not exist! %s' % target_id)
                request.session['umessage'] = 'Lockfile did not exist! %s' % target_id
                
            ###################################################################################
            # RETURN FROM NOTES_EDIT, valid form done processing
            ###################################################################################
            rutils.logThis(request, "EXIT: NOTES_EDIT >>>>>>>>>>>>>>>>>>>>>>>>>> ")            
            return universal_return(request, 'notes_edit', target_id, True, uuid)
 
        else:
            ##FORM IS INVALID #############################################################
            rutils.logThis(request, "       ERROR: INVALID FORM ===============")

            umessage = request.session.setdefault('umessage','')
            
            #erx = str(Sform.errors)
            erx = str(Sform.errors.as_data())
            rutils.logThis(request, "      notesUpdate invalid form: %s" % erx)
            rutils.message(request, '%s:%s' % (target_id, erx))
            umessage += 'Invalid form! %s   ' % erx 
            
            if qnote == 'q':
                is_qnote='y'
            else:
                is_qnote='n'
            #remove the lock file, so you can return and edit the file.

            lockfile = LOCKFILES+request.user.username+'_'+str(target_id)+'.lck'
            if os.path.isfile(lockfile):
                os.remove(lockfile)
            else:
                rutils.logThis(request, "      notes_edit ERROR! lockfile did not exist! ID: %s" % target_id)
                rutils.message(request, 'Lockfile did not exist! %s' % target_id)
                umessage  += 'Lockfile did not exist! %s   ' % target_id

            # any data entered will be lost. that's just wrong, given the transgression is so small for
            request.session['umessage'] = umessage
            context = {'target_id':target_id, 'qnote':is_qnote, 'return_target':return_target }
            rutils.logThis(request, "EXIT: NOTES_EDIT >>>>>>>>>>>>>>>>>>>>>>>>>> ")
            return HttpResponseRedirect(reverse('relix:notes_edit', kwargs= context ))

    else:
        ########################################################################################
        ######## GET [note_edit]   #############################################################
        ########################################################################################        
        rutils.logThis(request, "       notesUpdate - GET form for %s ======" % target_id)
        # UUIDxxx
        rutils.vsession(request, 'dump_to_log', {}, uuid)
        rutils.vsession(request, 'update', {'editing_note':True}, uuid)
        
        # test if there is a lockfile for this PMID #############
        lockfile = LOCKFILES+request.user.username+'_'+str(target_id)+'.lck'

        if os.path.isfile(lockfile):
            rutils.logThis(request, "       LOCKFILE EXISTS >>>>>>>> notesEdit: %s" % target_id)
            rutils.message(request, 'Note Locked! %s' % target_id)
            request.session['umessage'] = 'Note Locked! %s' % target_id
            rutils.logThis(request, "EXIT: NOTES_EDIT >>>>>>>>>>>>>>>>>>>>>>>>>> ")
            # return to the fetch list ##########
            return universal_return(request, 'notes_edit', target_id, True, uuid)
        else:
            ## create the lockfile ####################
            LOCK = open(lockfile, 'w')
            LOCK.write(str(target_id)+'\t'+target_node.title+'\t'+datetime.now(pytz.timezone('US/Pacific')).isoformat())
            LOCK.close()

        #get esnoteText [note_edit] ###########################################
        esNoteTextDict = es_sup.EStextNotesGet(request, [target_id],uuid)
        rutils.logThis(request, "       GET: esNTD...")
        # = %s" % str(esNoteTextDict))

        if int(target_id) in esNoteTextDict.keys():
            thisNoteText = esNoteTextDict[int(target_id)]
        else:
            thisNoteText = ''
        
        ##      STASH EXISTING NODE  ################################
        rinteract.stash_note(request,target_node.pmid, thisNoteText)
            
        #image_list is showing up as the string 'None' in notes_edit.html
        if target_node.image_list == None:
            target_node.image_list = ''

        all_worksets_list = rutils.get_all_worksets(request)

        target_node.noteText = thisNoteText
        ##save() permanently attach the text to the node, so don't do it

        ################ TEMPORARY FIELDS #############################################
        # Attach (temporarily) to the target_node its label/workset, and people,
        #   ONLY to pass to the form. 
        target_node.work_set = target_node.get_workset_name()
        target_node.assigned_to_peoples = ','.join([ x.nickname for x in target_node.assigned_to.all() ])
        target_node.involves_peoples = ','.join([ x.nickname for x in target_node.involves.all() ])

        shortlist_node = Group.nodes.get(group_name="shortlist",created_by=request.user.username)
        target_node.shortlist_marker = target_node.group_items.is_connected(shortlist_node)

        ancestors_of_target = list(target_node.ancestorList(request.user.username))
        ancestors_of_target.reverse()

        #the constructor of form #########################
        #sform = NotesForm()  ## sform = NotesForm(target_node.__dict__)
        #sform = NotesModelForm(instance=target_node)
        sform = NotesStandardForm(target_node.__dict__)

        if uuid == 'no_ne_uuid' or uuid not in list(request.session.keys()):
            uuid = str(uuid4())
            sdict = {'fetch_root': target_node.pmid }
            # set vsession
            rutils.vsession(request,'new',sdict,uuid)
            
        # set display workset to "None" so the user isn't tempted to abandon a note edit
        #   and clear the "we're editing a note now" flag, used by es_sup
        sdict = {'display_workset':'None', 'editing_note':False}
        rutils.vsession(request, 'update', sdict, uuid)
        
        umessage = request.session['umessage']
        request.session['umessage'] = ''
        rutils.logThis(request, "EXIT: NOTES_EDIT %s  >>>>>>>>>>>>>>>>>>>>>>>" % uuid)
        context = {'form':sform, 'ix':target_node, \
                   'workset_list':all_worksets_list, \
                   'return_me_to':return_target, \
                   'target_ancestors':ancestors_of_target, \
                   'titleCrumbBlurb':'Edit: '+str(target_node.pmid)+' '+target_node.title[:30], \
                   'umessage':umessage, \
                   'floater':'no', \
                   'uuid':uuid }
        
        # don't use Jinja2, b/c it doesn't have native forms support
        return render(request, 'record_edit.html', context)

    ###### END NOTES_EDIT via RECORD_EDIT / RT_EDIT  #############################################################
    

# CANCEL_EDIT ######################################################################################
@login_required()
def cancel_edit(request, target_id, return_to_id, uuid):
    '''abandon edit. clean up lockfile, return to previous view'''
    #remove lockfile, if it exists
    
    lockfile = LOCKFILES+request.user.username+'_'+str(target_id)+'.lck'
    if os.path.isfile(lockfile):
        os.remove(lockfile)
    else:
        rutils.logThis(request, "cancel_edit: lockfile did not exist! ID: %s" % target_id)
        rutils.message(request, 'Lockfile did not exist! %s' % target_id)
        request.session['umessage'] = 'Lockfile did not exist! %s' % target_id
    
    return universal_return(request, 'cancel_edit',  target_id, False, uuid)

### BEGIN QNOTES  ###########################################################################
@login_required()
#@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def qnotes(request, target_id, uuid):
    '''pop-up custom form for QNOTE creation
       ALSO USED FOR pop-up note editing. '''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER QNOTE:  %s <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" % target_id)
    target_id = int(target_id)

    #####################
    # I don't think the UUID that's passed in matters. It's a pop-up window, so no "return"

    uuid = str(uuid4())
    # set vsession
    sdict = {'fetch_root':-9}
    rutils.vsession(request,'new',sdict,uuid)
    
    # add to the recent list
    rutils.add_recent(request, target_id)
    
    if request.method == 'POST':
        rutils.logThis(request, "QNOTES: ERROR!!!!! Nothing should post here!")
        rutils.message(request, 'QNOTES ERROR!! Nothing should post here!! %s' % target_id)
        return HttpResponseRedirect(reverse('relix:home'))
            
    else:
        ######## GET ################################################################
        if target_id != 0:
            # it's a pop-up edit of an existing note, not a new qnote
            sdict = {'fetch_type':'popup-existing-edit'}
            rutils.vsession(request,'update',sdict,uuid)
            
            target_node = Notes.nodes.get(pmid=target_id)
            title_crumb = "Edit:"+target_node.title
            treat_as_qnote = 'n'

            # TEMPORARY. DO NOT SAVE. Just for passing to template
            target_node.noteText = es_sup.ESfastGet(request, target_node.pmid)
            
            rutils.logThis(request, "       text fetched, length %s" % len(target_node.noteText))
            #image_list is showing up as the string 'None' in notes_edit.html
            if target_node.image_list == None:
                target_node.image_list = ''
            
        else:
            # it's a request to create a qnote
            sdict = {'fetch_type':'popup-qnote-create'}
            rutils.vsession(request,'update',sdict,uuid)
            
            target_id = items.add_qnote(request)
            rutils.logThis(request, "       Qnote created. GET form for %s ======" % target_id)
            target_node = Notes.nodes.get(pmid=target_id)
            #image_list is showing up as the string 'None' in notes_edit.html
            if target_node.image_list == None:
                target_node.image_list = ''
            target_node.save()

            # Data is temporary, to pass to template. DO NOT SAVE. 
            target_node.noteText = ''
            title_crumb = 'Qnote: '+str(target_node.pmid)
            treat_as_qnote = 'y'
            
        rutils.logThis(request, "       QNote - GET form for %s ======" % target_id)
        # test if there is a lockfile for this PMID #############
        lockfile = LOCKFILES+request.user.username+'_'+str(target_id)+'.lck'
        return_target = target_id
        if os.path.isfile(lockfile):
            sdict = {'fetch_type':'popup-note-locked'}
            rutils.vsession(request,'update',sdict,uuid)
            
            rutils.logThis(request, "       LOCKFILE EXISTS >>>>>>>> notesEdit: %s" % target_id)
            rutils.message(request, 'Note Locked! %s' % target_id)
            request.session['umessage'] = 'Note Locked! %s' % target_id
            
            # return to the fetch list ##########
            return universal_return(request, 'notes_edit', target_id, True, uuid)
        else:
            ## create the lockfile ####################
            LOCK = open(lockfile, 'w')
            LOCK.write(str(target_id)+'\t'+target_node.title+'\t'+datetime.now(pytz.timezone('US/Pacific')).isoformat())
            LOCK.close()       
            
        all_worksets_list = rutils.get_all_worksets(request)
        
        # TEMPORARY. DO NOT SAVE. Just for passing to template ###############################################
        target_node.assigned_to_peoples = ','.join([ x.nickname for x in target_node.assigned_to.all() ])
        target_node.involves_peoples = ','.join([ x.nickname for x in target_node.involves.all() ])

        target_node.work_set = target_node.get_workset_name()
        ######################################################################################################
        
        ancestors_of_target = list(target_node.ancestorList(request.user.username))
        ancestors_of_target.reverse()

        #the constructor of the form 
        #sform = NotesModelForm(instance=target_node)
        sform = NotesStandardForm(target_node.__dict__)        

        #lack of fetchRoot sometimes errors; added 2020-05-28
        #should be set in vsession above, commenting out 2021-11-19
        #if 'fetch_root' not in request.session[uuid]:
        #    request.session[uuid]['fetch_root']=-9

        return render(request, 'record_edit.html', \
                      {'qnote':treat_as_qnote, 'form':sform, \
                       'ix':target_node, \
                       'workset_list':all_worksets_list,\
                       'target_ancestors':ancestors_of_target, \
                       'titleCrumbBlurb':title_crumb, \
                       'floater':'yes', \
                       'uuid':uuid
                      })
    #END OF QNOTES ##

    
### BEGIN QNOTE_LIST  ###########################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def qnote_list(request):
    '''list of all qnotes'''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER QNOTE_LIST  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" )
    uuid=str(uuid4())
    sdict = { 'fetch_type':'qlist', 'fetch_root': -9 }
    #get complete list of work_sets in use
    #   TEMP: didn't include '[None]' at start
    all_worksets_list = rutils.get_all_worksets(request)
    # "None" used to get translated to "All"
    sdict['display_workset'] = 'None'
    # set vsession #############
    rutils.vsession(request,'new',sdict,uuid)

    qnote_ws = Work_set.nodes.get(name='qnote',created_by=request.user.username)
    #found_items = qnote_ws.ws_belongs.filter(created_by=request.user.username).order_by('priority','title')

    # first grab the items that have a priority > 0   
    found_items_prio = list(qnote_ws.ws_belongs.filter(created_by=request.user.username,priority__ne='0').order_by('priority','title'))
    # then grab the items with priority = 0
    found_items_no_prio = list(qnote_ws.ws_belongs.filter(created_by=request.user.username,priority='0').order_by('title'))
    found_items = found_items_prio + found_items_no_prio
    
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    lf_display, lf_list = rutils.locked_file_pmids(request)
    
    rutils.logThis(request, "EXIT: QNOTE_LIST %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(found_items))
    context = {'current_items':found_items, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':0, \
               #'return_me_to':-10, \
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'uuid':uuid, \
               'titleCrumbBlurb':'qnote list', 'umessage':umessage}
    ## render QLIST view ####
    return render(request, 'flat.html', context) 
##############################################################
    
### V I E W S #####################################################
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def home(request):
    # one of the places we rebuild jumplinks
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: HOME <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")    
    # added 12/4/2017
    # rutils.safe_purge_session(request)
    rutils.rebuild_jumplinks(request)
    # purge unused Work_sets
    rutils.purge_unused_worksets(request)

    #get complete list of work_sets in use     #
    all_worksets_list = rutils.get_all_worksets(request)
    
    uuid=str(uuid4())
    sdict = {'display_workset':'All', 'fetch_type':'home', 'fetch_root':-9}
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)

    # begin-reminder-build
    AFTER_DATE=date(2020,1,1)
    reminder_items = Notes.nodes.filter(reminder_date__gte=AFTER_DATE,created_by=request.user.username).exclude(status__in = ['6','9']).order_by('reminder_date')

    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    lf_display, lf_list = rutils.locked_file_pmids(request)
    ### end-reminder-build
    
    kform = LoginForm(request.POST)
    context = {'form': '',\
               'current_items':reminder_items, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':0,\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'uuid':uuid, \
               'titleCrumbBlurb':'Relix home', 'umessage':umessage
    }
    rutils.logThis(request, "EXIT: HOME >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")        

    return render(request, 'home.html', context)

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def help(request):
    # simple help, plus simple stats and session var list for debugging
    result_matrix = {}
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: HELP <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")    
    allNodes = Notes.nodes.all()
    result_matrix['allNodes'] = len(allNodes)
    result_matrix['archived'] = len(Notes.nodes.filter(archived=True))
    result_matrix['multiparents'] = {}
    k = set()

    rutils.logThis(request, "           finding items w/more than 1 parent.....")    
    for item in allNodes:
        # a set with all owners
        k.add(item.created_by)
        # look for items with > 1 parent
        parents = item.parents_any_owner()
        if len(parents) > 1:
            result_matrix['multiparents'][item.pmid]=[]
            for ps in parents:
                result_matrix['multiparents'][item.pmid].append([ps.pmid,ps.created_by,ps.title])
            
    result_matrix['created_by'] = k

    rutils.logThis(request, "           person totals.....")    
    result_matrix['person_totals'] = {}
    for person in k:
        result_matrix['person_totals'][person] = len(Notes.nodes.filter(created_by=person))

    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)

    ## PROBLEMATIC WORK_SETS #######
    # worksets with a blank name
    rutils.logThis(request, "           worksets with blank name.....")    
    wsn_with_blank_name = Work_set.nodes.get_or_none(name = '',created_by=request.user.username)
    if wsn_with_blank_name != None:
        notes_attached_to_wsbn = wsn_with_blank_name.ws_belongs.all()
    else:
        notes_attached_to_wsbn = None
    
    # Active Notes without any work_set
    rutils.logThis(request, "           notes w/o any workset.....")    
    
    no_ws = Notes.nodes.has(ws_belongs=False).filter(created_by=request.user.username,archived=False)

    status=rutils.purge_old_uuid_session_vars(request)
    
    rutils.logThis(request, "EXIT: HELP >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")    
    context = {'results':result_matrix, \
               'workset_list':all_worksets_list, \
               'wsbn':wsn_with_blank_name, \
               'notes_attached_to_wsbn':notes_attached_to_wsbn, 'no_ws':no_ws, \
               'fetch_root_type': "help", 'titleCrumbBlurb':'Help'}
    return render(request, 'help.html', context)
##############################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def detail(request, target_id, uuid):
    target_id = int(target_id)
    rutils.starttime_reset(request)
    rutils.message(request, "detail: <b>%s</b>" % target_id)

    rutils.add_recent(request, target_id)
    
    rutils.logThis(request, "ENTER: DETAIL %s <<<<<<<<<<<<<<<<<<<<" % target_id)

    target_node = Notes.nodes.get(pmid=target_id)
    # ugh.  django_neomodel didn't seem to provide node.relationship.all support in templates

    if target_node.created_by != request.user.username:
        rutils.message(request, "User %s not owner of node %s" % (request.user.username, target_id))
        return HttpResponseRedirect(reverse('relix:home'))

    esNoteTextDict = es_sup.EStextNotesGet(request, [int(target_id)])

    # TEMPORARY, DO NOT SAVE. just passing to the form.
    target_node.work_set = target_node.get_workset_name()
    target_node.assigned_to_peoples = ','.join([ x.nickname for x in target_node.assigned_to.all() ])
    target_node.involves_peoples = ','.join([ x.nickname for x in target_node.involves.all() ])
    shortlist_node = Group.nodes.get(group_name="shortlist",created_by=request.user.username)
    target_node.shortlist_marker = target_node.group_items.is_connected(shortlist_node)

    if target_node.image_list != None:
        real_list = target_node.image_list.split()
    else:
        real_list = []

    #get complete list of work_sets in use #
    all_worksets_list = rutils.get_all_worksets(request)
    
    ancestors_of_target = list(target_node.ancestorList(request.user.username))
    ancestors_of_target.reverse()
    
    all_worksets_list.append(None) 
       
    context = {'target':target_node,  'esNoteDict':esNoteTextDict[int(target_id)], \
               'workset_list':all_worksets_list, \
               'titleCrumbBlurb':'Note: '+str(target_node.pmid)+' '+target_node.title[:60], \
               'image_list_display' : real_list,'uuid':uuid, \
               'target_ancestors':ancestors_of_target }
    return render(request, 'detail.html', context)

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def showNote(request, target_id,uuid):
    ''' serve a javascript pop-up to display the noteText '''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: SHOWNOTE %s <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" % target_id)
    rutils.logThis(request, "                       UUID: %s " % uuid)
    #get_or_none in case the note was deleted in another window
    target_node = Notes.nodes.get_or_none(pmid=target_id)

    # add to the recent list
    rutils.add_recent(request, target_id)
    
    error_message = ''
    if target_node==None:
        error_message = "Note %s not found." % target_id
    elif target_node.created_by != request.user.username:
        error_message = "User %s not owner of node %s" % (request.user.username, target_id)
    if error_message != '':
        rutils.message(request, error_message)
        return render(request, 'shownote_error.html', {'error_message':error_message})
        
    esNoteTextDict = es_sup.EStextNotesGet(request, [target_id], uuid)

    #turn image_list into a real list & pass to template
    if target_node.image_list != None:
        real_list = target_node.image_list.split()
    else:
        real_list = []

    # Find the color of the closest Jumplink ancestor
    # add the target_id to the ancestor list, in case it's a jumplink itself
    me_and_ancestor_ids=[target_id]+[i.pmid for i in target_node.ancestorList(request.user.username)]
    # get a list of jumplink pmids
    jumplink_ids = [i.pmid for i in Notes.nodes.filter(jumplink=True,created_by=request.user.username)]
    # find the FIRST ancestor that's a jumplink, and grab its color

    stripe_color="#cccccc" #i.e., same as background
    for anc_pmid in me_and_ancestor_ids:
        if anc_pmid in jumplink_ids:
            jumplink_anc = Notes.nodes.get(pmid=anc_pmid)
            jancc = jumplink_anc.jumpcolor
            if jancc not in ['', None]:
                stripe_color = jancc
                break
    #for shownote, only need ancestors for 1 node
    ancestors_of_target = list(target_node.ancestorList(request.user.username))
    ancestors_of_target.reverse()

    workset = target_node.get_workset_name()
    rutils.logThis(request, "EXIT: SHOWNOTE: %s >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % target_id)    
    
    context = {'target':target_node, 'esNoteDict':esNoteTextDict[int(target_id)], \
               'image_list_display' : real_list, \
               'titleCrumbBlurb':'Note: '+str(target_node.pmid)+' '+target_node.title[:30], \
               'target_ancestors' : ancestors_of_target, 'jumpcolor':stripe_color, \
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'work_set' : workset,'uuid':uuid    }
    return render(request, 'shownote.html', context)
    

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def reminder_list(request):
    '''generate a list of reminders'''
    AFTER_DATE=date(2020,1,1)
    rutils.starttime_reset(request)
    uuid=str(uuid4())
    sdict = { 'fetch_type':'reminders', 'fetch_root': -9 }
    lookup = {}
    rutils.logThis(request, "ENTER: REMINDERS_LIST <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" )

    # can't pass None, so pick a safe prior date
    reminder_items = Notes.nodes.filter(reminder_date__gte=AFTER_DATE,created_by=request.user.username).exclude(status__in = ['6','9']).order_by('reminder_date')
    all_worksets_list = rutils.get_all_worksets(request)
    # "None" used to get translated to "All"
    sdict['display_workset'] = 'None'
    
    # set vsession #############
    rutils.vsession(request,'new',sdict,uuid)
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    lf_display, lf_list = rutils.locked_file_pmids(request)

    rutils.logThis(request, "EXIT: REMINDER_LIST %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(reminder_items))
    context = {'current_items':reminder_items, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':0,\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'uuid':uuid, \
               'titleCrumbBlurb':'Reminders', 'umessage':umessage}
    ## render RECENT view ####
    return render(request, 'flat.html', context)  

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def recent(request):
    '''generate list of most recently accessed items'''
    rutils.starttime_reset(request)
    uuid=str(uuid4())
    sdict = { 'fetch_type':'recent', 'fetch_root': -9 }
    lookup = {}
    rutils.logThis(request, "ENTER: RECENT2 <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" )
    
    has_accessed=list(Notes.nodes.filter(dtAccessed__isnull=False,created_by=request.user.username).order_by('-dtAccessed'))
    found_items=has_accessed[:50]

    #get complete list of work_sets in use
    #   TEMP: didn't include '[None]' at start
    all_worksets_list = rutils.get_all_worksets(request)
    # "None" used to get translated to "All"
    sdict['display_workset'] = 'None'
    
    # set vsession #############
    rutils.vsession(request,'new',sdict,uuid)

    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    lf_display, lf_list = rutils.locked_file_pmids(request)
    
    rutils.logThis(request, "EXIT: RECENT2 %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(found_items))
    context = {'current_items':found_items, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':0,\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'uuid':uuid, \
               'titleCrumbBlurb':'Recent', 'umessage':umessage}
    ## render RECENT view ####
    return render(request, 'flat.html', context)


@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def meetings_list(request):
    '''generate list of meeting_masters'''
    rutils.starttime_reset(request)
    uuid = str(uuid4())
    sdict = {'fetch_type':'meetings', 'fetch_root':-9}
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)

    lookup = {}
    rutils.logThis(request, "ENTER: MEETINGS <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" )

    meeting_items = Notes.nodes.filter(meeting_master=True,created_by=request.user.username).order_by('title')
    ## sort by Work_set
    m_by_w = collections.defaultdict(list)
    for mi in meeting_items:
        # TEMPORARY. DO NOT SAVE. Just for passing to template
        mi.work_set=mi.get_workset_name()
        m_by_w[mi.work_set].append(mi)

    # now build the sorted-by-workset list ##
    # get the sorted keys
    wsk = sorted(m_by_w)
    mi_sorted = []
    for ws in wsk:
        for item in m_by_w[ws]:
            mi_sorted.append(item)

    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)
    
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    
    lf_display, lf_list = rutils.locked_file_pmids(request)
    
    rutils.logThis(request, "EXIT: MEETINGS %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(meeting_items))
    context = {'current_items':mi_sorted, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':0,\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'titleCrumbBlurb':'Meetings List', 'umessage':umessage, 'uuid':uuid}
    ## render MEETINGS_LIST view ####
    return render(request, 'meetings.html', context)

##################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def lockfiles_list(request):
    '''display a list of all active lock files'''

    rutils.logThis(request, "ENTER: LOCKFILES_LIST <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")    
    rutils.starttime_reset(request)
    
    uuid=str(uuid4())
    sdict = { 'fetch_type':'lock_file_list', 'fetch_root':-9 }
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)

    lf_display,lf_pmids = rutils.locked_file_pmids(request)
    rutils.logThis(request, "begin lock list render, n = %s " % len(lf_display))
    all_worksets_list = rutils.get_all_worksets(request)
    rutils.logThis(request, "EXIT: LOCKFILES_LIST >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")    
    context = {'lock_files':lf_display, 
               'workset_list':all_worksets_list, \
               'uuid':uuid,
               'titleCrumbBlurb':'Lock file listing' }
    return render(request, 'lockfiles.html', context)

@login_required()
def remove_lockfile(request, lockfile):
    '''break a lock, from the lockfile list page'''

    # did have freakish error where lockfile was gone by the time this executed
    #  led to hard crash.  so test for it.
    if os.path.isfile(LOCKFILES+lockfile):
        os.remove(LOCKFILES+lockfile)
    else:
        rutils.logThis(request, "ERROR! lockfile did not exist! ID: %s" % target_id)
        rutils.message(request, 'Lockfile did not exist! %s' % target_id)
        request.session['umessage'] = 'Lockfile did not exist! %s' % target_id
    return HttpResponseRedirect('/relix/lockfiles/')


@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def list_tagged_pages(request):
    '''generate list of tagged pages (formerly "pending moves") (includes qnotes)'''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: TAGGED_PAGES <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    uuid=str(uuid4())
    sdict = { 'fetch_type':'list_tagged_pages', 'fetch_root':-9 }

    found_items = list(Notes.nodes.filter(tagged_page=True, created_by=request.user.username))

    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)

    for f in found_items:
        # DO NOT SAVE. Just for passing to template
        f.work_set = f.get_workset_name()

    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
        
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''
        
    rutils.logThis(request, "EXIT: TAGGED_PAGES %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(found_items))
    context = {'current_items':found_items, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'scrollTo':0,\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'titleCrumbBlurb':'Tagged pages', 'umessage':umessage, 'uuid':uuid}
    ## render LIST_TAGGED_PAGES view ###
    return render(request, 'flat.html', context)

########################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def manage_people(request,uuid="nix"):
    '''manage people and their status'''

    #incoming UUID is ignored ATM  2022-12-14
    uuid = str(uuid4())
    sdict = { 'fetch_type':'manage_people', 'fetch_root':-9 }    
    rutils.vsession(request,'new',sdict,uuid)
    
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: MANAGE_PEOPLE  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    people = People.nodes.filter(created_by=request.user.username).order_by('dormant','nickname')
    
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        # PROBLEM: dynamic number of fields, not clear how to use a form
        # https://docs.djangoproject.com/en/3.1/topics/forms/#field-data
        #   says you can use request.POST, which is a querydict
        # https://docs.djangoproject.com/en/3.1/ref/request-response/#querydict-objects
        query_dict_post = request.POST
        # since we don't have repeating values, we can convert to dict
        qd = query_dict_post.dict()
        rutils.logThis(request,"String of qd:%s" % str(qd))
        
        if True:
            peeps = {}
            # make a dict w/key = nickname of all people
            for px in [u.nickname for u in people]:
                peeps[px]={}
                
            for k in qd.keys():
                if k not in ['csrfmiddlewaretoken','new_person']:
                    qd_field,qd_pers = k.split('_')
                    peeps[qd_pers][qd_field]=qd[k]

            for p in peeps:
                pnode=People.nodes.get(nickname=p)
                rutils.logThis(request,"pnode = %s , team = %s, dormant = %s"  % (p, peeps[p]['team'], peeps[p]['dormant']))
                # team is another type of node, so relate it
                pnode.is_member.connect(Team.nodes.get(team_name=peeps[p]['team']))
                #pnode.team = peeps[p]['team']
                if peeps[p]['dormant'] == 'True':
                    pnode.dormant =True
                else:
                    pnode.dormant = False
                pnode.save()
        else:
            # ORIGINAL METHOD ##########################
            #   this ELSE section can be removed if things go ok
            #################################
            # keys of field "dormant" from the form
            dormant_keys = []        
            for k in qd.keys():
                if k not in ['csrfmiddlewaretoken','new_person']:
                    dormant_keys.append(k)
            ## deal with dormant keys
            for k in dormant_keys:
                nick=k.split('dormant_')[1]
                pnode=People.nodes.get(nickname=nick)
                if qd[k] == 'True':
                    pnode.dormant=True
                    pnode.save()
                else:
                    pnode.dormant=False
                    pnode.save()
                    
        rutils.logThis(request,"peeps:%s" % str(peeps) )
        ## deal with new_person
        if qd['new_person'] != "":
            new_person = People(nickname=(qd['new_person'].lower()), dormant=False, created_by=request.user.username)
            new_person.save()
    else:
        # umessage should be empty, or contain an urgent message
        null = 'get would be here'
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''
    
    
    context = {'people_nodes':people, 'titleCrumbBlurb':'Manage People',\
               'TEAM_CHOICES':Team.TEAM_CHOICES,\
               'umessage':umessage,'uuid':uuid, \
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date()
    }
    rutils.logThis(request, 'EXIT: MANAGE_PEOPLE  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
    return render(request, 'manage_people.html', context)

##############################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def people_search(request, team_requested=None, person_nick=None):
    '''generate a list of tasks with people associated, via search (alternative to people_list)'''
    rutils.starttime_reset(request)
    uuid=str(uuid4())
    sdict = { 'fetch_type':'people_search', 'fetch_root': -9 }
    lookup = {}
    rutils.logThis(request, "ENTER: PEOPLE_SEARCH <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" )

    found_items=[]
    if person_nick != None:
        # list for a single person
        target_person = People.nodes.filter(nickname=person_nick, created_by=request.user.username)
        found_items = [x for x in  target_person.assigned_from ]+[x for x in  target_person.involved_with  ]
    else:
        if team_requested == '-none-':
            team_requested = 'appsadmin'

        non_dormant_people = People.nodes.filter(dormant=False, created_by=request.user.username).order_by('nickname')

        selected_team =[x[0] for x in Team.TEAM_CHOICES if x[1]==team_requested][0]
        thisTeam = Team.nodes.get(team_name=selected_team).team_members.all()
        
        for person in non_dormant_people:
            if person in thisTeam:
                found_items += [x for x in  person.assigned_from ]
                found_items += [x for x in  person.involved_with  ]

    found_items_no_arc = [ x for x in found_items if not x.archived ]

    already_added = []
    final_items = []
    for f in found_items_no_arc:
        if f not in already_added:
            final_items.append(f)
        already_added.append(f)
    
    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)
    # "None" used to get translated to "All"
    sdict['display_workset'] = 'None'
    
    # set vsession #############
    rutils.vsession(request,'new',sdict,uuid)

    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    lf_display, lf_list = rutils.locked_file_pmids(request)
    
    rutils.logThis(request, "EXIT: PEOPLE_SEARCH %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(found_items))
    context = {'current_items':final_items, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'TEAM_CHOICES':Team.TEAM_CHOICES,\
               'scrollTo':0,\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'uuid':uuid, \
               'titleCrumbBlurb':'People Search', 'umessage':umessage}
    ## render people_search view ####
    return render(request, 'flat.html', context)



######################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def viewTree(request, target_id, scrollTo='', Pr='n', Ar='n', Ref='noRefresh'):
    '''display the entire tree as outline. builds the itemlist view.
       Ordering determined solely by isort. 
    '''
    rutils.starttime_reset(request)
    uuid = str(uuid4())
    sdict = {}
    rutils.logThis(request, "ENTER: VIEWTREE target_id = %s <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" % target_id)

    ## exception if PMID not found
    try:
        targetNode = Notes.nodes.get(pmid=target_id)
    except DoesNotExist:
        rutils.message(request, "PMID %s not found." % (target_id))
        rutils.logThis(request, "        ERROR: PMID %s not found." % (target_id))        
        rutils.logThis(request, "EXIT: VIEWTREE   target_id = %s >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> ")        
        return HttpResponseRedirect(reverse('relix:home'))

    ############### moved below try ##########################3
    target_id = int(target_id)  # sometimes this comes from return_target
    sdict['fetch_type'] = 'tree'
    sdict['fetch_root'] = target_id
    # umessage should be empty, or contain an urgent message
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''
    ############### moved below try ##########################3
    
    rutils.logThis(request, "      : title: %s " % targetNode.title[:40])

    ancestors_of_target = list(targetNode.ancestorList(request.user.username))
    
    if Notes.nodes.get(pmid=target_id).created_by != request.user.username:
        rutils.message(request, "User %s not owner of node %s" % (request.user.username, target_id))
        return HttpResponseRedirect(reverse('relix:home'))

    # Pr = is this a priority-only display.
    if Pr == 'y':
        sdict['hotitems'] = True
    else:
        sdict['hotitems'] = False        

    # make sure old_arc exists before grabbing it
    sdict['old_arc'] = sdict.setdefault('old_arc', 'not yet set')    

    # Ar = include archived items
    if Ar == 'arc':
        if sdict['old_arc'] != True:        
            Ref = 'ref'
        sdict['include_archived'] = True 
        sdict['old_arc'] = True
        # we'll jump on the parameter
        Ref = 'ref'
    else:
        if sdict['old_arc'] != False:
            ## NEED TO SDICT UPDATE THAT CONDITIONAL
            Ref = 'ref'
        sdict['include_archived'] = False 
        sdict['old_arc'] = False
    ########################################################################
    
    ## this is where sectionhead restriction is implemented
    if targetNode.sectionhead:
        depth = 1
    else:
        depth = DDX

    # if someone asks directly for an archived item (ex., by a related item link), they
    # should get the archived item directly.
    if targetNode.archived == True:
        # sdict cond ^ #
        sdict['include_archived'] = True

    #####################################################################################    
    # the self.children_and_* functions return nodes in hierarchy order (i.e., shortest
    #    pathLength to target comes first.  So parents before children is guaranteed.
    #    this is needed by isort building (bss_execute)
    
    rutils.logThis(request, "      :begin pull nodes" )
    if 'include_archived' in sdict.keys():
        # sdict cond ^ x 2 . #
        if sdict['include_archived']:
            all_nodes = targetNode.children_and_self_w_arc(request.user.username, depth) 
        else:
            all_nodes = targetNode.children_and_self_no_arc(request.user.username, depth)
    else:
        all_nodes = targetNode.children_and_self_no_arc(request.user.username, depth)

    rutils.logThis(request, "      :end pull nodes" )
    rutils.logThis(request, "      :number of all_nodes: %s" % len(all_nodes))    

    # build the sortstrings (viewtree)
    order_lookup = BSS_execute(request, all_nodes, uuid)
    #uncomment to log the sort strings:
    #rutils.logThis(request, str(order_lookup))
    
    #### build the sort, lookup, node arrays  #####################################################
    ####   takes more time than BSS!
    
    # need to get the nodes into a dict by pmid, to cross-reference the order lookup ###
    rutils.logThis(request, "    :viewtree - build sort, node & lookup arrays; adorn nodes ")
    node_dict = { x.pmid: x for x in all_nodes } 
    isort_keys = list(order_lookup.keys())
    isort_keys.sort()
    listitems = []
    for ik in isort_keys:
        # isort_keys are sorted by isort; order_lookup lets you lookup the corresponding PMIDs
        (this_pmid, this_pathlength) = order_lookup[ik]

        ####################################################
        ######## ADDITIONS TO TEMPORARY NODE #######################
        # add pathlength & work_set to the (temporary) "node"
        node_dict[this_pmid].path_length = this_pathlength

        # neutralizing for now. It takes too much time,esp. on long fetches
        #node_dict[this_pmid].work_set = node_dict[this_pmid].get_workset_name()  # ?????
        node_dict[this_pmid].work_set = ""

        #############
        # 2023-12-28 experiment - moving functions out of hierarchical.html template, more efficient?
        #   test for archived, only do the query that will actually be used by the display
        # 2023-01-18 this broke the expando widget, fixed logic
        
        if 'include_archived' in sdict.keys():
            if sdict['include_archived'] == False:
                node_dict[this_pmid].kid_ids_no_arc = node_dict[this_pmid].children_ids_no_arc()
            else:                
                node_dict[this_pmid].kid_ids_w_arc = node_dict[this_pmid].children_ids_w_arc()
                
        ###############
        node_dict[this_pmid].assigned = node_dict[this_pmid].assigned_to.all()
        node_dict[this_pmid].involves = node_dict[this_pmid].involves.all()        
        
        #####################################################
        #####################################################
        
        listitems.append(node_dict[this_pmid])

    rutils.logThis(request, "    :viewtree - build arrays end ")
    #rutils.logThis(request, str(listitems))
    
    ###################################################
    tnws = targetNode.get_workset_name()
    if tnws == None: 
        sdict['display_workset'] = ''
    else:
        sdict['display_workset'] = tnws        

    #get complete list of work_sets in use     #
    all_worksets_list = rutils.get_all_worksets(request)

    lf_display, lf_list = rutils.locked_file_pmids(request)

    # shortlist ############################################################################
    # build list of shortlist item IDs, so highlighting works
    shortlist_node = Group.nodes.get(group_name="shortlist",created_by=request.user.username)
    shortlist_item_ids = [x.pmid for x in shortlist_node.group_items]

    # build list of start_folded kid IDs to hide on page load
    start_folded_parents = [x for x in listitems if x.start_folded]
    #x x xdes[j.pmid] = [x for x in grid_kid_nodes[j.pmid] if x.pmid != k.pmid]
    
    all_start_folded_kids = []
    for s in start_folded_parents:
        # knock out target_id - if that's the fetch_root, the user wants to see the kids
        if s.pmid != target_id:
            all_start_folded_kids+=s.children_ids_no_arc()

    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
    
    # put pmid in message line
    rutils.message(request, "%s" % target_id)
    rutils.logThis(request, "EXIT: VIEWTREE   target_id = %s >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> " % target_id)
    
    context = {'current_items':listitems, 'target_id':target_id, \
               'all_start_folded_kids':all_start_folded_kids, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':shortlist_item_ids, \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'target_ancestors':ancestors_of_target, 'scrollTo':scrollTo, \
               'umessage':umessage, \
               'titleCrumbBlurb':str(targetNode.pmid)+' '+targetNode.title[:30], \
               'uuid':uuid, \
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date()      }
    ## render VIEWTREE view ##
    #return render(request, 'simplest_item_list.html', context)    
    return render(request, 'hierarchical.html', context)


## END VIEWTREE ################################

#############################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def shortview(request,shortlist_jumpview=False):
    '''display the shortlist
       Ordering determined solely by isort. 
    '''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: SHORTVIEW <<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    
    uuid=str(uuid4())
    sdict = {'fetch_type':'shortview', 'fetch_root':-9 }

    # umessage should be empty, or contain an urgent message
    umessage = request.session.setdefault('umessage','')
    request.session['umessage'] = ''

    ## exception if PMID not found
    try:
        # build list of shortlist item IDs, so highlighting works
        rutils.logThis(request, "      :begin pull shortlist nodes" )
        shortlist_node = Group.nodes.get(group_name="shortlist",created_by=request.user.username)
        # order_by is slow, according to my class notes

        # finally a way to do multi-level sorts on a node set (well, you turn it into a list
        shortlist_nodes = list(shortlist_node.group_items) # .order_by("priority","title"))
        for x in shortlist_nodes:
            x.lowtitle = x.title.lower()
        all_sl_nodes = sorted(shortlist_nodes, key=attrgetter('priority','lowtitle'))
    except DoesNotExist:
        rutils.message(request, "Shortlist gen problem." )
        return HttpResponseRedirect(reverse('relix:home'))

    request.session['hotitems'] = False

    # set archive flags
    request.session['include_archived'] = True
    request.session['old_arc'] = True
    rutils.logThis(request, "      :number of all_sl_nodes: %s" % len(all_sl_nodes))    
    rutils.logThis(request, "    :shortview - build arrays end ")    
    ########
    # HACK::so far we only use this for personal items
    sdict['display_workset'] = "personal"

    # get an array of [(id,jumplabel),...] to pass to shortlist new item selector
    personal_jumplinks = rutils.return_personal_jumplist(request)
    jumplinks_w_slitems = []
    
    if False:
        ### build the by-jumplink jumpout links for the shortview display #####################
        # Build the shortlist-by-selected-workset links.   Rarely used.
        rutils.logThis(request, "    :shortview - building by-workset shortlist links ")

        # get group of all *jumplinks* in Work_set=personal 
        personal_ws=Work_set.nodes.get(name='personal',created_by=request.user.username)
        pjumplinks = personal_ws.ws_belongs.filter(jumplink=True).order_by('jumplabel')
        
        # shortlist_nodes - from above, is *all nodes* with shortlist label
        shortlist_node_ids = set([ x.pmid for x in shortlist_nodes])
        # now collect all personal *jumplinks* that have descendants that are shortlist items

        rutils.logThis(request, "    :shortview - pjumplinks loop.... ")
        # This routine is what makes shortlist_view SLOW. <=======================
        #    b/c you have to check each *jumplink* individually.  Loops within loops. 
        # for each jumplink in the Personal workset...
        for pj in pjumplinks:
            # ...get the IDs of its descendants...
            pjdes = pj.descendants()
            pjdes_ids = [ x.pmid for x in pjdes ]
            #... intersect it with the list of IDs of the nodes in the shortlist
            common = shortlist_node_ids & set(pjdes_ids)
            if len(common) > 0:
                jumplinks_w_slitems.append(pj)
    else:
        # shut off the by-jumplink jumpout links.
        jumplinks_w_slitems = []
        shortlist_jumpview = []
         
    rutils.logThis(request, "    :shortview - ...done.... ")
         
    ######################################################################################
    listitems = []
    no_priority = []
    rutils.logThis(request, "    :shortview - finalizing display data")    
    if shortlist_jumpview:
        ## node sort by priority puts empty priority at top. move them.
        jl_node = Notes.nodes.get(jumplabel=shortlist_jumpview,created_by=request.user.username)

        for l in all_sl_nodes:
            if l.descendant_of(jl_node.pmid):
                l.jumpparent = shortlist_jumpview
                if l.priority != '0':
                    listitems.append(l)
                else:
                    no_priority.append(l)
        listitems += no_priority
    else:
        for l in all_sl_nodes:
            l.jumpparent = ''
            if l.priority != '0':
                listitems.append(l)
            else:
                no_priority.append(l)
        listitems += no_priority    

    #get complete list of work_sets in use     #
    all_worksets_list = rutils.get_all_worksets(request)

    lf_display, lf_list = rutils.locked_file_pmids(request)

    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
    
    # put pmid in message line
    rutils.message(request, "shortlist %s" % len(listitems))
    rutils.logThis(request, "EXIT: SHORTVIEW >>>>>>>>>>>>>>>>>>>> ")
    
    context = {'current_items':listitems, 'target_id':-9, \
               'workset_list':all_worksets_list, \
               'lock_file_list':lf_list, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':0, \
               'umessage':umessage, \
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'titleCrumbBlurb':'Shortlist', 'uuid':uuid, \
               'personal_jumplinks':personal_jumplinks,
               'short_jumps':jumplinks_w_slitems, 'shortlist_jumpview':shortlist_jumpview }

    ## render SHORTVIEW view ##
    return render(request, 'flat.html', context)


#####################################################################
##@db.transaction ## <== is from neomodel, helps insure integrity, slight overhead
def BSS_execute(request, node_list, uuid):
    ''' does the isort building. call with a NODE list '''

    ## BSS_execute takes list of nodes; ( buildSortStrings took list of PMIDs)
    #     => Parent nodes *MUST* come before child nodes in the node_list passed arg
    
    ## for new-model array-based lookup for ordering nodes
    ##   to avoid saving isort in db, one node at a time
    # note: my_root has its isort/pathLength set locally
    order_lookup = {}
    pmid_lookup = {}
    current_fetchRoot = ''

    
    ## EXPERIMENT: assume node 0 is always the mother node. Avoids fetchRoot confusion due to
    ##             multiple open window "sessions"
    current_fetchRoot = node_list[0].pmid
    c = 0
    for k in node_list:
        # fetchRoot gets special handling
        if int(k.pmid) == current_fetchRoot:
            rutils.logThis(request, "    :BSS_exec for  fetchroot %s...." %  current_fetchRoot )
            # k.pmid added below 2024-09-02 to break ties for items with identical titles
            this_isort = '000'+k.title[:30]+str(k.pmid)
            order_lookup[this_isort] = (k.pmid, 0) 
            pmid_lookup[k.pmid] = this_isort
        else:
            #rutils.logThis(request, "    :BSS_exec for  %s...." %  k.pmid )
            # inherit SORT STRING base from parent
            p = k.parents(request.user.username)
            if len(p) == 1:
                # per input parm requirement, we've already seen the parent in this loop, so just look it up
                parentIsort = pmid_lookup[p[0].pmid]
            elif len(p) == 0:
                # it's a trunk item
                parentIsort = "0000TRUNK"
            else:
                ## multiple parents; should no longer exist; display message 
                rutils.message(request, "ERROR! parent > 1 for %s" % k.pmid)
                parentIsort = '00000BAD_PARENT_ISORT'
                    
            # add sort relevant data for item at its indent level
            sortPriority = k.priority  # k.priority is a string (choices)
            # 0 = no priority, so needs to sort last not first
            if sortPriority == '0': sortPriority = '_'
            # k.pmid added below 2024-09-02 to break ties for items with identical titles
            this_isort = parentIsort+"||"+'{:03}'.format(k.topSort)+sortPriority+'{:!<30}'.format(k.title[:30].lower()+str(k.pmid))
            # add counter to end of this_isort index, b/c we truncate title at 30chars,
            # and there have been collisions. The result is the dictionary entry is overwritten,
            # and the item never displays. =:-o
            # path_length = count the '||' separator in k.isort to avoid another cypher query
            order_lookup[this_isort+'{:03}'.format(c)] = (k.pmid, this_isort.count('||'))
            c += 1
            pmid_lookup[k.pmid] = this_isort # LOCAL USE. allows lookup in THIS function of *parent* isorts
    rutils.logThis(request, "    :BSS_exec end %s " %  current_fetchRoot   )
    return order_lookup

def test_BSS_execute(request, node_list, uuid):
    ## didn't seem that much faster. 
    order_lookup = {}
    rutils.logThis(request, "    :test_BSS_exec begin ")    
    for n in node_list:
        order_lookup["from_test_bss_execute:"+str(n.pmid)] = (n.pmid, 1)
    rutils.logThis(request, "    :test_BSS_exec end ")
    return order_lookup

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def my_root(request):
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: my_root <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    uuid = str(uuid4())
    sdict= {}
    sdict['fetch_type'] = 'my_root'
    sdict['fetch_root'] = -9

    # let's exclude the qnotes from display on the trunk. It's confusing.
    # first, gotta list them.
    qnote_workset = Work_set.nodes.get_or_none(name = 'qnote',created_by=request.user.username)
    qnote_nodes = qnote_workset.ws_belongs.all()
    qn_pmids=[x.pmid for x in qnote_nodes]
        
    #all_nodes = Notes.nodes.has(child_of=False).filter(created_by=request.user.username).exclude(pmid__in=qn_pmids).order_by('work_set', 'title')
    all_nodes = Notes.nodes.has(child_of=False).filter(created_by=request.user.username).exclude(pmid__in=qn_pmids).order_by('title')
    FIids = [f.pmid for f in all_nodes]
    order_lookup = {}
    # doing custom SortStrings here, to remove an "if/then" clause in bss_exec
    for f in all_nodes:
        
        # not having a workset is pathological, but it does happen
        if f.ws_belongs.all() == []:
            w = '__NO_WORKSET__'
        else:
            w = f.ws_belongs.single().name
        #this_isort = "0000TRUNK:"+'{:03}'.format(f.topSort)+'{:!<30}'.format(f.title[:30].lower())
        this_isort = "0000TRUNK:"+'{:03}'.format(f.topSort)+'{:!<30}'.format(w.lower())+format(f.title[:30].lower())+'{:!<30}'
        #new-model
        order_lookup[this_isort] = (f.pmid, 0)

    #### pull the nodes ############################################################
    ### VERBATIM FROM VIEWTREE
    # need to get the nodes into a dict by pmid, to cross-reference the order lookup
    node_dict = { x.pmid: x for x in all_nodes } 
    isort_keys = list(order_lookup.keys())
    isort_keys.sort()
    listitems = []
    for ik in isort_keys:
        # isort_keys are sorted by isort; order_lookup lets you lookup the corresponding PMIDs
        (this_pmid, this_pathlength) = order_lookup[ik]
        # add pathlength to the (temporary) "node"
        node_dict[this_pmid].path_length = this_pathlength
        # DO NOT SAVE. Just for passing to template
        node_dict[this_pmid].work_set = node_dict[this_pmid].get_workset_name()
        
        listitems.append(node_dict[this_pmid])
    # end new-model ######################################################end verbatim

    #get complete list of work_sets in use
    #all_worksets_list = [None] + f.get_all_workset_labels(request.user.username)
    all_worksets_list = rutils.get_all_worksets(request)

    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
    
    if len(all_nodes) == 0:
        rutils.message(request, 'trunk:no items to display')
        return render(request, 'home.html')
    rutils.logThis(request, "EXIT: MY_ROOT >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    
    context = {'current_items':listitems, 'parent_id':-9, \
               'all_start_folded_kids':[], \
               'workset_list':all_worksets_list, \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'titleCrumbBlurb':'trunk', \
               'uuid':uuid, \
               'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date()
    }
    return render(request, 'hierarchical.html', context)
## end MY_ROOT view ##############################
    
########################################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def grid(request,workset):
    '''grid layout of important items'''
    rutils.starttime_reset(request)
    rutils.logThis(request, "ENTER: GRID ws=%s <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" % workset)

    uuid=str(uuid4())
    sdict = {'fetch_type':'grid'}

    #workset is passed as a URL parameter
    if workset != 'orphans_':
        # get the node for the current workset  xxx
        wsx = Work_set.nodes.get_or_none(name=workset,created_by=request.user.username)
        if wsx == None:
            rutils.logThis(request, "     GRID:  Work_set %s not found, aborting." % workset )
            rutils.message(request, "     GRID:  Work_set %s not found, aborting." % workset )
            return HttpResponseRedirect(reverse('relix:home'))
        
        # gridItemsForWorkset (cypher) does ordering by [grid order, and then toLower title]
        #  returns Notes nodes
        #  gpn_list = wsx.gridItemsForWorkset(request.user.username)

        # dict of grid groups
        #ggd = {x.grid_group_order:x.grid_group_name for x in GridGroup.nodes.filter(work_set=workset)}
        
        # get GridGroups sorted by order
        gpn_list = []  # will be list of NOTE nodes, sorted by grid group order, and then note title
        for gg in  GridGroup.nodes.filter(work_set=workset, created_by=request.user.username).order_by('grid_group_order'):
            gpn_list += gg.gg_members.order_by('title')
            #uh-oh, no priority sort first. Then again, they won't be selected for the grip display!!! yay!!
            
        # get a list of grid parent nodes
        grid_kid_nodes = {}
        all_important_kid_pmids = set()

        # for each node, populate grid_kid_nodes['someGridParent']
        num_of_kids=0
        for g in gpn_list:
            kid_pmid_list = []
            grid_kid_nodes[g.pmid] = g.important_kids(request.user.username, DDX)

        # knock out items that appear on a lower-level grid parent node  ## 5/15/2017
        for g in gpn_list:
            for k in grid_kid_nodes[g.pmid]:
                # TEMPORARY. DO NOT SAVE. Just for passing to template                
                ### opportunistically get work_set attached....
                k.work_set = workset
                # ... and record all important, i.e. GPN kid PMIDs
                all_important_kid_pmids.add(k.pmid)
                for acx in k.gridAncestorList(request.user.username):
                    # acx come up in closest-parent-first order
                    if acx == g: break
                    else:
                        # the ancestor of this kid is a grid parent, and it's not the current ancestor in gpn_list g,
                        # and we hit it first, so remove OTHER griditem's kids :-p
                        for j in gpn_list:
                            if acx.pmid != j.pmid:
                                # grid_kid_nodes is a dict (key=GPN) of lists (of kids)
                                grid_kid_nodes[j.pmid] = [x for x in grid_kid_nodes[j.pmid] if x.pmid != k.pmid]
                    break

        #eliminate empty nodes, count final kids ####
        gpnl_final = []
        for gpn in gpn_list:
            if len(grid_kid_nodes[gpn.pmid]) != 0:
                gpnl_final.append(gpn)
                num_of_kids += len(grid_kid_nodes[gpn.pmid])
        other_important = []
    else:
        # it's a request for an ORPHAN LIST
        #pull nodes or IDs for all important items, drop those that are a child of any grid parent node
        # m.priority in ["1","2","3","4"] AND NOT m.status in ["6","9"]
        grid_item_descendants=rutils.allGridItemDescendants(request.user.username)
        other_important = Notes.nodes.filter(priority__in=["1","2","3","4"], created_by=request.user.username).exclude(status__in=["6","9"]).exclude(pmid__in=grid_item_descendants)
        gpnl_final=[]
        grid_kid_nodes=[]
        num_of_kids=len(other_important)
        # no good choice for orphan workset. 'None' is better than "All", which doesn't expose jumplinks
        workset = 'None'  

    # set vsession
    sdict['display_workset'] = workset    
    rutils.vsession(request,'new',sdict,uuid)

    rutils.logThis(request, "       n of items: %s" % num_of_kids)    
    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)

    rutils.logThis(request, "EXIT: GRID >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")    
    context = {'grid_parents':gpnl_final, 'grid_kids':grid_kid_nodes, 'other_important':other_important,\
               'num_of_kids':num_of_kids,'target_workset':workset,\
               'workset_list':all_worksets_list,\
               'titleCrumbBlurb':'Grid:%s' % workset,\
               'uuid':uuid}
    return render(request, 'grid.html', context)



##############################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def gridgroup_admin(request,workset):
    '''admin the grid groups for a workset'''
    rutils.starttime_reset(request)

    # to start, make sure the set of grid groups nodes order attribute are numbered consecutively
    ws_ggroup = GridGroup.nodes.filter(work_set=workset, created_by=request.user.username).order_by('grid_group_order')
    c = 0
    for g in ws_ggroup:
        c += 1
        g.grid_group_order = str(c);
        g.save()


   ########## POST #####################################################
    if request.method == 'POST':
        uuid=str(uuid4())
        sdict={ 'fetch_type':'gridgroup', 'searchFx':'', 'fetch_root':-9 }

        Sform = gridgroupAdminForm(request.POST)
        # check whether it's valid:
        if not Sform.is_valid():
            rutils.logThis(request, "       gridGroupAdmin: INVALID FORM ======")
            return HttpResponseRedirect(reverse('relix:home'))
        else:
            rutils.logThis(request, "       gridGroupAdmin: valid form ======")

        
    else:
        ### it's a GET ####################################################
        rutils.logThis(request, "       gridGroupAdmin: GET FORM ======")

        uuid=str(uuid4())
        sdict={ 'fetch_type':'grid_groups', 'searchFx':'', 'fetch_root':-9 }
        rutils.vsession(request,'new',sdict,uuid)
        
        # pull the grid group info for this workset
        ggroups = GridGroup.nodes.filter(created_by=request.user.username, work_set=workset).order_by('grid_group_order')

        # get all the Notes items related to the workset in the request
        grid_ws = Work_set.nodes.get(name=workset,created_by=request.user.username)
        # filter the result for notes that are gridItems
        grid_items = grid_ws.ws_belongs.filter(gridItem=True).order_by('title')
        # would be nice to re-order by grid_group_order, but that's on another label
        ggorder = {}
        
        sorted_gis = []
        for gi in grid_items:
            #shoulda been set default, etc
            if gi.gg_belongs.single() == None:
                this_order = "0"
            else:
                this_order = gi.gg_belongs.single().grid_group_order
            if this_order not in ggorder.keys():
                ggorder[this_order] = [ gi.pmid ]
            else:
                ggorder[this_order].append(gi.pmid)
        for g in sorted(ggorder):
            for i in ggorder[g]:
                sorted_gis.append(Notes.nodes.get(pmid=i))
            
        #get complete list of work_sets in use
        all_worksets_list = rutils.get_all_worksets(request)
        rutils.logThis(request, "       gridGroupAdmin: rendering " + str(len(ggroups)) + " grid groups")

        context = {'grid_groups':ggroups, 'grid_items':sorted_gis, \
                   'GGCHX':GridGroup.GRIDGROUP_ORDER_CHOICES, \
                   'target_id':-9,\
                   'workset':workset,\
                   'workset_list':all_worksets_list, \
                   'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))),\
                   'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
                   'titleCrumbBlurb':'Grid group admin','uuid':uuid }
        ## render GRID_GROUP view ##
        return render(request,'grid_groups.html',context)

##############################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def today(request,uuid='uuid_not_passed'):
    '''priority-ordered list of items in selected worksets'''
    rutils.starttime_reset(request)
    
    ########## POST #####################################################
    if request.method == 'POST':
        uuid=str(uuid4())
        sdict={ 'fetch_type':'today', 'searchFx':'', 'fetch_root':-9 }
        lookup = {}
        wks_list = []

        rutils.logThis(request, "ENTER: TODAY as a POST <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
        # receive POST and create a form instance and populate it with data from the request:
        Sform = todayForm(request.POST)
        # check whether it's valid:
        if Sform.is_valid():
            rutils.logThis(request, "       todayform: valid form======")
            wks_list = request.POST.getlist('today_select')

        sdict['work_set_list'] = wks_list
        rutils.vsession(request,'new',sdict,uuid)

    else:
        ### it's a GET ####################################################
        # assume it's come from a universal return, so don't overwrite the session UUID, etc
        rutils.logThis(request, "ENTER: TODAY as a GET <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
        if uuid not in request.session.keys():
            rutils.logThis(request, "TODAY: session.uuid=%s missing, aborting " % uuid )
            rutils.message(request, "TODAY:uuid missing" % uuid )
            return HttpResponseRedirect(reverse('relix:home'))
        if 'work_set_list' in request.session[uuid]:
            wks_list = request.session[uuid]['work_set_list']

        
    ######## both ###################################################################
    rutils.logThis(request, "       wks_list=%s" % wks_list)
    #################################################################################

    # can't filter by work_set, b/c it's NO LONGER A NODE ATTRIBUTE
    found_items = list(Notes.nodes.filter(created_by=request.user.username, \
                                          priority__in=['1', '2', '3']).exclude(status__in=['6', '9']).order_by('priority', 'title'))
    in_scope_items = []
    for f in found_items:
        if f.get_workset_name() in wks_list:
            # TEMPORARY. DO NOT SAVE. Just for passing to template
            f.work_set = f.get_workset_name() # temporary attribute
            in_scope_items.append(f)

    display_workset = ''
    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)

    rutils.logThis(request, "EXIT: TODAY  %s items >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" % len(in_scope_items))
    context = {'current_items':in_scope_items, 'target_id':-9,
               'workset_list':all_worksets_list, \
               'today_workset_list':wks_list, \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'shortlist_ids':rutils.get_shortlist_ids(request), \
               'scrollTo':0,\
               #'return_me_to':-12,\
               'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'titleCrumbBlurb':'Today','uuid':uuid }
    ## render TODAY view ##
    return render(request, 'flat.html', context)

##############################################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def tree_summary(request,target_id='nix', depth=6):
    '''deliver a high-level tree summary'''

    uuid=str(uuid4())
    sdict = { 'fetch_type':'tree_summary','fetch_root':target_id }
    
    if target_id == 'nix':
        return HttpResponseRedirect(reverse('relix:home'))
    target_node = Notes.nodes.get(pmid=target_id)
    all_nodes = target_node.children_and_self_no_arc(request.user.username, depth)
    order_lookup = BSS_execute(request, all_nodes, uuid)
    
    #### pull the nodes ## VERBATIM FROM VIEWTREE ###################################
    # new-model
    # need to get the nodes into a dict by pmid, to cross-reference the order lookup
    node_dict = { x.pmid: x for x in all_nodes } 
    isort_keys = list(order_lookup.keys())
    isort_keys.sort()
    listitems = []
    for ik in isort_keys:
        # isort_keys are sorted by isort; order_lookup lets you lookup the corresponding PMIDs
        (this_pmid, this_pathlength) = order_lookup[ik]
        # TEMPORARY. DO NOT SAVE. Just for passing to template        
        node_dict[this_pmid].path_length = '&nbsp;'*this_pathlength*3
        node_dict[this_pmid].work_set = node_dict[this_pmid].get_workset_name()
        listitems.append(node_dict[this_pmid])
    
    if len(target_node.ws_belongs.all()) == 0:
        sdict['display_workset'] = ''
    else:
        sdict['display_workset'] = target_node.get_workset_name()

    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
    
    rutils.logThis(request, ":* TREE template >>>>> n listitems = %s" % len(listitems))
    
    context = {'current_items':listitems, 'target_id':target_id, \
               'workset_list':all_worksets_list, \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':target_id, \
               'uuid':uuid, \
               'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'titleCrumbBlurb':':'+str(target_node.pmid)+' '+target_node.title[:30] }
                
    ## render TREE (skinny)) view ##
    return render(request, 'tree_list.html', context)

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def kidtree(request,target_id='nix'):
    '''deliver a tree of one node w/kids, with notes'''

    uuid=str(uuid4())
    sdict = { 'fetch_type':'kidtree','fetch_root':target_id }
    if target_id == 'nix':
        return HttpResponseRedirect(reverse('relix:home'))
    target_node = Notes.nodes.get(pmid=target_id)
    all_nodes = target_node.children_and_self_no_arc(request.user.username, 99)
    order_lookup = BSS_execute(request, all_nodes, uuid)
    
    #### pull the nodes ## VERBATIM FROM VIEWTREE ###################################
    # need to get the nodes into a dict by pmid, to cross-reference the order lookup
    node_dict = { x.pmid: x for x in all_nodes } 
    isort_keys = list(order_lookup.keys())
    isort_keys.sort()
    listitems = []
    for ik in isort_keys:
        # isort_keys are sorted by isort; order_lookup lets you lookup the corresponding PMIDs
        (this_pmid, this_pathlength) = order_lookup[ik]
        # TEMPORARY. DO NOT SAVE. Just for passing to template        
        node_dict[this_pmid].path_length = '&nbsp;'*this_pathlength*3
        node_dict[this_pmid].work_set = node_dict[this_pmid].get_workset_name()
        listitems.append(node_dict[this_pmid])
    
    if len(target_node.ws_belongs.all()) == 0:
        sdict['display_workset'] = ''
    else:
        sdict['display_workset'] = target_node.get_workset_name()

    #get complete list of work_sets in use
    all_worksets_list = rutils.get_all_worksets(request)

    # grab the note text
    esNoteTextDict = es_sup.EStextNotesGet(request, list(node_dict.keys()))
    
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
    
    rutils.logThis(request, ":* KIDTREE template >>>>> n listitems = %s" % len(listitems))
    
    context = {'current_items':listitems, 'target_id':target_id, \
               'esNoteDict':esNoteTextDict, \
               'workset_list':all_worksets_list, \
               'PCHX':Notes.PRIORITY_CHOICES, \
               'SCHX':Notes.STATUS_CHOICES, \
               'scrollTo':target_id, \
               'uuid':uuid, \
               'todayx':datetime.isoformat(datetime.now(pytz.timezone('US/Pacific'))),\
               'todaydate':datetime.now(pytz.timezone('US/Pacific')).date(), \
               'titleCrumbBlurb':':'+str(target_node.pmid)+' '+target_node.title[:30] }
                
    ## render KIDTREE view ##
    return render(request, 'kidtree.html', context)


#######################################################################################################    
##### U N I V E R S A L    S E A R C H  ###############################################################
#######################################################################################################
def universal_return(request, called_by, target_id=-9, rebuild=False, uuid='no_uuid_passed'):
    '''Checks session store, via UUID.  Also uses request vars: searchFx, fetchRoot, fetchType'''

    rutils.logThis(request, 'UNIV_RETURN =============================================================' )
    rutils.logThis(request, "      === UR: PASSED: target_id=>%s, called_by=>%s" % (target_id, called_by))

    if uuid != 'no_uuid_passed':
        fetch_type = request.session[uuid]['fetch_type']
        fetch_root = request.session[uuid]['fetch_root']
        rutils.logThis(request, "      === SESSION: fetch_root=>%s, fetch_type=>%s, uuid=>%s" % (fetch_root, fetch_type,uuid ))
        
        if fetch_type == 'popup-existing-edit': 
            return HttpResponseRedirect(reverse('relix:completed', kwargs={'uuid':uuid,'popup_msg':'edit completed','target_id':target_id }))
        elif fetch_type == 'popup-qnote-create':
            return HttpResponseRedirect(reverse('relix:completed', kwargs={'uuid':uuid, 'popup_msg':'note saved','target_id':target_id }))
        elif fetch_type == 'popup-note-locked': 
            return HttpResponseRedirect(reverse('relix:completed', kwargs={'uuid':uuid, 'popup_msg':'note locked!','target_id':target_id }))
        elif fetch_type =='recent':
            return HttpResponseRedirect(reverse('relix:recent'))
        elif fetch_type =='list_tagged_pages':
            return HttpResponseRedirect(reverse('relix:list_tagged_pages'))
        elif fetch_type =='shortview':
            return HttpResponseRedirect(reverse('relix:shortview'))
        elif fetch_type =='reminders':
            return HttpResponseRedirect(reverse('relix:reminderlist'))
        elif fetch_type =='people_list':
            return HttpResponseRedirect(reverse('relix:people_list'))
        elif fetch_type == 'my_root':  # it's a root node
            return HttpResponseRedirect(reverse('relix:my_root'))
        elif fetch_type == 'qlist':  # the qnote listing page
            return HttpResponseRedirect(reverse('relix:qnote-list'))
        elif fetch_type == 'grid': 
            return HttpResponseRedirect(reverse('relix:grid'))
        elif fetch_type == 'search': # SEARCH and QUICKSEARCH
            # PROBLEM: This reiterates all searches as relevance ranked (not time-sorted) (but Hotsearch works OK)
            #    rationalized and probably fixed 2024-01-27
            if 'sort' in  request.session[uuid]['searchQuery'].keys():
                if 'priority' in  request.session[uuid]['searchQuery']['sort']:
                    return HttpResponseRedirect(reverse('relix:reiterateSearch', kwargs={'sort_order':'priority','uuid':uuid}))
                elif 'dtModified' in  request.session[uuid]['searchQuery']['sort']:
                    return HttpResponseRedirect(reverse('relix:reiterateSearch', kwargs={'sort_order':'date_mod','uuid':uuid}))
            else:
                return HttpResponseRedirect(reverse('relix:reiterateSearch', kwargs={'sort_order':'relev','uuid':uuid}))
        elif fetch_type == 'today':
            return HttpResponseRedirect(reverse('relix:today',kwargs={'uuid':uuid} ))
        elif fetch_type == 'people_list':
            return HttpResponseRedirect(reverse('relix:list_people'))
        elif fetch_type == 'lock_file_list': # lock file listing
            # not set, this will never hit.  You can't do anything that requires returning to the lock file list
            return HttpResponseRedirect(reverse('relix:recent'))
        elif fetch_type == 'meetings': # meeting view
            return HttpResponseRedirect(reverse('relix:meetings_list'))
        elif fetch_type == 'tree_summary':
            return HttpResponseRedirect(reverse('relix:tree_summary'))
        elif fetch_type == 'items_edit':
            return HttpResponseRedirect(reverse('relix:viewtree', kwargs={'target_id':fetch_root,'scroll_to':target_id,'Ref':'ref'}))
        elif fetch_type in ['tree','movetagged']:
            # return to list of items, after edit ##################################
            if rebuild:
                return_url = '/relix/%s/%s/view/ref/' % (fetch_root, target_id)
            else:
                return_url = '/relix/%s/%s/view/' % (fetch_root, target_id)                
            rutils.logThis(request, "      Return to target_id...")
            return HttpResponseRedirect(return_url)
        elif fetch_type == 'changerel':
            # actually really does need the refresh /ref
            return_url = '/relix/%s/%s/view/ref' % (fetch_root, target_id)
            rutils.logThis(request, "      Redirect after changerel, in UR...")
            return HttpResponseRedirect(return_url)
        else:
            rutils.logThis(request, '      UR_ERROR: fell though UUID switch <============' )
    else:
        rutils.message(request, '      UR_ERROR: no UUID provided' )
        rutils.logThis(request, '      UR_ERROR: no UUID provided <===========================' )        
    
    
    rutils.logThis(request, "      UR_ERROR: FATAL fallthrough <=========================")
    rutils.message(request, "      UR_ERROR: FATAL fallthrough")    
    return HttpResponseRedirect(reverse('relix:home'))
    
