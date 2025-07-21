#####################################################
# rutils.py
######################################################
''' utilities that are shared across modules (views.py, es_sup.py, etc)'''

from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

import inspect  # to find the function that called a function

#from neo4j import GraphDatabase, basic_auth
from neomodel import db, DoesNotExist

from datetime import datetime, date
import pytz, time, os, pickle, uuid
from uuid import uuid4

from relix.forms import LoginForm
from relix.models import Notes, Group, Work_set, People
from . import es_sup
from multifactor.decorators import multifactor_protected

LOGFILE = '/tau/dj313/relix3/logs/14-relix.log'
LOCKFILES = '/tau/dj313/relix3/lockfiles/'
PMID_COUNTER_FILE = '/tau/dj313/relix3/pmid_counter.txt'

DDX = 20

##############################################################

def log_user_in(request):
    # but do see https://docs.djangoproject.com/en/1.10/topics/auth/default/#using-the-views

    # make sure session store is clear
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        logThis(request, 'LOGIN attempt...')

        Lform = LoginForm(request.POST)
        # check whether it's valid:
        if Lform.is_valid():
            # process the data in form.cleaned_data as required
            user = authenticate(username=Lform.cleaned_data['username'], \
                                password=Lform.cleaned_data['password'])
            if user is not None:                
                login(request, user)
                logThis(request, '    ... user %s logged in.' % request.user.username)
                jlist = rebuild_jumplinks(request)
                starttime_reset(request)
                return HttpResponseRedirect(reverse('relix:home'))
            else:
                message(request, "bad login")
                logThis(request, "LOGIN - bad credentials")
        else:
            message(request, "form invalid")
            logThis(request, "LOGIN form invalid")
    else:
        # if a GET (or any other method) we'll create a blank form
        logThis(request, 'Generating LOGIN form...')
        pass
        #all non-logged in results return to the home page w/form

    kform = LoginForm()
    return render(request, 'home.html', {'form': kform,'titleCrumbBlurb':'Relix home'})


def log_user_out(request):
    # https://docs.djangoproject.com/en/1.10/topics/auth/default/#how-to-log-a-user-out
    logThis(request, 'LOGOUT ...')
    message(request, 'Thanks for visiting, %s ' % request.user.username)
    logout(request)
    starttime_reset(request)
    kform = LoginForm()
    return render(request, 'home.html', {'form': kform,'titleCrumbBlurb':'Relix home'})


####################################################################################

    
def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False
#########################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def get_next_pmid(request):
    ''' generate the next PMID for a new Note'''
    PMF = open(PMID_COUNTER_FILE, 'r')
    last_pmid = PMF.readline()
    PMF.close()
    next_pmid = int(last_pmid)+1
    PMF = open(PMID_COUNTER_FILE, 'w')
    PMF.write(str(next_pmid))
    PMF.close()
    return next_pmid

#########################################################

##############################################################

@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def purge_old_uuid_session_vars(request):
    # this purges one uuid-keyed branch underneath a session.
    ## RIGHT NOW IT ONLY OPERATES ON THE CURRENT SESSION.
    ##
    
    nowx = datetime.now(pytz.timezone('US/Pacific'))
    session_keys = list(request.session.keys())
    for sk in session_keys:
        if is_valid_uuid(sk):
            ## 'created' was missing very early on
            if 'created' not in request.session[sk] or \
               (nowx-datetime.fromisoformat(request.session[sk]['created'])).days > 30:
                logThis(request, "Purging session 'window thread': %s"  % sk)
                del request.session[sk]
            

    
##########################################################
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def vsession (request, action, sdict, uuid):
    '''perform actions on the view-session
       sdict should have keys: vroot, vfetch, vrtm
       uuid must be set in routine making the call.
    '''

    # see https://docs.djangoproject.com/en/3.0/topics/http/sessions/
    # see #clearsessions:  $ django-admin clearsessions  <== not done automatically
    # $ django-admin clearsessions  --settings=relix3.settings --pythonpath='/tau/dj313/relix3/'
    
    # see https://docs.djangoproject.com/en/3.0/topics/http/sessions/#when-sessions-are-saved
    #     request.session.modified = True
    #     ^ needed if you only modify items contained below request.session['something']

    # seems that rinteract.workset_display_change(request, selected_workset, uuid)
    #  is the first place uuid is needed when, ex., user asks Firefox to "restore last session"
    #  added a check there to be sure UUID is in session keys.

 
    def new_vsession(request, sdict, uuid):
        #create a new vsession
        # factored this out so it could be used by both requests to generate a new vsession,
        #  and also unexpected lack of UUID
        logThis(request, "***** UUID not found, creating new UUID = %s"  % uuid)
        request.session[uuid]={}
        request.session[uuid]['created'] = datetime.now(pytz.timezone('US/Pacific')).isoformat()
        request.session[uuid]['created_by'] = request.user.username
        
        for k,v in sdict.items():
            request.session[uuid][k] = v
        if 'display_workset' not in sdict:
            request.session[uuid]['display_workset'] = 'None'
        request.session.modified = True
        return
    
    if action == 'new':
        # create a new session with whatever info was passed in
        new_vsession(request, sdict, uuid)
        
    elif action == 'update':
        #update a vsession

        if uuid not in request.session:
            # sometimes happens when, ex., FF crashes.
            # create a skeleton session[uuid]
            logThis(request, "*****Update UUID not found. Creating skeleton record for %s"  % uuid)
            #request.session[uuid]={}
            #request.session[uuid]['created'] = datetime.now(pytz.timezone('US/Pacific')).isoformat()
            #request.session[uuid]['created_by'] = request.user.username
            uuid = str(uuid4())
            if 'fetch_root' not in sdict:
                sdict['fetch__root']=-9
            if 'fetch_type' not in sdict:
                sdict['fetch_type']='tree'
            new_vsession(request, sdict, uuid)
        
        if sdict != {}:
            for k,v in sdict.items():
                request.session[uuid][k] = v
        request.session.modified = True            
        
    elif action == 'delete':
        #delete a vsession
        del request.session[uuid]
        
    elif action == 'dump_to_log':
        
        ## lifted from rinteract, which might not be needed there now #########
        if uuid == 'undefined' or uuid not in list(request.session.keys()):
            # create a stub
            uuid = str(uuid4())
            sdict = {'fetch_root':-9, 'fetch_type':-9, 'include_archived':False}
            # set vsession
            new_vsession(request,sdict,uuid)
       ##############################
        logThis(request, "vsession dump: %s" % str(request.session[uuid]))

    else:
        logThis(request, "************ ERROR! UNSUPPORTED VSESSION ACTION: %s"  % request.session[uuid])
        return ("Unsupported action")
    
    logThis(request, "vsession // action:%s // called by:%s // uuid:%s // "  % (action,inspect.stack()[1].function,uuid))
    # uncomment to debug
    # logThis(request, "    %s"  % request.session[uuid])
    return

##########################################################

def logThis(request, s):
    #make sure request.session['starttime'] is defined
    LX = open(LOGFILE, 'a')
    current_time = datetime.now().strftime("%Y/%m/%d  %H:%M:%S:%f")
    if 'starttime' not in request.session.keys():
        v = 0
        s +=  '   <== WARNING: STARTTIME UNKNOWN =='
    else:
        v = datetime.now().timestamp()-request.session['starttime']
    LX.write(current_time+"\t"+'{:.6f}'.format(v)+":\t"+request.user.username+":\t"+s+'\n')
    LX.close
    return()
##########################################################

def message(request, m):
    # base template currently shows last 3 messages
    # since viewtree puts in a bypassed message ("fetch")
    # this prevents a recent message from getting bumped out of view.

    tempList = request.session.setdefault('messages', [])
    if m != 'fetch':
        tempList.append(m+'; ')
    else:
        tempList.append('')
        
    # might as well truncate the thing
    request.session['messages'] = tempList[-9:]
###########################################################################

def starttime_reset(request):
    '''set the new start time to the current time
       for elapsed time logging'''
    #request.session['starttime'] = request.session.setdefault('starttime',datetime.now())
    #can't just store the datetime object, it's not "JSON serializable", and crashes
    request.session['starttime'] = datetime.now().timestamp()
    return

##########################################################
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def safe_purge_session(request):
    '''purge session variables (except auth stuff)
       and unused Work_set nodes'''

    # PURGE SESSION VAR'S    #########################
    # can't do request.session.clear() or we'll forget who's logged in.  auth keys start w/"_"
    # get as list, since the loop changes the dict size
    # Not clear that this is needed any more, given the vsessions
    skeys = list(request.session.keys())
    for k in skeys:
        if k[0] != '_' and \
           k not in ['jumplist', 'messages', 'pending_moves', 'recents',\
                     'starttime','search_packet','display_workset', 'umessage']:
            request.session.pop(k)
    request.session['needsBSrebuild']=False

    # PURGE UNUSED WORK_SET NODES ####################
    result = purge_unused_worksets(request)
    
    return

##############################
def get_all_worksets(request):
    '''get worksets for the current user. returns a sorted list'''

    if request.user.is_authenticated:
        workset_list = [w.name for w in Work_set.nodes.filter(created_by=request.user.username)]
        workset_list.sort()
        workset_list = ['All'] + ['None'] + workset_list 
    else:
        workset_list = []
    return workset_list

##################################
def get_shortlist_ids(request):
    '''return a list of PMIDs of shortlist items''' 
    shortlist_node = Group.nodes.get_or_none(group_name="shortlist",created_by=request.user.username)
    if shortlist_node == None:
        return []
    else:
        return [x.pmid for x in shortlist_node.group_items]

##################################
def purge_unused_worksets(request):
    '''delete any Work_set node that has no related nodes'''
    
    unbound = Work_set.nodes.has(ws_belongs=False).filter(created_by=request.user.username)
    
    for u in unbound:
        u.delete_ws_and_relationships(request.user.username)

    # however, "qnote" label must always exist
    #  including if the program is every instantiated from scratch
    if Work_set.nodes.get_or_none(name='qnote',created_by=request.user.username) == None:
        q = Work_set(name='qnote', created_by=request.user.username).save()
    return



############################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def set_workset_with_descent(request, target_node, new_workset_name):
    ''' assumes target_node is NOT already linked to its new work_set (lowercase). 
        new work_set comes in as target_node.work_set.
        Old label is the one currently connected to target_node. '''

    # normalize to lower case
    #target_node.work_set = target_node.work_set.lower()
    new_workset_name = new_workset_name.lower()
    new_ws_node = Work_set.nodes.get_or_none(name=new_workset_name,created_by=request.user.username)
    old_ws_node = Work_set.nodes.get_or_none(name=target_node.get_workset_name(),created_by=request.user.username)
    
    if old_ws_node == None:
        old_ws_node_name = '' #b/c old_ws_node.name errors
    else:
        old_ws_node_name = old_ws_node.name

    #this may preclude attempts to "clean-up" by moving item onto its own parent, etc.
    # leave for now
    if old_ws_node_name == new_workset_name:
        return  "no workset change"
    
    if new_ws_node == None:
        # need to create it. No biggie.
        new_ws_node = Work_set(name=new_workset_name, created_by=request.user.username).save()

    me_and_my_children = target_node.children_and_self_w_arc(request.user.username, DDX)
    number_of_kids = len(me_and_my_children)
    count = 0

    to_update_in_ES = []
    for amc in me_and_my_children:
        # if CHILD has no workset,  more than 1 label, or if the child workset
        #    is the same as target_node's old workset, update it
        #    Otherwise, step over kids w/intentional different workset names
        if len(amc.ws_belongs.all()) != 1  or amc.get_workset_name() == old_ws_node_name:
            if old_ws_node != None:
                ### DISCONNECT ALL n workset relations ###
                for former_workset in amc.ws_belongs.all():   
                    amc.ws_belongs.disconnect(former_workset)
            ## CONNECT new Work_set node
            amc.ws_belongs.connect(new_ws_node)
            
            ## ES updating #########################################################
            ## now work_set is solely a scope - a collection of PMIDs, not a field that gets indexed
            ## 2021-09-19:  think it would be best to update it in ES. Could be misleading otherwise.
            to_update_in_ES.append(amc)            
            count += 1
    if len(to_update_in_ES) > 0:
        es_sup.ESbulkWorksetUpdate(request,to_update_in_ES)

    return count
##############################################################################################
@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def check_and_archive(request, targetNode):
    '''checks if an item, ex., that is being moved, can be archived; 
       and checks if an items ancestors can be archived'''

    ######## 6 = canceled, 9 = "done", 10 = pending done, 11 = pending cancel ####

    items_to_reindex = set()
    # items with status != done or canceled shouldn't be archived #####################
    if targetNode.status not in ['6', '9']:
        if targetNode.archived:
            targetNode.archived = False
            items_to_reindex.add(targetNode.pmid)
        targetNode.save()
        
        ##### if kid is not done/cancelled, Ancestor can't be done/cancelled
        ####### NOTE child has to be already moved for this to work
        for ax in targetNode.ancestorList(request.user.username):
            if ax.status == '9': 
                ax.status = '10' #pending done
                items_to_reindex.add(ax.pmid)
            if ax.status == '6':
                ax.status = '11' #pending cancelled
                items_to_reindex.add(ax.pmid)
            if ax.archived:
                ax.archived = False
                items_to_reindex.add(ax.pmid)
            ax.save()


    # done or cancelled items must be removed from the shortlist        
    if targetNode.status in ['6','9']:
        shortlist_node = Group.nodes.get(group_name="shortlist", created_by=request.user.username)
        if targetNode.group_items.is_connected(shortlist_node):
            targetNode.group_items.disconnect(shortlist_node)
            
    # items with status cancelled, done, or pending cancelled or pending done
    #      need to be checked for children status, and ancestors status
    if targetNode.status in ['6', '9', '10', '11']:
        kids = targetNode.children_ids_w_arc()
        # no kids = archived targetNode
        if len(kids) == 0:
            targetNode.archived = True
            # switch from pending to done or cancelled
            if targetNode.status == '10':
                targetNode.status = '9'
            if targetNode.status == '11':
                targetNode.status = '6'
            items_to_reindex.add(targetNode.pmid)
        else:
            kids_all_done = True
            for kx in Notes.nodes.filter(pmid__in=kids):
                # if ANY kid is not done/cancelled, flag to false
                if kx.status not in ['6', '9']:
                    kids_all_done = False
            if kids_all_done:
                # if no kids tripped the i'm-still-alive flag
                for kx in Notes.nodes.filter(pmid__in=kids):
                    kx.archived = True
                    kx.save()
                    items_to_reindex.add(kx.pmid)
                if targetNode.status == '10':
                    targetNode.status = '9'
                if targetNode.status == '11':
                    targetNode.status = '6'
                targetNode.archived = True
                items_to_reindex.add(targetNode.pmid) 
            else:
                if targetNode.status == '9':
                    targetNode.status = '10'
                if targetNode.status == '6':
                    targetNode.status = '11'
                items_to_reindex.add(targetNode.pmid)

        targetNode.save()
        
        #############################################################################################
        # now check if ANCESTORS can be archived (should be no need to change their kids' statuses)
        #        ES for ancestors is updated here if needed.
        if targetNode.status in ['6', '9']: # target is done or canceled, not pending
            for ax in targetNode.ancestorList(request.user.username):
                # if ancestor was cancelled or done, now it goes pending yyy
                retireAncestor = True
                if ax.status in ['10', '11']: 
                    for akx in Notes.nodes.filter(pmid__in=ax.children_ids_w_arc()):
                        if akx.status not in ['6', '9']: retireAncestor = False
                else:
                    retireAncestor = False

                if retireAncestor:
                    # means ancestor ax and its children are done|canceled and ancestor can be archived
                    if ax.status == '10': ax.status = '9'
                    if ax.status == '11': ax.status = '6'                    
                    ax.archived = True
                    ax.save()
                    ## set the archive field in ES for this ancestor y1
                    #resultDict = es_sup.EStextNotesGet(request, [ax.pmid])
                    #status = es_sup.ESupdateDocument(request, ax, resultDict[ax.pmid])
                    #logThis(request, "Ancestor ESuD status=%s" % status)
                    items_to_reindex.add(ax.pmid)
                    
        # Note, the check_and_archive call for the previous parent is done as a separate call in items_edit (confirmed)
    logThis(request,"      rutils:check_and_archive items_to_reindex: %s" % list(items_to_reindex))
    return list(items_to_reindex)



#############################################################################
@login_required()
def return_personal_jumplist(request):
    personal_ws = Work_set.nodes.get(created_by=request.user.username,name="personal")
    pjumplinks = personal_ws.ws_belongs.filter(jumplink=True).order_by('jumplabel')
    pjl_short = []
    for x in pjumplinks:
        pjl_short.append((x.pmid,x.jumplabel))
    return pjl_short
#############################################################################
@login_required()
def rebuild_jumplinks(request):
    '''less crazy, plus provides leading linkout to Grid display'''
    logThis(request,"        enter Rebuild Jumplinks...........")
    work_set_list=list(Work_set.nodes.filter(created_by=request.user.username).order_by('name'))
    jstruct = {}  # dict to hold the compiled data
    c=0
    for ws in work_set_list:
        # list of jumplinks for that WS. In case-sensitive order
        if ws.name in [None,'']:
            wsname = 'none'
        else:
            wsname = ws.name
        num_griditems = len(ws.gridItemsForWorkset(request.user.username))
        # pull the jumplinks within each work_set
        # deal with case-sensitive sort issue #######
        # list(ws.ws_belongs.filter(jumplink=True).order_by('jumplabel'))
        # exclude done and cancelled items
        raw_jumpnodes = list(ws.ws_belongs.filter(jumplink=True).exclude(status__in = ['9','11']).order_by('jumplabel'))
        jn_by_jumplabel = {}
        # each jumpnode gets stuck into a dict, where key = jumplabel
        for jnx in raw_jumpnodes:
            jn_by_jumplabel[jnx.jumplabel]=jnx
        jn_keys=sorted(jn_by_jumplabel,key=str.lower)
        jn_sorted=[jn_by_jumplabel[x] for x in jn_keys]
        jstruct[wsname]={ 'jitems':jn_sorted,'wsc':'wsc_'+str(c),'num_griditems':num_griditems }
        c+=1
    jumpset=[]
    jumplist=[]

    # sort work_set keys (outer loop)
    wskeys = sorted(jstruct,key=str.lower)
    for ws in wskeys:
        if len(jstruct[ws]['jitems']) > 0:
            # prepend the grid link #
            if jstruct[ws]['num_griditems'] > 0:
                gridx = '<a href="/relix/grid/'+ws+'/"><b>'+ws+'</b></a>'
            else:
                gridx = ws                
            jumplist.append('class="shortcut workset_'+str(ws)+' '+jstruct[ws]['wsc']+'"'+\
                            ' style="border:2px solid #dedede;background: #dedede;">'+gridx+'\n')
            for j in jstruct[ws]['jitems']:
                # note that a jumplink MUST HAVE a workset in this model
                if j.jumpcolor in [None,'']:
                    style_slug = ' style="border:2px solid #dedede;" '
                else:
                    style_slug = ' style="border:2px solid '+j.jumpcolor+';"'

                jumplist.append('class="shortcut workset_'+str(ws)+' '+jstruct[ws]['wsc']+'"'+style_slug+'> <a href="/relix/'+str(j.pmid)+'/view/">'+str(j.jumplabel)+'</a>\n')
                jumpset.append((j.pmid,j.jumplabel,str(ws)))
                
    # add the trailing orphans link
    jumplist.append('class="shortcut workset_none" '+\
                            ' style="border:2px solid #dedede; background: #dedede;"><a href="/relix/grid/orphans_/"><b>others</b></a>\n')
    logThis(request,"        exit Rebuild Jumplinks...........")    
    request.session['jumplist'] = jumplist
    request.session['jumpset'] = jumpset

    return jumplist


        
#############################################################################
# must import db from neomodel
def allGridItemDescendants(usern):
    '''returns the PMIDs of all descendants of all GRIDITEMS.
           helps to find hot items that are not under a gridItem'''
    cypherx = "MATCH (n:Notes)-[:CHILD_OF*..44]->(g:Notes {gridItem:true}) RETURN DISTINCT n.pmid " 
    results, meta = db.cypher_query(cypherx)
    if len(results) > 0:
        return [ x[0] for x in results[1:] ]
    else:
        return []

#############################################################################


def prio_stat_choices(request):
    '''return the priority and status choices lists'''
    return(Notes.PRIORITY_CHOICES, Notes.STATUS_CHOICES)


def locked_file_pmids(request):
    '''return a list of items with current lockfiles'''
    lockfile_names = os.listdir(LOCKFILES)
    lockfiles = {}
    lockpmids = []
    for l in lockfile_names:
        if request.user.username in l:
            FILEX = open(LOCKFILES+l,'r')
            file_contents = FILEX.readlines()
            FILEX.close()
            pmid, titlex, timex = file_contents[0].split('\t')
            lockpmids.append(int(pmid))
            lockfiles[timex] = [l] + file_contents[0].split('\t')
    flkeys = list(lockfiles.keys())
    flkeys.sort()
    lf_display = []
    for j in flkeys:
        lf_display.append(lockfiles[j])

    return(lf_display,lockpmids)
###############################################################################

@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def safe_mfa_check(request):
    '''call this MFA-decorated function at any point you need to safely check, ex., before doing an operation that can't be interrupted.'''
    logThis(request,"        rutils.safe_mfa_check called...........")
    return

###############################################################################
# restore add_recent

@login_required()
@multifactor_protected(factors=1, user_filter=None, max_age=300, advertise=False)
def add_recent(request, target_id):
    '''add a pmid to the recent list'''
    target_id = int(target_id)
    target_node = Notes.nodes.get(pmid=target_id)
    # populate dtAccessed 
    target_node.dtAccessed = datetime.now(pytz.timezone('US/Pacific'))
    target_node.save()
    return


    

