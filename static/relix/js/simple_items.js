$(document).ready(function() {

    $("div#optionBar").css("display","none");

    // try to prevent a click on item title from bubbling up to td handler,
    //  which opens the item details pane
    // see https://medium.com/@jacobwarduk/how-to-correctly-use-preventdefault-stoppropagation-or-return-false-on-events-6c4e3f31aedb
    //
    // this is probably in the wrong place, b/c
    // not every page has .item_title_linkout. should only be on those pages.
    const xitem_titles = document.querySelectorAll('.item_title_linkout');
    for ( i=0; i < xitem_titles.length; i++ )  {
	xitem_titles[i].addEventListener('click', event => event.stopPropagation());
    }
    // same for detail widgets
    const detail_widgets = document.querySelectorAll('ul.item_detail_widgets');						
    for ( i=0; i < detail_widgets.length; i++ )  {
	detail_widgets[i].addEventListener('click', event => event.stopPropagation());
    }
    // same for related items
    const related_linkouts = document.querySelectorAll('div.related a'); 
    for ( i=0; i < related_linkouts.length; i++ )  {
	related_linkouts[i].addEventListener('click', event => event.stopPropagation());
    }
    // same for fetch ancestors link, on flat list
    const anc_arrows = document.querySelectorAll('table.item_table.flat_list span.ancestor_fetch')
    for ( i=0; i < anc_arrows.length; i++ )  {
	anc_arrows[i].addEventListener('click', event => event.stopPropagation());
    }
    // and the parent links
    const p_crumb = document.querySelectorAll('table.item_table.flat_list div.parentCrumb')
    for ( i=0; i < p_crumb.length; i++ )  {
	p_crumb[i].addEventListener('click', event => event.stopPropagation());
    }
    // and shownote widget
    const shownote_widgets = document.querySelectorAll('span.shownote_widget');						
    for ( i=0; i < shownote_widgets.length; i++ )  {
	shownote_widgets[i].addEventListener('click', event => event.stopPropagation());
    }
    
    // timer for automated liveSave
    let hxtitle = $("div#headerx div.hxtitle a").text();
    if (hxtitle.indexOf("relix:j:Edit:") == 0 || hxtitle.indexOf("relix:j:Qnote:") == 0) {
	setInterval(function(){
	    dx = new Date();
	    liveSave();
	    console.log("Autosave check at "+dx.getHours()+':'+dx.getMinutes()+":"+dx.getSeconds());	    
	}, 60000);
    }

   
} );


function simpleNoteToggle(Bx)
{
    if ($("#"+Bx).css("display") == 'none') {
        $("#"+Bx).css("display","table-row");
        $("#"+Bx+" td").css("display","table-cell");
        
    } else {
        $("#"+Bx).css("display","none");
	$("#"+Bx+" td").css("display","none");
    }
}

function simpleDoneToggle()
{
    if ($("tr.status_9").css("display") == 'none') {
        $("tr.status_9").css("display","table-row");
        $("tr.status_9 td").css("display","table-cell");
        
    } else {
        $("tr.status_9").css("display","none");
	$("tr.status_9 td").css("display","none");
    }
}

function simplePriorityToggle()
{
    if ($("tr.not_hot").css("display") == 'none') {
        $("tr.not_hot").css("display","table-row");
        $("tr.not_hot td").css("display","table-cell");
	/* (re)hide done items */
        $("tr.status_9").css("display","none");
	$("tr.status_9 td").css("display","none");
	
    } else {
        $("tr.not_hot").css("display","none");
	$("tr.not_hot td").css("display","none");
    } 
}

function todayToggle()
{
    if ($("div#optionBar").css("display") == 'none') {
        $("div#optionBar").css("display","block");
	$("input#action_button_top.notes_button").css("display", "none");
    } else {
        $("div#optionBar").css("display","none");
	$("input#action_button_top.notes_button").css("display", "inline")
    }
}


function noreaderToggle()
{
    if ($("td.noreader").css("display") == 'none') {
        $("td.noreader").css("display","table-cell");
        $("th.noreader").css("display","table-cell");	
        
    } else {
        $("td.noreader").css("display","none");
        $("th.noreader").css("display","none");	
    }
}

function Elist_item_widgets_toggle(Bx)
{
    if ($("table.e_list tr#"+Bx+" div#detail_pane"+Bx).css("display") == 'none') {
        $("table.e_list tr#"+Bx+" div#detail_pane"+Bx).css("display","block");
    } else {
        $("table.e_list tr#"+Bx+" div#detail_pane"+Bx).css("display","none");
    }
}

/*
function assign_people_OLD(pmid){
    // replace the DOM element with the result from build_people_widget. beauty!
    uuid = $("input[name='uuid']").val();
    $("div.item_details_block ul#pf"+pmid).load('/relix/'+pmid+'/buildpeople/'+uuid);
}

function Elist_people_widgets_toggle_OLD(Bx)
{
    
    if ($("table.e_list tr#"+Bx+" div#people_pane"+Bx).css("display") == 'none') {
        $("table.e_list tr#"+Bx+" div#people_pane"+Bx).css("display","block");

	// prevent people pane click from toggling detail pane
	$("ul#pf"+Bx).click(function(event1) {
	    event1.stopPropagation();
	    //alert("trap_pw_click"+"ul#pf"+Bx);
	});
	
    } else {
        $("table.e_list tr#"+Bx+" div#people_pane"+Bx).css("display","none");
    }
}
*/

function assign_people(pmid){
    uuid = $("input[name='uuid']").val();
    if ($("table.e_list tr#"+pmid+" div#people_pane"+pmid).css("display") == 'none') {
	// pane is hidden so first build and load the element...

	// replace the DOM element with the result from build_people_widget. beauty!
	$("div#people_pane"+pmid).load('/relix/'+pmid+'/buildpeople/'+uuid);
	
	// ... then show it
        $("table.e_list tr#"+pmid+" div#people_pane"+pmid).css("display","block");
	// prevent people pane click from toggling detail pane
	$("div#people_pane"+pmid).click(function(event1) {
	    event1.stopPropagation();
	    //alert("trap_pw_click"+"ul#pf"+pmid);
	});
	
    } else {
	// hide the pane
        $("table.e_list tr#"+pmid+" div#people_pane"+pmid).css("display","none");
	// SHOULD NOT BE NEEDED  =====> update the ppl cell
	//$("td#item_people"+pmid).load('/relix/'+pmid+'/peoplecell/');
    }
    
}

function Elist_people_widgets_toggle(Bx)
{
    
    if ($("table.e_list tr#"+Bx+" div#people_pane"+Bx).css("display") == 'none') {
        $("table.e_list tr#"+Bx+" div#people_pane"+Bx).css("display","block");

	// prevent people pane click from toggling detail pane
	$("ul#pf"+Bx).click(function(event1) {
	    event1.stopPropagation();
	    //alert("trap_pw_click"+"ul#pf"+Bx);
	});
	
    } else {
        $("table.e_list tr#"+Bx+" div#people_pane"+Bx).css("display","none");
    }
}



function peopleChanged(Ix,whichList,nick,pmid)
{
    console.log("peopleChanged:",pmid,Ix.checked,whichList,nick);
    if (Ix.checked == false) {
	action = 'remove';
    } else {
	action = 'add';
    }
    console.log("action:",action)
    $.get('/relix/'+pmid+'/people_update/' + whichList + '/' + action + '/' + nick, {})
	.done(function (data) {
	    console.log(pmid + " " + whichList  + " " + nick + " " + action + ": people update completed <== ");
	    // update the ppl cell
	    $("td#item_people"+pmid).load('/relix/'+pmid+'/peoplecell/');
	})
	.fail(function (data) {
	    console.log(pmid + " " + whichList  + " " + nick + " " + action + ": people update failed <== " );
	})
    ;

}


function trap_pw_click(Bx)
{
    // prevent people pane click from toggling detail pane
    $("ul#pf"+Bx).click(function(event1) {
	event1.stopPropagation();
	alert("trap_pw_click"+"ul#pf"+Bx);
    });
}
function Elist_item_select_widgets_toggle()
{
    if ($("table.e_list span.item_select_widgets").css("display") == 'none') {
	$("table.e_list span.item_select_widgets").css("display", 'block');
    } else {
	$("table.e_list span.item_select_widgets").css("display", 'none');

    }
}

/* for e_item_list.html, this could be simplified, since columns aren't hidden (ex., for reader view) */
function childrenToggle(Bx)
{
    // Bx is an array of kid PMIDs
    // alert("which:"+includeArchived);
    // errors: items hidden by the Depth widget
    
    // if first child is invisible, make every (undone) thing invisible, and vice-versa
    // on, no, what if first child is "done"? or "archived"? :-(
    // need to march through kids and check
    // && ! $("tr#"+Bx[i]).hasClass("status_9") ) {
    showing = 'nix'
    
    for ( i=0; i < Bx.length; i++ )  {
	if ($("tr#"+Bx[i]).css("display") == 'table-row' ) {
	    showing = 'true'
        }
    }
    
    if ( showing == 'nix' )    {
	for ( i=0; i < Bx.length; i++ )  {
	    //if ( ! $("tr#"+Bx[i]).hasClass("status_9") ) {
	    $("tr#"+Bx[i]).css("display","table-row");
	    $("tr#"+Bx[i]+" td").css("display","table-cell");
	    //}
        }
    }
    else {
	for ( i=0; i < Bx.length; i++ )  {
            $("tr#"+Bx[i]).css("display","none");
	    $("tr#"+Bx[i]+" td").css("display","none");
	}
    }
    /* now restore reader view status */
    if ($("td.noreader").css("display") == 'none') {
        $("td.noreader").css("display","none");
        $("th.noreader").css("display","none");	
        
    } else {
        $("td.noreader").css("display","table-cell");
        $("th.noreader").css("display","table-cell");	
    }
}

function hideChildren(Bx)
{
    // stripped-down form of childrenToggle, for when page loads, and
    // start_folded kids must be hidden
    for ( i=0; i < Bx.length; i++ )  {
        $("tr#"+Bx[i]).css("display","none");
	$("tr#"+Bx[i]+" td").css("display","none");
    }
}
function showChildren(Bx)
{
    // symmetry for start_folded_toggle
    for ( i=0; i < Bx.length; i++ )  {
        $("tr#"+Bx[i]).css("display","table-row");
	$("tr#"+Bx[i]+" td").css("display","table-cell");
    }
}


function start_folded_toggle(pmid) {
    $.get('/relix/st_folded/' + pmid + '/', {})
	.done(function (data) {
	    console.log(pmid + " start folded ok <== "+data.state);
	    //console.log(pmid + " start folded ok <== "+data.children);
	    
	    if(data.state == "folded") {
		hideChildren(data.children);
	    } else {
		showChildren(data.children);
	    }
	    // toggle classes expando (show kids) and foldo (fold kids)
	    $("tr#"+pmid+".items td.id_cell_psd span").toggleClass("expando").toggleClass("foldo");
	    // toggle the highlight on the widget
	    $("tr#"+pmid+" li#sf"+pmid).toggleClass("sf_hilite");
	})
	.fail(function (data) {
	    console.log(pmid + " start folded failed <== ");
	},"json")
    ;
}
    


function showDepth(Bx)
{
    /* IF Bx = 3, set all BX < 3 to display, and all BX > 3 to hide */
    for (i = 0; i < 10; i++) {
        if ( i <= Bx ) {
            $("tr.path_length_"+i).css("display","table-row");
	    $("tr.path_length_"+i+" td").css("display","table-cell");
        } else {
            $("tr.path_length_"+i).css("display","none");
	    $("tr.path_length_"+i+" td").css("display","none");
	    // close any open notebody as well
            $("tr.psd_note_row").css("display","none");
	    $("tr.psd_note_row td").css("display","none");
        }
	/* re-hide the done items */
	$("tr.status_9").css("display","none");
	$("tr.status_9 td").css("display","none");
	
    }
}

function showWorkset(Bx,uuid)
{
    /* for item list: */
    /* see the j2_relix_base.html template for default option selection at page load */
    if (Bx == "All") {
    /* in service of mobile, if user selects anythihng, begin by turning it on. */
     $("td.jumplink_lozenges").css("display","inline-block");
	
        $("span#shortcutlist span.shortcut").css("display","inline-block");
	/* first item in pulldown list, no need to use JS to select it when
              you hit a page that has display_workset=All */
    } else if (Bx == "None") {
        $("span#shortcutlist span.shortcut").css("display","none");
	/* need to flick the pop-up to "None" */
	
    } else {
	/* turn them all off... */
        $("span#shortcutlist span.shortcut").css("display","none");
	/* then turn on the one you want... */
	/*alert(onLoadExecuted);*/
	if (onLoadExecuted) {
	    /* in service of mobile, if user selects anythihng, begin by turning it on. */
	    $("td.jumplink_lozenges").css("display","inline-block");
	}

        $("span#shortcutlist span.shortcut.workset_"+Bx).css("display","inline-block");
    }
    /* for grid: deactivated, b/c grid is now by-workset
    if (Bx == "None") {
        $("div#mainGrid div.gridCell").css("display","inline");
    } else {
        $("div#mainGrid div.gridCell").css("display","none");
        $("div#mainGrid div.gridCell.workset_"+Bx).css("display","inline");
    } */
    
    /* Data: update the display_workset session var, in case the user changed it */
    $.get('/relix/workset_update/' + Bx + '/' + uuid, {})
	.done(function (data) {
	    console.log(Bx + ": workset update completed <== ");
	})
	.fail(function (data) {
	    console.log(Bx + ": workset update failed <== " );
	})
    ;
}


function revealRel(x)
{
    $("table#rel_form tr.relpick").css("display","table-row");
    $("table#rel_form tr.relpick td").css("display","table-cell");
}


// ALL BELOW  needed to support Ajax delivery of content to server/////////////////////////////////////
// csrf approach is per the django doc's

function getCookie(name)
{
    // to help with CSRF token setting for grabCKcontent
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}


////////////////////////////////////////////////////////////////////////////////////////////////////

function liveSave(x)
{
    /* https://api.jquery.com/jQuery.ajax/
       had to use ajax, b/c other convenience methods didn't permit use of
       beforeSend to set up the csrf header token */
    //https://github.com/realpython/django-form-fun/blob/master/part1/main.js
    
    var csrftoken = getCookie('csrftoken');
    //https://stackoverflow.com/questions/1452871/how-can-i-access-iframe-elements-with-javascript
    var $ckContent = $("iframe.cke_wysiwyg_frame").contents().find("body").html();
    var $pmid = $("input#id_pmid").val()
    var $title = $("input#id_title").val()
    var $is_qnote = $("input#id_is_qnote").val()    
    
    var $priority = $("select#id_priority").val()
    var $status = $("select#id_status").val()    
    var $topSort = $("input#id_topSort").val()
    var $jumplabel = $("input#id_jumplabel").val()
    var $work_set = $("input#id_work_set").val()    
    var $grid_order = $("select#id_grid_order").val()
    var $image_list = $("textarea#id_image_list").val()
    
    if($("input#id_sectionhead").is(':checked')){
	$sectionhead = 'True';     }
    else { $sectionhead = 'False'; }
    
    if($("input#id_jumplink").is(':checked')){
	$jumplink = 'True';     }
    else { $jumplink = 'False'; }
    
    if($("input#id_gridItem").is(':checked')){
	$gridItem = 'True';     }
    else { $gridItem = 'False'; }
    
    $.ajax({
	url: '/relix/live_save/',
	type: 'POST',
	beforeSend: function(xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
		xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
	},
	data: {'ck_content': $ckContent, 'pmid':$pmid, 'title':$title, 'priority':$priority,
	       'status': $status, 'topSort': $topSort, 'sectionhead': $sectionhead,
	       'jumplink': $jumplink, 'jumplabel': $jumplabel, 'work_set': $work_set,
	       'gridItem': $gridItem, 'grid_order': $grid_order, 'image_list': $image_list,
	       'is_qnote': $is_qnote
	      },
	dataType: 'json',
	success: function (data) {
	    //alerts not needed if automated liveSave
	    //alert("completed <== ");
	},
	failure: function (data) {
	    //alert("failed <== ");
	    console.log("SI JS:autosave failed");
	}
	
    });
}

function priority_status_update(p_or_s) {
    // save priority and status on the ITEM LIST form
    //    (live save operates on the note edit form)
    var csrftoken = getCookie('csrftoken');
    
    //console.log($(p_or_s).closest("tr").attr( "id" ));
    
    // PMID comes from ID of the parent TR tag
    var $pmid = $(p_or_s).closest("tr.items").attr( "id" );
    console.log("pmid:" + $pmid);
    
    /* we want to get both Priority and Status, regardless of which one the user clicked on.
       so we can't use the simplest form, ex.,  var $new_status = $(p_or_s).val();  */
    
    var $new_priority = $("tr#"+$pmid+" td.priority select").val()
    var $new_status = $("tr#"+$pmid+" td.status select").val()
    console.log("NP:" + $new_priority +" NS:" + $new_status);
    
    $.ajax({
	url: '/relix/priority_status_update/',
	type: 'POST',
	beforeSend: function(xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
		xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
	},
	data: {'pmid':$pmid, 'priority':$new_priority, 'status': $new_status},
	dataType: 'json',
	success: function (data) {
	    //not sure if "success" waits until remote operation is complete, or just data push
	    // UPDATE ELASTICSEARCH
	    update_es_no_text($pmid);
	    console.log($pmid + " node updated completed <== ");
	},
	failure: function (data) {
	    console.log($pmid + " node update failed <== ");
	}
	
    });
    // update the styling to reflect the new value    
    $("tr#"+$pmid+" td.priority select").removeClass().addClass("ps_select priority_"+$new_priority);

    // Do I need to update the option "selected" attribute for both option lists?
    //    jquery seems to indicate it's already set (retrievable)
    
    //https://api.jquery.com/jquery.get/
}

function update_es_no_text(pmid) {
    $.get('/relix/es_refresh_no_text/' + pmid + '/', {})
	.done(function (data) {
	    console.log(pmid + " es update completed <== ");
	})
	.fail(function (data) {
	    console.log(pmid + " es update failed <== ");
	})
    ;
}


function tagged_page_toggle(pmid) {
    $.get('/relix/tag_page/' + pmid + '/', {})
	.done(function (data) {
	    console.log(pmid + " tagged page ok <== ");
	})
	.fail(function (data) {
	    console.log(pmid + " tagged page failed <== ");
	})
    ;
    
    $("tr#"+pmid+" li#tp"+pmid).toggleClass("tp_hilite")
}
    


function shortlist_toggle(pmid) {
    $.get('/relix/shorttoggle/' + pmid + '/', {})
	.done(function (data) {
	    console.log(pmid + " shortlist ok <== " + data );
	})
	.fail(function (data) {
	    console.log(pmid + " shortlist failed <== ");
	})
    ;
    
    $("tr#"+pmid+" li#sl"+pmid).toggleClass("sl_hilite")
}


// priority arrows on the GRID template
function parrow_toggle(pmid) {
    //console.log(pmid + " parrow hit <== ");
    if ($("div#"+pmid+".itemd span.p_arrows").css("display") == 'none')
	{
	    $("div#"+pmid+".itemd span.p_arrows").css("display","inline")
		} else {
	$("div#"+pmid+".itemd span.p_arrows").css("display","none")
	    }
    
}
function removeNullOption() {
    // remove option select values of "---------", which won't validate on form
    // remove_null_option class is on adorn, priority, and status
    // <option value="">---------</option>    
    // https://api.jquery.com/remove/
    $( "td.remove_null_option select option" ).remove( ":contains('---------')");

}

// hide "metadata" on rt_edit.html
function rt_header_toggle() {
    //console.log(pmid + " rtht hit <== ");
    if ($("div.rt_hier_rel_container").css("display") == 'none')
	{
	    $("div.rt_hier_rel_container").css("display","block");
	    $("table.rt_table").css("display","block")

		}
    else
	{
	    $("div.rt_hier_rel_container").css("display","none");
	    $("table.rt_table").css("display","none")
		}
}

// hide "metadata" on shownote.html
function shownote_header_toggle() {
    if ($("div.anc_crumb").css("display") == 'none')
	{
	    $("div.anc_crumb").css("display","block");
	}
    else
	{
	    $("div.anc_crumb").css("display","none");
	}
}

// hide metadata on detail.html
function toggle_detail_metadata() {
    if ($("div.detail_metadata").css("display") == 'none')
    {
	$("div.detail_metadata").css("display","block");
    }
    else
    {
	$("div.detail_metadata").css("display","none");
    }
}




// hide ancestor list on search/today results
function hide_search_ancestors() {
    //console.log(pmid + " rtht hit <== ");
    if ($("table.flat_list div.item_content_block div.parentCrumb").css("display") == 'none')
    {
	$("table.flat_list div.item_content_block div.parentCrumb").css("display","block");
    }
    else
    {
	$("table.flat_list div.item_content_block div.parentCrumb").css("display","none");
    }
}

function more_features(pmid){
    // replace the DOM element with the result from buildfeatures. beauty!
    uuid = $("input[name='uuid']").val();
    $("div.item_details_block ul#mf"+pmid).load('/relix/'+pmid+'/buildfeatures/'+uuid);
}


function ancestor_fetch(pmid){
    // for flat list, widget to retrieve/hide ancestor list
    var $pcb = $("tr#"+pmid+" div.item_content_block div.parentCrumb");
    if ($pcb.text().length > 0){
	$pcb.text("");
	$("span#af"+pmid).html("&uarr;")
    }
    else
    {
	//$("tr#"+pmid+" div.item_content_block div.parentCrumb").load('/relix/'+pmid+'/anc_list/');
	$pcb.load('/relix/'+pmid+'/anc_list/');
	$("span#af"+pmid).html("&darr;")
    }
}

function set_windowsize_field(){
    w = window.innerWidth;
    $("input[name='windowsize']").val(w)
}
