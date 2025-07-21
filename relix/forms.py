from django import forms
from django.forms import ModelForm
from relix.models import Notes
from ckeditor.widgets import CKEditorWidget
from ckeditor_uploader.widgets import CKEditorUploadingWidget


PRIORITY_CHOICES = (
    ('1', 'TODAY'),
    ('2', 'Urgent'),
    ('3', 'Important'),
    ('4', 'Normal'),
    ('5', 'Low'),
    ('0', '')
    )

STATUS_CHOICES = (
    ('1', 'WIP'),
    ('2', 'Next'),
    ('3', 'Cold'),
    ('4', 'Ongoing'),
    ('5', 'Hold'),
    ('6', 'Canceled'),
    ('8', 'Ref'),
    ('9', 'Done'),
    ('10', 'Pending done'),
    ('11', 'Pending cancel'),        
    ('0', '')
        )

GRID_ORDER_CHOICES = ( ( '1','1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), \
                               ('6','6'), ('7', '7'), ('8','8'), ('9','9'), ('-9','none') )

ADORN_CHOICES = ( ( '0','0'), ( '1','1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'))
    
# ckedit: SHOULD automatically invoke select widget on forms.
# maybe neomodel field types mess this up??
# https://docs.djangoproject.com/en/2.0/ref/models/fields/#choices



class LoginForm(forms.Form):
    username = forms.CharField(label='User name', max_length=100)
    password = forms.CharField(label='Password', max_length=100, \
                               widget=forms.PasswordInput)
    
class quickSearchForm(forms.Form):
    searchFx = forms.CharField(label='search term', max_length=100)

class idSearchForm(forms.Form):
    fetchID = forms.IntegerField(label='search PMID')

class todayForm(forms.Form):
    today_select = forms.CharField(label='today_select', required=True)


class advancedSearchForm(forms.Form):
    pmid = forms.IntegerField(label='PMid', required=False)
    title = forms.CharField(label='title', max_length=100, required=False)
    priority = forms.CharField(label='priority', max_length=20, required=False)
    status = forms.CharField(label='status', max_length=20, required=False)
    work_set = forms.CharField(label='work_set', max_length=40, required=False)
    noteText = forms.CharField(label='noteText', max_length=100, required=False)
    people = forms.CharField(label='people', max_length=50, required=False)    
    scope = forms.IntegerField(label='scope', required=False)
    scope_manual = forms.IntegerField(label='scope_manual', required=False)
    include_archived = forms.BooleanField(label='include_archived', required=False)
    webpage_set = forms.BooleanField(label='webpage_set', required=False)

    sectionhead_only = forms.BooleanField(label='sectionhead_only', required=False)
    
    startDate = forms.DateField(label='startDate', required=False)   
    endDate = forms.DateField(label='endDate', required=False)
    whichDate = forms.CharField(label='whichDate', max_length=20, required=False)
    uuid = forms.CharField(label='uuid',required=True)


class NotesStandardForm(forms.Form):
    # https://django-ckeditor.readthedocs.io/en/latest/#field
    # ok to contradict neomodel model field type, this is just for the form
    #noteText = forms.CharField(widget=CKEditorWidget(), required=False)

    # uncomment to use ckeditor
    noteText = forms.CharField(widget=CKEditorUploadingWidget(), required=False)
    # uncomment to revert to standard form text field
    #noteText = forms.CharField(label='noteText', widget=forms.Textarea, required=False)
    image_list = forms.CharField(widget=forms.Textarea, required=False)

    is_qnote = forms.CharField(label='is_qnote', max_length=4, required=True)
    return_me_to = forms.CharField(label='return_me_to', required=False)

    # pmid is needed for validation. Hide on form?
    pmid = forms.IntegerField(label='PMid', required=False)
    title = forms.CharField(label='title', max_length=400, required=False)
    
    priority = forms.ChoiceField(label='priority', choices=PRIORITY_CHOICES, required=False)
    status = forms.ChoiceField(label='status', choices=STATUS_CHOICES, required=False)
    
    topSort = forms.IntegerField(label='topSort', required=False, min_value=0, max_value=99)
    sectionhead = forms.BooleanField(label='sectionhead', required=False)
    #fields not edited: pmid, dtCreated, dtModified, created_by, isort

    assigned_to_peoples = forms.CharField(label='assigned to', max_length=80, required=False)
    involves_peoples = forms.CharField(label='involves', max_length=80, required=False)
    jumplink = forms.BooleanField(label='jumplink', required=False)
    jumplabel = forms.CharField(label='jumplabel', max_length=20, required=False)
    jumpcolor = forms.CharField(label='jumpcolor', max_length=10, required=False)
    gridItem = forms.BooleanField(label='gridItem', required=False)
    #grid_order = forms.ChoiceField(label='grid_order',choices=GRID_ORDER_CHOICES)
    work_set = forms.CharField(label='work_set', max_length=20, required=False)

    tagged_page = forms.BooleanField(label='tagged_page', required=False)
    shortlist_marker = forms.BooleanField(label='shortlist_marker', required=False)
    start_folded = forms.BooleanField(label='start_folded', required=False)
    meeting_master = forms.BooleanField(label='meeting_master', required=False)
    webpage_set = forms.BooleanField(label='webpage_set', required=False)

    
    adorn = forms.ChoiceField(label='adorn',choices=ADORN_CHOICES)
    uuid = forms.CharField(label='UUID', required=False) 

    remind_date = forms.DateField(label='reminder',required=False)

    windowsize = forms.IntegerField(label='windowSize', required=False)
    
    # size increased 2023-06-25
    mobile_input = forms.CharField(label='mobile_input', max_length=99999, required=False)


# ModelForm version of NotesModelForm threw a "not enough values to unpack (expected 2, got 1)"
#   error, somehow related to choices, when we moved to Django3

# class NotesModelForm(ModelForm):
#     # https://django-ckeditor.readthedocs.io/en/latest/#field
#     # ok to contradict neomodel model field type, this is just for the form
#     #noteText = forms.CharField(widget=CKEditorWidget(), required=False)

#     #comment this out, and uncomment the next statement to return to standard form text field
#     noteText = forms.CharField(widget=CKEditorUploadingWidget(), required=False)
#     #reverting to standard form text field
#     #noteText = forms.CharField(label='noteText', widget=forms.Textarea, required=False)

#     is_qnote = forms.CharField(label='is_qnote', max_length=4, required=True)
#     image_list = forms.CharField(widget=forms.Textarea, required=False)
#     return_me_to = forms.IntegerField(label='return_me_to', required=False)
   
#     class Meta:
#         model = Notes
#         #fields not edited: pmid, dtCreated, dtModified, created_by, isort
#         # pmid is needed for validation. Hide on form?
#         fields = ['pmid', 'title', 'priority', 'status', \
#                   'topSort', 'sectionhead', \
#                   'dtCreated', 'dtModified', \
#                   'assigned_to_peoples', 'involves_peoples', \
#                   'jumplink', 'jumplabel', 'jumpcolor', 'gridItem', 'grid_order', \
#                   'work_set', 'noteText', 'image_list', \
#                   'is_qnote', 'tagged_page', 'shortlist_marker', 'adorn']

class changeRelixForm(forms.Form):
    #targetID = forms.IntegerField(label='targetID', required=True)
    origLinkToID = forms.IntegerField(label='origLinkToID', required=True)
    origRelType = forms.CharField(label='origRelType', max_length=20, required=True)
    mode = forms.CharField(label='mode', max_length=10, required=True)
    relType = forms.CharField(label='relType', max_length=20, required=True)
    selectedLinkTo = forms.IntegerField(label='selectedLinkTo', required=False)
    pmidLinkTo = forms.IntegerField(label='pmidLinkTo', required=False)
    addToTaggedPages =forms.BooleanField(label='addTaggedPage', required=False)
    #return_me_to = forms.IntegerField(label='return_me_to', required=False)

class itemEditForm(forms.Form):
    #need this to avoid ugly errors if it tries to move or change priority
    #on a null node
    itemSelect = forms.IntegerField(label='selectedItems', required=True)
    grab = forms.IntegerField(label='itemGrab', required=False)
    pmid_manual = forms.IntegerField(label='pmid_manual', required=False)
    priority_change = forms.CharField(label='priority_change', required=False)
    status_change = forms.CharField(label='status_change', required=False)    
    return_me_to = forms.IntegerField(label='return_me_to', required=False)
    uuid = forms.CharField(label='UUID', required=False)    
    display_root = forms.IntegerField(label='display_root', required=False)
      
class newShortlistItemForm(forms.Form):
    new_shortitem_parent_pmid = forms.IntegerField(label='pmid_target', required=True)
    new_shortitem_priority = forms.CharField(label='priority', required=True)
    new_shortitem_title = forms.CharField(label='title', max_length=400, required=True)

class newGridGroupForm(forms.Form):
    new_gridgroup_name = forms.CharField(label='name', max_length=400, required=True)
    new_gridgroup_order = forms.CharField(label='order', required=True)
    new_gridgroup_color = forms.CharField(label='color',  required=False)
    workset = forms.CharField(label='workset',  required=True)

class GGassignForm(forms.Form):
        workset = forms.CharField(label='workset',  required=True)
        ass_length = forms.IntegerField(label='ass_length', required=True)

        ass_pmid_1 = forms.IntegerField(label='ass_pmid_1', required=False)            
        ass_pmid_2 = forms.IntegerField(label='ass_pmid_2', required=False)
        ass_pmid_3 = forms.IntegerField(label='ass_pmid_3', required=False)            
        ass_pmid_4 = forms.IntegerField(label='ass_pmid_4', required=False)
        ass_pmid_5 = forms.IntegerField(label='ass_pmid_5', required=False)            
        ass_pmid_6 = forms.IntegerField(label='ass_pmid_6', required=False)
        ass_pmid_7 = forms.IntegerField(label='ass_pmid_7', required=False)            
        ass_pmid_8 = forms.IntegerField(label='ass_pmid_8', required=False)
        ass_pmid_9 = forms.IntegerField(label='ass_pmid_9', required=False)            
        ass_pmid_10 = forms.IntegerField(label='ass_pmid_10', required=False)
        ass_pmid_11 = forms.IntegerField(label='ass_pmid_11', required=False)            
        ass_pmid_12 = forms.IntegerField(label='ass_pmid_12', required=False)
        ass_pmid_13 = forms.IntegerField(label='ass_pmid_13', required=False)
        ass_pmid_14 = forms.IntegerField(label='ass_pmid_14', required=False)
        ass_pmid_15 = forms.IntegerField(label='ass_pmid_15', required=False)
        ass_pmid_16 = forms.IntegerField(label='ass_pmid_16', required=False)
        ass_pmid_17 = forms.IntegerField(label='ass_pmid_17', required=False)
        ass_pmid_18 = forms.IntegerField(label='ass_pmid_18', required=False)
        ass_pmid_19 = forms.IntegerField(label='ass_pmid_19', required=False)
        ass_pmid_20 = forms.IntegerField(label='ass_pmid_21', required=False)
        ass_pmid_20 = forms.IntegerField(label='ass_pmid_22', required=False)                

        gg_order_1 = forms.IntegerField(label='gg_order_1', required=False)
        gg_order_2 = forms.IntegerField(label='gg_order_2', required=False)
        gg_order_3 = forms.IntegerField(label='gg_order_3', required=False)
        gg_order_4 = forms.IntegerField(label='gg_order_4', required=False)
        gg_order_5 = forms.IntegerField(label='gg_order_5', required=False)
        gg_order_6 = forms.IntegerField(label='gg_order_6', required=False)
        gg_order_7 = forms.IntegerField(label='gg_order_7', required=False)
        gg_order_8 = forms.IntegerField(label='gg_order_8', required=False)
        gg_order_9 = forms.IntegerField(label='gg_order_9', required=False)
        gg_order_10 = forms.IntegerField(label='gg_order_10', required=False)
        gg_order_11 = forms.IntegerField(label='gg_order_11', required=False)
        gg_order_12 = forms.IntegerField(label='gg_order_12', required=False)            
        gg_order_13 = forms.IntegerField(label='gg_order_13', required=False)            
        gg_order_14 = forms.IntegerField(label='gg_order_14', required=False)            
        gg_order_15 = forms.IntegerField(label='gg_order_15', required=False)            
        gg_order_16 = forms.IntegerField(label='gg_order_16', required=False)            
        gg_order_17 = forms.IntegerField(label='gg_order_17', required=False)            
        gg_order_18 = forms.IntegerField(label='gg_order_18', required=False)            
        gg_order_19 = forms.IntegerField(label='gg_order_19', required=False)            
        gg_order_20 = forms.IntegerField(label='gg_order_20', required=False)            
        gg_order_21 = forms.IntegerField(label='gg_order_21', required=False)            
        gg_order_22 = forms.IntegerField(label='gg_order_22', required=False)            

class StashRecallForm(forms.Form):
        pmid = forms.CharField(label='pmid', required=True)
