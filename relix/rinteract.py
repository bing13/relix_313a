#####################################################
# rinteract.py    RELIX3 ----------------------------------------------------------
# 2018-06-29 orig
######################################################
''' support for interactive features'''
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from relix.models import Notes, Group, People
from django.http import JsonResponse
from django.http import HttpResponse
from . import rutils
from . import es_sup
import os
import pytz
import glob
import hashlib
import pickle
from uuid import uuid4
#import datetime as datetime
from datetime import datetime, date
from multifactor.decorators import multifactor_protected
from relix.forms import StashRecallForm

STASHUSERDIR ='/tau/dj313/relix3/relix/stash/'

##############################################################################################
def completed(request,uuid,popup_msg,target_id):
    rutils.message(request, '%s completed' % str(target_id) )
    context = {'uuid':uuid, 'popup_msg':popup_msg, 'titleCrumbBlurb':str(target_id)+': '+popup_msg,'targetID':target_id }

    return render(request, 'completed.html', context)
##############################################################################################
@login_required
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def priority_status_update(request):
    '''handle the interactive priority update'''

    rutils.starttime_reset(request)
    rutils.logThis(request, "priority_update  ========================")

    # Get field from JS, save fields to target_node
    target_id = int(request.POST.getlist('pmid')[0])
    priority = request.POST.getlist('priority')[0]
    status = request.POST.getlist('status')[0]

    target_node = Notes.nodes.get(pmid=target_id)
    target_node.priority = priority
    target_node.status = status
    # NEED TO UPDATE dtModified ###
    #was UTC#############
    target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))
    
    target_node.save()
    
    #archive processing #######################################################    
    rutils.message(request, "... check and archive...")    

    #   check if node status is done, pending done, or canceled; include ancestors
    ps_to_reindex = rutils.check_and_archive(request, target_node)
    # UPDATE ES done elsewhere ###################
    # ES is updated directly from the Javascript routine, which calls /relix/es_refresh/
    
    rutils.message(request, '%s:p%s/s%s' % (target_id, priority, status))
    return_data = {'data': "success for " + str(target_node.pmid)}
    return JsonResponse(return_data)
##############################################################################################


def workset_display_change(request, selected_workset, uuid):
    '''when display workset is set, including by loading a display page, this saves the session var
       8/2/2020 - only being called by javascript. '''
    
    if False:  # set True for debugging
        return JsonResponse({'data': "workset now: FAKE"})
    rutils.starttime_reset(request)
    #rutils.logThis(request, "workset_display_change  ========================")
    if uuid == 'undefined' or uuid not in list(request.session.keys()):
        uuid = str(uuid4())
        sdict = {'fetch_root':-9}
        # set vsession
        rutils.vsession(request,'new',sdict,uuid)
        
    if selected_workset == 'undefined':
        selected_workset = 'None'
    # set session var
    request.session[uuid]['display_workset'] = selected_workset
    rutils.vsession(request,'update',{},uuid)
    rutils.logThis(request, "workset_display_change = %s, uuid = %s"  % (selected_workset,uuid))
    return_data = {'data': "workset now: " + str(selected_workset)}
    return JsonResponse(return_data)


### LIVE_SAVE ############################################################################################
@login_required
#@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def live_save(request):
    '''save the note you are currently editing, do not leave the context'''
    rutils.starttime_reset(request)
    
    # fields not edited: pmid, dtCreated, dtModified, created_by, isort
    #new_work_set = Sform.cleaned_data['new_work_set']

    # GET FIELDS FROM JAVASCRIPT
    # save fields to target_node
    target_id = int(request.POST.getlist('pmid')[0])
    
    # GET TARGET_NODE    
    try:
        target_node = Notes.nodes.get(pmid=target_id)
    except:
        rutils.logThis(request, "ERROR - PMID not found: %s" % target_id)
        rutils.message(request, "ERROR - PMID not found: %s" % target_id)
        return HttpResponseRedirect(reverse('relix:home'))

    rutils.logThis(request, "LIVE_SAVE entered: %s  ========================" % target_id)
    
    # this should never happen, but...
    if target_node.created_by != request.user.username:
        rutils.message(request, "User %s not owner of node %s, edit aborted" % (request.user.username, target_id))
        return HttpResponseRedirect(reverse('relix:home'))

    ##was UTC
    target_node.dtModified = datetime.now(pytz.timezone('US/Pacific'))
    target_node.title = request.POST.getlist('title')[0]
    target_node.priority = request.POST.getlist('priority')[0]
    target_node.status = request.POST.getlist('status')[0]
    target_node.topSort = request.POST.getlist('topSort')[0] ## COMPLAINING ABOUT LIST TO INT
    ## note data
    is_qnote = request.POST.getlist('is_qnote')[0]
    noteText = request.POST.getlist('ck_content')[0]

    #rutils.logThis(request, "sectionhead: %s" % str(request.POST.getlist('sectionhead')))

    # for some reason it was hard to get the form field "translated" correctly. This works. 
    if request.POST.getlist('sectionhead')[0] == 'True':
        target_node.sectionhead = True
    else:
        target_node.sectionhead = False
    if request.POST.getlist('jumplink')[0] == 'True':
        target_node.jumplink = True
    else:
        target_node.jumplink = False
    if request.POST.getlist('gridItem')[0] == 'True':
        target_node.gridItem = True
    else:
        target_node.gridItem = False
            
    target_node.jumplabel = request.POST.getlist('jumplabel')[0]
    #target_node.grid_order = request.POST.getlist('grid_order')[0]    
    work_set_name = request.POST.getlist('work_set')[0]
    
    target_node.image_list = request.POST.getlist('image_list')[0]
    ## QNOTE ###################################################################
    if is_qnote == 'yes':
        #do something
        target_node.pending_move = True
    ## HASNOTE FIELD ###########################################################
    if len(noteText) > 1 or len(target_node.image_list) > 8:
        target_node.hasNote = True
    else:
        target_node.hasNote = False

    ##      SAVE ALL FIELDS FROM THE NODE ##########################
    target_node.save()

    ##      Create a hash so you can tell if the note was modified since the last liveSave #####
    ##         request.session['live_save_hash'][pmid] stores these
    targdat = [target_node.pmid,target_node.title, target_node.priority, target_node.status, target_node.topSort, \
               target_node.sectionhead, target_node.jumplink, target_node.gridItem, target_node.jumplabel, \
               work_set_name, target_node.image_list, target_node.hasNote, noteText]
    #          target_node.grid_order
    targhash = hashlib.md5(pickle.dumps(targdat)).hexdigest()
    rutils.logThis(request, "    targhash: %s  " % targhash)

    save_it=False
    if 'live_save_hash' not in request.session:
        request.session['live_save_hash'] = {}
        request.session.modified = True                    
        rutils.logThis(request, " request.session['live_save_hash'] added as empty dict")
        
    string_pmid = str(target_node.pmid)
    if string_pmid not in request.session['live_save_hash'] :
        rutils.logThis(request, " PMID %s not in request.session['live_save_hash'], adding" % string_pmid)
        #rutils.logThis(request, " request.session['live_save_hash'] keys: %s" % str(request.session['live_save_hash'].keys()))
        request.session['live_save_hash'][string_pmid] = targhash
        request.session.modified = True 
        save_it = True
        rutils.logThis(request, " save_it=TRUE  r.s['live_save_hash'][%s]=%s"  % (string_pmid,request.session['live_save_hash'][string_pmid]  )   )
    elif request.session['live_save_hash'][string_pmid] == targhash:
        save_it = False
        #rutils.logThis(request, " save_it=FALSE  %s r.s['live_save_hash']=%s"  % (target_node.pmid,request.session['live_save_hash'][string_pmid]  )   )
    else:
        save_it = True
        #rutils.logThis(request, " save_it=TRUE UPDATE  %s r.s['live_save_hash']=%s"  % (target_node.pmid,request.session['live_save_hash'][string_pmid]  )   )
        request.session['live_save_hash'][string_pmid] = targhash
        request.session.modified = True 
        
    if save_it:
        rutils.logThis(request, "    LiveSave beginning for %s  %s...  ========================" % (target_node.pmid,target_node.title))
        ##      STASH EXISTING NODE  ################################
        stash_note(request,target_node.pmid, noteText)

        ## ES updating #########################################################
        status = es_sup.ESupdateDocument(request, target_node, noteText)
        rutils.logThis(request, "    ES fetched..")
        rutils.logThis(request, "    updated ES, status %s...  ========================" % status)    
    
        rutils.set_workset_with_descent(request, target_node, work_set_name )
        target_node.save()
        rutils.message(request, "LIVE saved: %s" % target_id)

        #archive processing (from live save) ####################################################
        #   check if node status is done, pending done, or canceled; include ancestors
        rutils.message(request, "... check and archive...")
        ls_to_reindex = rutils.check_and_archive(request, target_node)
        caa_nodes = Notes.nodes.filter(pmid__in=ls_to_reindex)
        if len(caa_nodes) != 0:
            (status, success) = es_sup.ESbulkItemsEditUpdate(request, caa_nodes)

            # qnote: we don't know if it's a qnote or not - that's passed in call to notes_edit
            #        but that should set node.pending_mov reliably, so no action here.

        return_data = {'data': "success for  %s" % str(target_node.pmid)}
    else:
        rutils.logThis(request, "    no LiveSave needed for %s %s...  ========================" % (target_node.pmid,target_node.title))    
        return_data = {'data': "no save needed for  %s" % str(target_node.pmid)}
    return JsonResponse(return_data)
### end LIVE_SAVE ###

####STASH ###########################################################################
@login_required()
def stash_note(request, pmid,noteText='nix'):
    '''save a shadow copy of the note on the file system.
       the LAST VERSION SAVED is stashed, not the current version.
       Call stash_note RIGHT BEFORE you save a new note.'''
    
    target_node = Notes.nodes.get(pmid=pmid)
    rutils.logThis(request, "   ENTER STASH %s" % target_node.pmid)

    #sud1 
    STASHDIR =STASHUSERDIR+request.user.username+'/'+str(target_node.pmid)
    INDENT="        "
    rutils.logThis(request, INDENT+"STASHDIR=%s" % STASHDIR)
    
    if noteText == 'nix':
        text = target_node.noteText
    else:
        text = noteText

    # relix3/relix/stash was "drwxrwxr-x 76 ubuntu ubuntu 4096 Jun 29 20:41 stash"
    # stash subdirectories and files were owned by ubuntu:www-data
    
    if not os.path.isdir(STASHUSERDIR):
        rutils.logThis(request, INDENT+"stashuserdir needed %s" % target_node.pmid)
        os.mkdir(STASHUSERDIR)
        rutils.logThis(request, INDENT+"stashuserdir built %s" % target_node.pmid)
    if not os.path.isdir(STASHDIR):
        os.mkdir(STASHDIR)
        rutils.logThis(request, INDENT+"stashdir built %s" % target_node.pmid)

    ## build the payload ##############################
    if target_node.parents(request.user.username) == []:
        parentx = 'QNOTE'
    else:
        parentx = str(target_node.child_of[0].pmid)
    rutils.logThis(request, INDENT+"parentx assigned %s" % target_node.pmid)

    
    if target_node.image_list == None:
        image_list_text = ''
    else:
        image_list_text = target_node.image_list

    payload = '\n<br/>'.join(["PMID="+str(target_node.pmid),"Parent="+parentx, \
                              'Title=<strong>'+target_node.title+'</strong>', \
                              'Created by='+target_node.created_by, \
                              "Created="+target_node.dtCreated.astimezone().strftime('%Y-%m-%d %H:%M:%S'),\
                              "Modified="+target_node.dtModified.astimezone().strftime('%Y-%m-%d %H:%M:%S'),\
                              "Image List="+image_list_text])
    
    # Now strongly suspect crash happens when text comes back as a None, or maybe empty dict
    # avoid the error on concat
    rutils.logThis(request, INDENT+"text type: "+str(type(text)))
    if text == None:
        text = ''
    payload += text
    rutils.logThis(request, INDENT+"payload built %s ..." % payload[:30].replace('\n',' '))
    
    stash_stamp = datetime.now(pytz.timezone('US/Pacific')).isoformat()+'_'+str(target_node.pmid)+'.sta'
    octal_permission=0o600 # owner read/write, g=none, w=none
    
    def opener(path, flags):
        return os.open(path, flags, octal_permission)  #0o777)

    with open(STASHDIR+'/'+stash_stamp, 'w', opener=opener) as LX:
        LX.write(payload+'\n')
    
    rutils.logThis(request, "   EXIT STASH for %s" % target_node.pmid)
    return

### end STASH_NOTE ###############################################

####### STASH_RECALL #########################################################
# stash_recall   ############################################################

@login_required()                                                                                               
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False) 
def stash_recall (request):
    '''POST: retrieve stash history for an item
       GET: return initial stash recall page'''
    
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: STASH_RECALL   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
    uuid=str(uuid4())
    sdict = { 'fetch_type':'lock_file_list', 'fetch_root':-9 }
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)

    all_worksets_list = rutils.get_all_worksets(request)
    
    if request.method == 'POST':
        # create a form instance and populate it with data from the request: 
        Sform = StashRecallForm(request.POST)
        # check whether it's valid: 
        if Sform.is_valid():
            pmid = Sform.cleaned_data['pmid']
            # next tests that the pmid submitted will convert to numeric
            if pmid.isnumeric():
                rutils.logThis(request, "     ...valid form..." )
                # using the PMID, harvest the list of stashed records
                # /tau/dj3-1-0/relix3/relix/stash/bernard/52305$ 
                target_node = Notes.nodes.get_or_none(pmid=pmid)
                #sud1
                if target_node != None:
                    STASHDIR =STASHUSERDIR+request.user.username+'/'+str(target_node.pmid)+'/'
                    if os.path.isdir(STASHDIR):
                        rutils.logThis(request, "    STASHDIR=%s" % STASHDIR)                        
                        file_names = os.listdir(STASHDIR)   # array
                        # success #################
                        context = {'pmid':pmid, 'stashed_files':file_names,  'titleCrumbBlurb':"stash recall",\
                                   'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(),\
                                   'workset_list':all_worksets_list,'uuid':uuid }
                        return render(request, 'stash_recall.html', context)

                    else:
                        rutils.message(request, "invalid stashdir %s" % pmid)
                else:
                    rutils.message(request, "invalid pmid %s" % pmid )
            else:
                rutils.message(request, "pmid not numeric: %s" % pmid)
        else:
            rutils.message(request, "form not valid")            
            rutils.logThis(request, '    STASHDIR FORM NOT VALID!')
            
        # for all not-successes
        context = {'pmid':0, 'stashed_files':[],  'titleCrumbBlurb':"stash recall",\
                   'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(),\
                   'workset_list':all_worksets_list,'uuid':uuid }
        return render(request, 'stash_recall.html', context)
                   
    else:
        # must be a GET
        context = {'pmid':0, 'stashed_files':[],  'titleCrumbBlurb':"stash recall",\
                   'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
                   'workset_list':all_worksets_list,'uuid':uuid }
        return render(request, 'stash_recall.html', context)
        

### end STASH_RECALL
# stash_display  ###################################################
@login_required()                                                                                               
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False) 
def stash_display(request, target_id,stashfile):
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: STASH_DISPLAY   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    uuid=str(uuid4())
    sdict = { 'fetch_type':'lock_file_list', 'fetch_root':-9 }
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
     
    all_worksets_list = rutils.get_all_worksets(request)
    
    #load the stash file contents from disk
    #sud1
    STASHDIR =STASHUSERDIR+request.user.username+'/'+str(target_id)+'/'
    with open(STASHDIR+stashfile,'r') as SC:
        sc = SC.readlines()

    rutils.logThis(request, 'EXIT: STASH_DISPLAY')

    context = {'pmid':target_id, 'stashfile':stashfile, 'scontents':sc,
               'titleCrumbBlurb':"stash display "+str(target_id),\
               'workset_list':all_worksets_list,'uuid':uuid, \
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat()
               }
    return render(request, 'stash_display.html', context)

### end STASH_DISPLAY ####################

# stash_purge  ###################################################
@login_required()                                                                                               
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def stash_purge(request):
    import subprocess
    rutils.starttime_reset(request)
    rutils.logThis(request, 'ENTER: STASH_PURGE   <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')

    uuid=str(uuid4())
    sdict = { 'fetch_type':'lock_file_list', 'fetch_root':-9 }
    # set vsession
    rutils.vsession(request,'new',sdict,uuid)
     
    all_worksets_list = rutils.get_all_worksets(request)

    # days = sta files older than this are deleted
    days = 14
    print_cmd = "find /tau/dj313/relix3/relix/stash -depth -name *.sta -mtime +%s -print" % days
    delete_cmd = "find /tau/dj313/relix3/relix/stash -name *.sta -mtime +%s -delete" % days

    # using the find-print command to get the # of files that will be deleted    
    #result=subprocess.run(print_cmd, capture_output=True, shell=True)
    #rout=result.stdout.decode(encoding='utf-8', errors='ignore').split('\n')
    #rutils.logThis(request, "      Deleting %s files" % len(rout))
    #rutils.message(request, "      Deleting %s files" % len(rout))
    
    # now the actual deletion
    result=subprocess.run(delete_cmd, capture_output=True, shell=True)
    rout=result.stdout.decode(encoding='utf-8', errors='ignore').split('\n')
    if rout == ['']:
        rutils.message(request,'no files to delete')
        rutils.logThis(request,'        ==> no files to delete')
    else:
        rutils.message(request, '    % files deleted' % len(rout))
        rutils.logThis(request, '    % files deleted' % len(rout))
        # remove following line to reduce log pollution
        rutils.logThis(request, "     "+str([x.split('bernard')[1]+'\n' for x in rout2 if len(x) > 1]))

    rutils.logThis(request, 'EXIT: STASH_DISPLAY')

    context = {'pmid':0, 'stashed_files':[],  'titleCrumbBlurb':"stash recall",\
               'todayx':datetime.now(pytz.timezone('US/Pacific')).isoformat(), \
               'workset_list':all_worksets_list,'uuid':uuid }

    return render(request, 'stash_recall.html', context)

### end STASH_PURGE ####################



####TAGGED PAGE ###########################################################################

@login_required()
def tag_page(request, pmid):
    '''click on TP widget on item list to tag an item'''

    target_node = Notes.nodes.get(pmid=pmid)
    if target_node.tagged_page:
        target_node.tagged_page = False
        result = {'data': 'untagged' }
    else:
        target_node.tagged_page = True
        result = {'data': 'tagged' }
    target_node.save()

    return JsonResponse( result)

####START FOLDED ###########################################################################

@login_required()
def start_folded(request, pmid):
    '''click on SF widget on item list to mark it was defaulting to folded children'''

    target_node = Notes.nodes.get(pmid=pmid)
    kids = target_node.children_ids_no_arc()
    if target_node.start_folded:
        target_node.start_folded = False
        result = {'state':'unfolded','children':kids }
    else:
        target_node.start_folded = True
        result = {'state': 'folded','children':kids }
    target_node.save()
    
    rutils.logThis(request, "START_FOLDED:  %s" % target_node.start_folded)
    return JsonResponse(result)

####SHORT LIST ###########################################################################

@login_required()
def shortlist(request, pmid):
    '''click on SL widget to put an item on/off the short list'''

    target_node = Notes.nodes.get(pmid=pmid, created_by=request.user.username)
    shortlist_node = Group.nodes.get(group_name="shortlist", created_by=request.user.username)
    if target_node.group_items.is_connected(shortlist_node):
        target_node.group_items.disconnect(shortlist_node)
        target_node.shortlist_marker = False
        result = {'data': 'unshortlisted' }
    else:
        target_node.group_items.connect(shortlist_node)
        target_node.shortlist_marker = True
        result = {'data': 'shortlisted' }
    target_node.save()

    return JsonResponse( result)


### build_note_features ##################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def build_note_features(request, pmid, uuid):
    ''' additional features for the detail pane. called by /build_note_features'''

    if uuid == 'undefined' or uuid not in list(request.session.keys()):
        uuid = str(uuid4())
        sdict = {'fetch_root':-9, 'fetch_type':'unknown-bnf'}
        # set vsession
        rutils.vsession(request,'new',sdict,uuid)

    # TRAP ERROR ################################################################
    if 'fetch_root' not in request.session[uuid].keys():
        result = '<li>ERROR:</li><li>No fetchroot in session. pmid: %s</li>' % pmid
        return HttpResponse( result )
    
    rmt = request.session[uuid]['fetch_root']
    
    ci = Notes.nodes.get_or_none(pmid=pmid, created_by=request.user.username)

    # TRAP ERROR ################################################################
    if ci == None:
        result = '<li>ERROR:</li><li>Note %s not found.</li>' % pmid
        return HttpResponse( result )
    #############################################################################

    #tagged_page ####################
    tagged_page='<li onClick="tagged_page_toggle( %s );" id="tp%s"' % (ci.pmid,ci.pmid)
    if ci.tagged_page:
        tagged_page += 'class="tagged_page tp_hilite live_link"'
    else:
        tagged_page += 'class="tagged_page live_link"'
    tagged_page += ' >&starf;</li>'

    #shortlist ####################
    shortlist_node = Group.nodes.get(group_name="shortlist", created_by=request.user.username)

    shortlist = '<li  onClick="shortlist_toggle( %s );" id="sl%s"' % (ci.pmid,ci.pmid)
    if ci.group_items.is_connected(shortlist_node):
        shortlist += ' class="shortlist sl_hilite live_link"'
    else:
        shortlist += ' class="shortlist live_link"'
    shortlist += ' >&dscy;</li>'

    #start_folded ####################
    kid_ids=ci.children_ids_no_arc()
    if len(kid_ids) > 0:
        folded='<li onClick="start_folded_toggle( %s );" id="sf%s"' % (ci.pmid,ci.pmid)
        if ci.start_folded:
            folded += 'class="start_folded sf_hilite live_link"'
        else:
            folded += 'class="start_folded live_link"'
        folded += ' >&dtrif;</li>'
    else:
        folded = ''
        
    #parent/move ####################
    if request.session[uuid]['fetch_type'] == 'my_root' or ci.child_of.single() == None:
        parent_move = '<li><a href="/relix/%s/myroot/0/changerel/%s">add parent</a></li>' % (ci.pmid, uuid )
    else:
        parent_move = '<li><a href="/relix/%s/child_of/%s/changerel/%s">move</a></li>' % (ci.pmid, ci.child_of.single().pmid, uuid )

    #related ####################
    if len(ci.rel_content) == 0:
        related='<li><a href="/relix/%s/rel_content/0/changerel/%s"  >add rel.</a></li>' % (ci.pmid, uuid)
    else:
        related=''

    # item select widget toggle ####################
    item_select_widget = '<li class="live_link activate_item_select" onClick="Elist_item_select_widgets_toggle();">&ocir;</li>'

    # pop-out edit
    pop_edit = '''<li class="live_link" onClick="var $pmid =$(this).closest('tr').attr('id'); 
			   var $return_me_to = $('input[name=return_me_to]').val();
			   window.open('/relix/' + $pmid + '/qnote/%s','_blank','width=900,height=1000,top=80,left=60');">&nearr;</li>''' % uuid

    # new child ####################
    new_child = '<li><a href="/relix/%s/addnote/%s" class="add-plus">new child</a></li>' % (ci.pmid, uuid)

    # adopt child ####################
    adopt = '<li><a href="/relix/%s/adopt_item/%s">adopt child</a></li>' % (ci.pmid, uuid)
    
    # simple (aka "detail")####################
    simple = '<li><a href="/relix/%s/%s">detail</a></li>' % (ci.pmid, uuid)
    # split ####################
    split = '<li><a href="/relix/%s/splitnote/%s">split</a></li>' % (ci.pmid, uuid)
    # ktree ##########################
    ktree = '<li> <a href="/relix/kidtree/%s/">ktree view</a></li>' % (ci.pmid)		    
    
    #workset / topsort ####################
    work_top ='<li class="static_text">'
    if request.session[uuid]['fetch_type'] not in ['searchx','my_rootx','todayx']:
        work_top += '%s : %s' % (ci.get_workset_name(), ci.topSort)
    work_top += '</li>'
    
    result="\n".join([item_select_widget,tagged_page,shortlist,folded,pop_edit,new_child,adopt,parent_move,related,simple,split,ktree,work_top])
    return HttpResponse( result )
### END build_note_features

### build_people_widget ##################################################################################
@login_required()
def build_people_HORIZONTAL(request, pmid, uuid):
    ''' build people widget for pop-down pane. called by JS assign_people'''

    if uuid == 'undefined' or uuid not in list(request.session.keys()):
        uuid = str(uuid4())
        sdict = {'fetch_root':-9, 'fetch_type':'unknown-bpw'}
        # set vsession
        rutils.vsession(request,'new',sdict,uuid)
    rmt = request.session[uuid]['fetch_root']
    pi = People.nodes.filter(created_by=request.user.username,dormant=False)
    # TRAP ERROR ################################################################
    if pi == None:
        result = '<li>ERROR:</li><li>No people???</li>' % pmid
        return HttpResponse( result )
    #############################################################################
    
    # the current Note
    j=Notes.nodes.get(pmid=pmid, created_by=request.user.username)
    # get list of People currently assigned to this item
    which_list = {}
    which_list['assigned'] = [x.nickname for x in j.assigned_to.all()]
    which_list['involved'] = [x.nickname for x in j.involves.all()]    

    all_nicks = []
    for person in pi:
        all_nicks.append(person.nickname)
    outx = ''
    for action in ['assigned','involved']:
        outx += '<ul id="action%s" class="item_people_%s">' % (pmid, action)
        for nick in sorted(all_nicks):
            checker = ''
            if nick in which_list[action]:
                checker = 'checked="checked"'
            outx += '''<li><input type="checkbox" name="people" value="%s" %s  onclick="peopleChanged(this,'%s','%s','%s');" >%s</li>''' % (nick, checker,action, nick,pmid, nick)
        outx += '''</ul>'''
    return HttpResponse( outx )
## END build_people_widget

### build_people_vertical  ##################################################################################
# same as build_people_widget, but alternate display (single vertical column)

@login_required()
def build_people_widget(request, pmid, uuid):
    ''' build people widget for pop-down pane. called by JS assign_people'''

    if uuid == 'undefined' or uuid not in list(request.session.keys()):
        uuid = str(uuid4())
        sdict = {'fetch_root':-9, 'fetch_type':'unknown-bpw'}
        # set vsession
        rutils.vsession(request,'new',sdict,uuid)
    rmt = request.session[uuid]['fetch_root']
    pi = People.nodes.filter(created_by=request.user.username,dormant=False)
    # TRAP ERROR ################################################################
    if pi == None:
        result = '<li>ERROR:</li><li>No people???</li>' % pmid
        return HttpResponse( result )
    #############################################################################
    
    # the current Note
    j=Notes.nodes.get(pmid=pmid, created_by=request.user.username)
    # get list of People currently assigned to this item
    which_list = {}
    which_list['assigned'] = [x.nickname for x in j.assigned_to.all()]
    which_list['involved'] = [x.nickname for x in j.involves.all()]    

    all_nicks = []
    for person in pi:
        all_nicks.append(person.nickname)
    outx = ''
    #for action in ['assigned','involved']:
    outx += '<ul id="action%s" class="item_people">' % (pmid)
    for nick in sorted(all_nicks):
        ichecker = '' ; achecker = ''
        if nick in which_list['assigned']:
            achecker = 'checked="checked"'
        if nick in which_list['involved']:
            ichecker = 'checked="checked"'
        
        outx += '''<li>a:<input type="checkbox" name="people" value="%s" %s  onclick="peopleChanged(this,'%s','%s','%s');" >''' % (nick, achecker,'assigned', nick,pmid)
        outx += '''i:<input type="checkbox" name="people" value="%s" %s  onclick="peopleChanged(this,'%s','%s','%s');" >%s</li>\n''' % (nick, ichecker,'involved', nick,pmid, nick)
    outx += '''</ul>'''
    return HttpResponse( outx )
## END build_people_vertical ##########
        
### people_update ########################################################################################

@login_required()
def people_update(request,pmid, which_list, action, nick):
    ''' AJAX service point for people panel changes. 
        The user has clicked one of the checkboxes, so process it. '''
    rutils.logThis(request, "people_update...%s  %s  %s  %s" % (pmid, which_list, action, nick))
    target_node=Notes.nodes.get(pmid=pmid)
    person_node=People.nodes.get(nickname=nick)
    #rutils.logThis(request, ".... nodes obtained")
    if which_list == 'assigned':
        if action == 'add':
            result = target_node.assigned_to.connect(person_node)
        else:
            result = target_node.assigned_to.disconnect(person_node)
    elif which_list == 'involved':
        if action == 'add':
            result = target_node.involves.connect(person_node)
        else:
            result = target_node.involves.disconnect(person_node)
    else:
        return HttpResponse("ERROR!   UNCAUGHT people_update which_list = %s" % which_list)
    # any change in People needs to be indexed in ES
    # for the note_edit target_node
    es_sup.es_refresh_document_no_text(request, pmid)
    
    return HttpResponse(result)
### people_update ########################################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def build_people_cell(request,pmid):
    '''updates the "ppl" display cell. called by assign_people JS'''
    # the current Note
    j=Notes.nodes.get(pmid=pmid, created_by=request.user.username)
    # get list of People currently assigned to this item
    assigned = [x.nickname for x in j.assigned_to.all()]
    involved = [x.nickname for x in j.involves.all()]    
    outx= ''
    if len(assigned) > 0:
        for a in sorted(assigned):
            outx += '<span class="assigned_to">%s</span> ' % a
    else:
        outx = ''
    if len(involved) > 0:
        outx += '<br/>'
        for i in sorted(involved):
            outx += '<span class="involves">%s</span> ' % i
    return HttpResponse(outx)
    

### anc_list #############################################################################################

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def anc_list(request,pmid):
    ''' return HTML list of ancestor for a given PMID'''
    rutils.logThis(request,"anc_list requested, %s" % pmid)
    target_node=Notes.nodes.get(pmid=pmid)
    list_of_ancestors = list(target_node.ancestorList(request.user.username))
    result = ''
    if list_of_ancestors == []:
        result = '<br/>&nbsp;&nbsp;&nbsp;<a href="/relix/trunk/" class="parentLink item_title_linkout">[ root node ]</a>'
    else:
        list_of_ancestors.reverse()
        for anc in list_of_ancestors:
            result += '<br/>&nbsp;&nbsp;&nbsp;<a href="/relix/'+str(anc.pmid)+'/view/" class="parentLink item_title_linkout">'+anc.title+'</a>'
    return  HttpResponse(result)

