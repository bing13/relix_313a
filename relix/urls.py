## RELIX3 URLS ####################################
from django.urls import path, register_converter
from . import views
####################################################

# this was crashing 2023-10-07, upgrade to OS & Django, etc
#from django.conf.urls import include, url
# see https://github.com/Tivix/django-rest-auth/issues/659
# said to use
from django.urls import include
from django.urls import re_path as url
#####################

from django.contrib.auth import views as auth_views
from . import es_sup, rinteract, items, rutils

#from . import url_converter
#register_converter(url_converter.PosNegInteger,'pnint')
## not used yet. 

app_name = 'relix'
urlpatterns = [
    path('', views.home, name='home'),    
    path('help/', views.help, name='help'),
    # /login
    url(r'^login/$', rutils.log_user_in, name='login'),
    # /logout
    url(r'^logout/$', rutils.log_user_out, name='logout'),
    
    # used for original porting
    #url(r'^fixtimes$', views.fixTimes, name='fixTimes'),
    # detail ex: /relix/234

    url(r'^recent/$', views.recent, name='recent'),
    path('reminders/', views.reminder_list, name='reminderlist'),    
    path('lockfiles/', views.lockfiles_list, name='lockfilelist'),
    path('<str:lockfile>/break_lock/', views.remove_lockfile),        
    url(r'^list_tagged_pages/$', views.list_tagged_pages, name='list_tagged_pages'),
    path('shorttoggle/<int:pmid>/', rinteract.shortlist),
    path('shortlist/', views.shortview, name='shortview'),
    path('shortlist/<str:shortlist_jumpview>/', views.shortview, name='shortview'),
    url(r'^newshort/$', items.new_shortlist_item, name='new_shortlist_item'),    
    path('st_folded/<int:pmid>/', rinteract.start_folded),
    path('tag_page/<int:pmid>/',  rinteract.tag_page),    
    url(r'^today/$', views.today, name='today'),
    path('today/<str:uuid>', views.today, name='today'),    
    url(r'^es_refresh_no_text/(?P<target_id>[0-9]+)/$', es_sup.es_refresh_document_no_text, name='es_refresh_no_text'),
    url(r'^trunk/$', views.my_root, name='my_root'),
    url(r'^itemsedit/$', views.items_edit, name='items_edit'),
    path('<int:target_id>/<str:return_to_id>/cancel_edit/<str:uuid>', views.cancel_edit),    
    url(r'^(?P<target_id>[0-9]+)/view/$', views.viewTree, name='viewTree'),
    url(r'^(?P<target_id>[0-9]+)/(?P<scrollTo>[0-9]+)/view/$', views.viewTree, name='viewTree'),
    url(r'^(?P<target_id>[0-9]+)/view/(?P<Pr>[yn])/$', views.viewTree, name='viewTree'),
    url(r'^(?P<target_id>[0-9]+)/view/(?P<Ar>arc)/$', views.viewTree, name='viewTree'),
    url(r'^(?P<target_id>[0-9]+)/view/(?P<Ref>ref)/$', views.viewTree, name='viewTree'),
    url(r'^(?P<target_id>[0-9]+)/(?P<scrollTo>[0-9]+)/view/(?P<Ref>ref)/$', views.viewTree, name='viewTree'),    

    #url(r'^(?P<target_id>[0-9]+)/(?P<relatedID>[0-9]+)/(?P<relType>[a-z_\-]+)/deleterel/(?P<uuid>[\-0-9]+)/$', views.deleteRel, name='delete-rel'),
    path('<int:target_id>/<int:relatedID>/<str:relType>/deleterel/<str:uuid>/', items.deleteRel, name='delete-rel'),
    path('grid/<str:workset>/', views.grid, name='grid'),
    path('gridgroups/<str:workset>/', views.gridgroup_admin, name='gridgroups'),
    path('gridgroupadd/', items.new_gridgroup, name='new_gridgroup'),
    path('gridgroupassign/', items.assign_gridgroup, name='assign_gridgroup'),
    path('gridgroupdelete/<str:grid_group_name>/<str:gworkset>/', items.delete_gridgroup, name='delete_gridgroup'),
    path('gridgroupmove/<str:grid_group_name>/<str:gworkset>/<str:direction>/', items.move_gridgroup, name='move_gridgroup'),

    path('stashrecall/', rinteract.stash_recall, name='stash_recall'),
    path('stashdisplay/<int:target_id>/<str:stashfile>/', rinteract.stash_display, name='stash_display'),
    path('stashpurge/', rinteract.stash_purge, name='stash_purge'),
    
    #url(r'^(?P<target_id>[0-9]+)/cleartagged/(?P<return_target>[\-0-9]+)/$', views.cleartagged, name='clear-tagged'),
    url(r'^addrootnode/$', items.addRootNode, name='add-root-node'),

    url(r'^live_save/$',rinteract.live_save, name='live_save'),
    url(r'^priority_status_update/$',rinteract.priority_status_update, name='priority_status_update'),
    path('tree/<int:target_id>/<int:depth>/', views.tree_summary),
    path('kidtree/<int:target_id>/', views.kidtree),    
    ## rmt may be a negative number
    path('<int:pmid>/buildfeatures/<str:uuid>', rinteract.build_note_features),
    path('<int:pmid>/buildpeople/<str:uuid>', rinteract.build_people_widget),
    # people_update is an ajax service point
    path('<int:pmid>/people_update/<str:which_list>/<str:action>/<str:nick>', rinteract.people_update),
    path('<int:pmid>/peoplecell/', rinteract.build_people_cell),
    path('<int:pmid>/anc_list/', rinteract.anc_list),
    path('<int:target_id>/splitnote/<str:uuid>', items.split_note),
    path('<int:mmaster_pmid>/add_meeting/<str:uuid>', items.add_meeting, name='add_meeting'),    
    path('meetings/', views.meetings_list, name='meetings_list'),
    path('<int:target_id>/adopt_item/<str:uuid>', items.adopt_item),
    path('<int:target_id>/shownote/<str:uuid>', views.showNote, name='show-note'),
    path('<int:parent_id>/addnote/<str:uuid>', items.addNote, name='add-note-to-parent'),
    path('<int:target_id>/edit/<str:qnote>/<str:uuid>', views.notes_edit, name='notes_edit'),
    path('<int:target_id>/qnote/<str:uuid>', views.qnotes, name='qnote-create'),
    path('qnote_list', views.qnote_list, name='qnote-list'),    
    path('completed/<str:uuid>/<str:popup_msg>/<int:target_id>', rinteract.completed, name='completed'),
    path('<int:target_id>/<str:linkToType>/<int:linkToID>/changerel/<str:uuid>', items.changeRel, name='change-relix'),
    path('<int:target_id>/<str:uuid>', views.detail, name='detail'),
    path('<int:target_id>/deletenote/<str:uuid>', items.deleteNote, name='delete-note'),
    path('<int:target_id>/<int:newLinkTo>/movetagged/<str:uuid>', items.movetagged, name='move-tagged'),
    # people ######
    path('manage_people/', views.manage_people),
    path('manage_people/<str:uuid>', views.manage_people),        
    path('peoples/<str:team_requested>', views.people_search, name='people_search'),    
    path('person/<str:person_nick>', views.people_search, name='people_search'),
    
    # search ##################################################################################
    path('ESquick/<str:uuid>', es_sup.ESquick, name='es_quick'),
    path('runESadvSearch/<str:uuid>', es_sup.runESadvSearch, name='run_es_advanced_search'),
    path('reiterate/<str:sort_order>/<str:uuid>', es_sup.ESreiterateSearch, name='reiterateSearch'),
    path('<int:target_id>/hotsearch/<str:uuid>', es_sup.hotSearch, name='hot_search'),
    path('idfetch/', es_sup.id_fetch, name='idFetch'),
    path('search/', es_sup.quickSearch, name='quickSearch'),
    path('advsearch/<str:empty_search>/<str:uuid>', es_sup.advancedSearch, name='get_no-hit'), 
    path('advsearch/<str:uuid>', es_sup.advancedSearch, name='advanced-search'),
    path('advsearch/', es_sup.advancedSearch, name='advanced-search-get'),

    # endsearch ################################################################################
    path('workset_update/<str:selected_workset>/<str:uuid>', rinteract.workset_display_change, name='workset_display_change'),

]

## ckeditor links are in relix3/relix3/urls.py  (project-level)
############### RELIX3 ###########################################
