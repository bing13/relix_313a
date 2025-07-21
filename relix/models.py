from django.db import models
# Create your models here.
from django.urls import reverse
from django.contrib.auth.models import User
from datetime import datetime
from django_neomodel import DjangoNode
from neomodel import StructuredNode, StructuredRel, StringProperty, \
    DateTimeProperty, DateProperty,\
    IntegerProperty, BooleanProperty, RelationshipTo, RelationshipFrom, Relationship

class kRel(StructuredRel):
    type = StringProperty()

class ggRel(StructuredRel):
   type = StringProperty()

class teamRel(StructuredRel):
   type = StringProperty()

##class Notes(StructuredNode):
class Notes(DjangoNode):

    #http://neomodel.readthedocs.io/en/latest/properties.html#dates-and-times
    #dM an dC were older recepticles, which we will reuse.'''
    dtModified = DateTimeProperty()
    dtCreated = DateTimeProperty(default_now=True)
    dtAccessed = DateTimeProperty()    
    
    #ISO stamp last accessed, for "recent" view
    accessed = StringProperty()
    reminder_date = DateProperty()

    pmid = IntegerProperty(unique_index=True, editable=False)
    title   = StringProperty()    
    noteText = StringProperty() # solely in ES
    created_by = StringProperty()
    
    image_list = StringProperty()

    #ephemeral lists of related people to pass to the rt_edit form. never saved.
    assigned_to_peoples = StringProperty()
    involves_peoples = StringProperty()

    # only need upload in the forms, not the model. not a real field.
    #ck_image_upload = StringProperty()
    
    hasNote = BooleanProperty(default=False)
    topSort = IntegerProperty(default=50) # the two-digit manual sort override
    sectionhead = BooleanProperty(default=False)
    
    jumplink = BooleanProperty(default=False)
    jumplabel = StringProperty()
    jumpcolor = StringProperty()    
    
    gridItem = BooleanProperty(default=False)

    GRID_ORDER_CHOICES = ( ( '1','1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), \
                               ('6','6'), ('7', '7'), ('8','8'), ('9','9'), ('-9','none') )
    grid_order = StringProperty(choices = GRID_ORDER_CHOICES, default='-9')

    tagged_page = BooleanProperty(default=False)

    ADORN_CHOICES = ( ( '0','0'), ( '1','1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'))
    adorn = StringProperty(choices = ADORN_CHOICES, default='0')
    
    ####################################################################
    #there is also RelationshipFrom, and non-dir Relationship
    relates = RelationshipTo('Notes', 'RELATES', model=kRel)
    child_of = RelationshipTo('Notes', 'CHILD_OF', model=kRel)
    prev_instance = RelationshipTo('Notes', 'PREV_INSTANCE', model=kRel)
    # note, rel_content is bi-directional
    rel_content = Relationship('Notes', 'REL_CONTENT', model=kRel)
    group_items = RelationshipTo('Group','GROUP_ITEMS')
    ####################################################################
    ws_belongs = RelationshipTo('Work_set', 'WS_BELONGS', model=kRel)
    gg_belongs = RelationshipTo('GridGroup','GG_BELONGS', model=ggRel)
    ####################################################################
    assigned_to = RelationshipTo('People', 'ASSIGNED_TO')
    involves  = RelationshipTo('People', 'INVOLVES')
    ##################################################
    
    # 2020-12-25 changed '0' value to '-'; was ''
    #   it's a little ugly, but needed to pass the W3C validator
    PRIORITY_CHOICES = (
        ('1', 'TODAY'),
        ('2', 'Urgent'),
        ('3', 'Important'),
        ('4', 'Normal'),
        ('5', 'Low'),
        ('0', '-')
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
        ('0', '-')
        )
    
    # cku
    # SHOULD automatically invoke select widget on forms.
    # Neomodel *does* support choice on strings, according to docs
    # https://docs.djangoproject.com/en/2.0/ref/models/fields/#choices
    priority = StringProperty(choices=PRIORITY_CHOICES, default='0')
    status = StringProperty(choices=STATUS_CHOICES, default='0')
    #priority = IntegerProperty(choices=PRIORITY_CHOICES, default=0)
    #status = IntegerProperty(choices=STATUS_CHOICES, default=0)

    archived = BooleanProperty(default=False)
    oneNote = BooleanProperty(default=False)

    # shortlist is a relationship, this is just to pass status info
    #   to/from the display template (CSS highlighting)
    shortlist_marker = BooleanProperty(default=False)

    # page with a collection of web page pointers.
    #   goal is to reduce habit of keeping huge # of pages open,
    #   most of them generally inactive
    webpage_set = BooleanProperty(default=False)
    
    start_folded = BooleanProperty(default=False)
    meeting_master = BooleanProperty(default=False)
    #######################################################
    
    class Meta:
        app_label = 'notesapplabel'
        #ordering = ['title']

    def __str__(self):
        return self.title

    # for generic views
    def get_absolute_url(self):
        return reverse('relix_nm:viewTree',args=(self.pmid) )

    #### THESE RETURN NODES ##########################
    def children_and_self(self, usern, depth):
        '''extend to accept depth of traversal, if !done items only, and username'''
        cypherx = "MATCH p = (m)-[:CHILD_OF*0..%s]->(n:Notes) WHERE elementId(n)=$self AND \
        m.created_by='%s' RETURN m ORDER BY length(p)" % (depth, usern)
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    def children_and_self_w_arc(self, usern, depth):
        '''extend to accept depth of traversal, if !done items only, and username'''
        cypherx = "MATCH p = (m)-[:CHILD_OF*0..%s]->(n:Notes) WHERE elementId(n)=$self AND \
        m.created_by='%s' RETURN m ORDER BY length(p)" % (depth, usern)
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    def children_and_self_no_arc(self, usern, depth):
        '''extend to accept depth of traversal, if !done items only, and username'''
        cypherx = "MATCH p = (m)-[:CHILD_OF*0..%s]->(n:Notes) WHERE elementId(n)=$self AND \
        m.created_by='%s' AND NOT m.archived RETURN m ORDER BY length(p)" % (depth, usern)
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    ### 4 Grid-related methods ###############################
    
    def important_kids(self, usern, depth):
        ''' like children_and_self, but w/additional filter for importance and status
            does not currently knock out kids that should appear on lower-level parents'''
        cypherx = 'MATCH (m)-[:CHILD_OF*0..%s]->(n:Notes) WHERE elementId(n)=$self  \
        AND m.priority in ["1","2","3","4"] \
        AND NOT m.status in ["6","9"] \
        AND m.created_by="%s" RETURN m ORDER BY m.priority, toLower(m.title) ' % (depth, usern)
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]
        
    def gridAncestorList(self, usern):
        '''return all ancestor NODES that are GRIDITEMS'''
        cypherx = "MATCH p = (m) -[:CHILD_OF*..44]-> (n) \
        WHERE elementId(m)=$self AND n.created_by='%s' AND n.gridItem=TRUE \
        RETURN n ORDER BY length(p)" % usern
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    ## A TRUE NO-NODE CYPHER QUERY ###########################
    ## see rutils.allGridItemDescendants(usern)
    
    ## gridItemsForWorkset is a Work_set method, below

    ### THESE RETURN IDS #####################################
    def children_ids_w_arc(self):
        '''convenience function for archive processing; also template, 
           esp. progressive disclosure widget (cannot pass parameters)
           RETURNS PMID'''
        cypherx = "MATCH (m)-[:CHILD_OF*0..%s]->(n:Notes) WHERE elementId(n)=$self RETURN m.pmid " % (5)
        results, columns = self.cypher(cypherx)
        if len(results) > 0:
            return [ x[0] for x in results[1:] ]
        else:
            return []
        
    def children_ids_no_arc(self):
        '''convenience function for template, esp. progressive disclosure widget (cannot pass parameters)'''
        # depth was 5 until 12/22/2018
        cypherx = "MATCH (m)-[:CHILD_OF*0..%s]->(n:Notes) WHERE elementId(n)=$self AND NOT m.archived RETURN m.pmid " % (25)
        results, columns = self.cypher(cypherx)
        if len(results) > 0:
            return [ x[0] for x in results[1:] ]
        else:
            return []

        
    def get_pathLength(self,destinationID):
        '''return the integer path distance to a child node from a parent'''
        cypherx="MATCH p=(m)-[:CHILD_OF*0..15]->(n {pmid:%s }) WHERE elementId(m)=$self \
        RETURN length(p) as pathLength" % destinationID
        results, columns = self.cypher(cypherx)
        if len(results) > 0:
            return results[0][0]
        else:
            return 0

    def parents(self,usern):
        '''return parent NODES; could be more than one parent'''
        cypherx = "MATCH (m)<-[:CHILD_OF]-(n:Notes) WHERE elementId(n)=$self AND m.created_by='%s'\
        RETURN m " % usern
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    def parents_any_owner(self):
        '''return parent NODES from ANY owner. ONLY For finding data integrity issues.'''
        cypherx = "MATCH (m)<-[:CHILD_OF]-(n:Notes) WHERE elementId(n)=$self RETURN m " 
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    def ancestorList(self, usern):
        '''return all ancestor NODES'''
        cypherx = "MATCH p = (m) -[:CHILD_OF*..44]-> (n) WHERE elementId(m)=$self AND n.created_by='%s'\
        RETURN n ORDER BY length(p)" % usern
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    def descendant_of(self, ancestorID):
        ''' if self is a descendant of pmid=ancestorID node, return True, else False'''
        #cypherx ="MATCH (n) -[:CHILD_OF*..44]-> (m {pmid:%s}) WHERE elementId(n)=$self RETURN exists(m.pmid)" % ancestorID
        cypherx ="MATCH (n) -[:CHILD_OF*..44]-> (m {pmid:%s}) WHERE elementId(n)=$self RETURN m.pmid IS NOT NULL" % ancestorID
        results, columns = self.cypher(cypherx)
        if len(results) > 0 and len(results[0]) > 0:
            return True
        return False

    def descendants(self):
        ''' return all descendants of self'''
        cypherx ="MATCH (m) -[:CHILD_OF*..44]-> (n) WHERE elementId(n)=$self RETURN m" 
        results, columns = self.cypher(cypherx)
        return [self.inflate(row[0]) for row in results]

    def count_of_descendants(self):
        ''' return count of all descendants of self'''
        cypherx ="MATCH (m) -[:CHILD_OF*..44]-> (n) WHERE elementId(n)=$self RETURN count(m)" 
        results, columns = self.cypher(cypherx)
        return results[0][0]
    
    def delete_me_and_relationships(self, usern):
        ''' delete node and its relationships'''
        cypherx ="MATCH (n) WHERE elementId(n)=$self AND n.created_by='%s' DETACH DELETE n" % usern
        results, columns = self.cypher(cypherx)
        return

    #########################################################
    def get_workset_name(self):
        '''seems slow'''
        wsba = self.ws_belongs.all()
        if len(wsba) == 0:
            return(None)
        else:
            return(wsba[0].name)
    
    ### get_foo_property doesn't seem to be supported in neomodel, so we do it by hand
    PRIO_CHX_DICT = {}
    STAT_CHX_DICT = {}
    #WSET_CHX_DICT = {}
    for num, displayLabel in PRIORITY_CHOICES: PRIO_CHX_DICT[num] = displayLabel
    for num, displayLabel in STATUS_CHOICES: STAT_CHX_DICT[num] = displayLabel


    def priority_chx(self):
        '''return display value for a given choice'''
        return self.PRIO_CHX_DICT[self.priority]
    def status_chx(self):
        '''return display value for a given choice'''
        return self.STAT_CHX_DICT[self.status]

#######################################################
 
class Work_set(DjangoNode):
    '''Work_set is a node type, to which notes are linked.'''

    #aid = models.AutoField(primary_key = True)
    v4id = IntegerProperty()    
    name   = StringProperty()
    created_by = StringProperty()
    ####################################################################
    ws_belongs = RelationshipFrom('Notes', 'WS_BELONGS', model=kRel)
    #??? why kRel???
    ####################################################################
    
    def delete_ws_and_relationships(self, usern):
        ''' delete Work_set node and its relationships'''
        cypherx ="MATCH (w) WHERE elementId(w)=$self AND w.created_by='%s' DETACH DELETE w" % usern
        results, columns = self.cypher(cypherx)
        return results

    def gridItemsForWorkset(self, usern):
        '''return all gridItems (i.e., grid "parent" items) for a given workset. Note that the method is on a
           WORK_SET item, but it inflates NOTES. '''
        cypherx = "MATCH (n:Notes) -[:WS_BELONGS]-> (w) \
        WHERE elementId(w)=$self AND n.created_by='%s' AND n.gridItem=TRUE \
        RETURN n ORDER BY n.grid_order, toLower(n.title)" % (usern)
        results, columns = self.cypher(cypherx)
        return [Notes.inflate(row[0]) for row in results]
    


class People(StructuredNode):
    '''People to associate with Notes'''
    
    #aid = models.AutoField(primary_key = True)
    v4id = IntegerProperty()
    nickname = StringProperty()
    created_by = StringProperty()
    assigned_from = RelationshipFrom('Notes', 'ASSIGNED_TO')
    involved_with  = RelationshipFrom('Notes', 'INVOLVES')
    is_member = RelationshipFrom('Team','TEAM_MEMBERS')
    dormant = BooleanProperty(default=False)

class Group(StructuredNode):
    '''Items to appear on a special list'''

    #aid = models.AutoField(primary_key = True)
    v4id = IntegerProperty()
    group_name = StringProperty()
    created_by = StringProperty()
        
    group_items = RelationshipFrom('Notes','GROUP_ITEMS')


class GridGroup(DjangoNode):
    '''Groups for grouping grid items on grid display.
       Have a grid title, grid order, and color.'''

    GRIDGROUP_ORDER_CHOICES = ( ( '1','1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), \
                               ('6','6'), ('7', '7'), ('8','8'), ('9','9'), ('-9','none') )

    #aid = models.AutoField(primary_key = True) 
    v4id = IntegerProperty()
    grid_group_name = StringProperty()

    #gg_belongs on Notes class is "reciprocal"
    gg_members = RelationshipFrom('Notes','GG_MEMBERS', model=ggRel)
    # ex:
    #        some_gg_node.grid_group_member.connect(some_note_node)
    #        some_gg_node.grid_group_member.all()    
    #        gg[0].gg_members.is_connected(gen)
    grid_group_color = StringProperty()    
    grid_group_order = StringProperty(choices = GRIDGROUP_ORDER_CHOICES, default='-9')
    work_set = StringProperty()    
    created_by = StringProperty()

#https://github.com/neo4j-contrib/django-neomodel
#    says DjangoNode is for Model forms and signals
# https://neomodel.readthedocs.io/en/latest/properties.html#unique-identifiers
#  says don't try to use property ID, which is the neo4j id. Use UniqueIdProperty() instead. [???]

class Team(StructuredNode):
    '''Teams will group people'''

    TEAM_CHOICES = [("0", "-none-"), ("1", "a/v"), ("2", "admin"), ("3", "appsadmin"), ("4", "bizsystems"), ("5", "brm"), ("6", "cyber"), ("7", "data"), ("8", "data center"), ("9", "endpoint"), ("10", "exec"), ("11", "iam"), ("12", "library"), ("13", "network"), ("14", "platforms"), ("15", "pmo"), ("16", "scipub"), ("17", "servicedesk"), ("18", "snow"), ("19", "vendor")]

    team_name = StringProperty(choices = TEAM_CHOICES, default="0")
    team_members = RelationshipTo('People','TEAM_MEMBERS', model=teamRel)
    created_by = StringProperty()
