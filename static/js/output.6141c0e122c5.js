;var CURRENT_PLAYER=null;var CURRENT_MATCH=null;var CURRENT_TIMEOUT=null;var delay_k=0;if(/Android|Mobi/i.test(navigator.userAgent)){delay_k=2000;}
function jumpToTime(e,loop,play_all){if(CURRENT_MATCH!=null){CURRENT_MATCH.classList.remove('stopped','playing','paused','looped')}
if(CURRENT_PLAYER){var result_container=e.closest(".result-container");if(result_container&&CURRENT_PLAYER.a!=result_container.getElementsByClassName("player-container")[0]){CURRENT_PLAYER.pauseVideo();}}
if($(e.parentElement).hasClass("match-wrap")){var match_wrap=e.parentElement;}
else if(e.attributes.id.value=="blank-match-wrap"||$(e).hasClass("match-wrap")){var match_wrap=e;}
else{console.log("Match wrap doesnt valid");return;}
var player_container=match_wrap.parentElement.parentElement.parentElement.parentElement.querySelector('.player-container')
var video_id=match_wrap.attributes.video_id.value;var startTime=parseInt(match_wrap.attributes.start_time.value);var endTime=parseInt(match_wrap.attributes.end_time.value);var player=YT.get(video_id);if(player==undefined){player=createPlayer(video_id,startTime,endTime,loop);CURRENT_PLAYER=player;CURRENT_MATCH=match_wrap;CURRENT_MATCH.attributes.loop.value=loop;CURRENT_MATCH.attributes.play_all.value=play_all;return;}
CURRENT_PLAYER=player;CURRENT_MATCH=match_wrap;CURRENT_MATCH.attributes.loop.value=loop;CURRENT_MATCH.attributes.play_all.value=play_all;player.addEventListener('onStateChange',checkPlayerStatus);player.seekTo(startTime);player.playVideo();function checkPlayerStatus(event){var loop=CURRENT_MATCH.attributes.loop.value;var play_all=CURRENT_MATCH.attributes.play_all.value;if(loop=="true"){addClassToElement(CURRENT_MATCH,'looped');}
if(event.data==0){CURRENT_MATCH.classList.remove('stopped','playing','paused');addClassToElement(CURRENT_MATCH,'stopped');CURRENT_PLAYER=null;};if(event.data==1){if(CURRENT_PLAYER&&CURRENT_PLAYER!=event.target){CURRENT_PLAYER.pauseVideo();}
CURRENT_PLAYER=event.target;addClassToElement(CURRENT_MATCH,'showed');CURRENT_MATCH.classList.remove('stopped','playing','paused');addClassToElement(CURRENT_MATCH,'playing');var player=event.target;var startTime=parseInt(CURRENT_MATCH.attributes.start_time.value)
var endTime=parseInt(CURRENT_MATCH.attributes.end_time.value)
var currentTime=parseInt(player.getCurrentTime());if(startTime<=currentTime&&currentTime<endTime){p_left_time=endTime-player.getCurrentTime();p_left_time=p_left_time*1000;p_left_time=parseInt(p_left_time)+delay_k;if(loop=="true"){var timeout=setTimeout(function(){player.seekTo(startTime);},p_left_time);CURRENT_TIMEOUT=timeout;}
else if(play_all=="true"){var next_match=CURRENT_MATCH.nextElementSibling;if(next_match!=null){if(CURRENT_MATCH.previousElementSibling!=null){var match_container=CURRENT_MATCH.parentElement;scrollToElm(match_container,CURRENT_MATCH.previousElementSibling,600);}
var timeout=setTimeout(function(){jumpToTime(next_match,'false','true')},p_left_time);CURRENT_TIMEOUT=timeout;}
else{var timeout=setTimeout(function(){player.pauseVideo();},p_left_time);CURRENT_TIMEOUT=timeout;}}
else{var timeout=setTimeout(function(){player.pauseVideo();},p_left_time);CURRENT_TIMEOUT=timeout;}
function stopTimeout(){clearTimeout(timeout);};player.addEventListener('onStateChange',stopTimeout);}
else{CURRENT_MATCH.classList.remove('stopped','playing','paused');CURRENT_MATCH=null;}}
if(event.data==2){CURRENT_MATCH.classList.remove('stopped','playing','paused');addClassToElement(CURRENT_MATCH,'paused');};};};function thumbPlay(e){var match=e.nextElementSibling.getElementsByClassName('match')[0];match.click();}
function createPlayer(video_id,startTime,endTime,loop,play_all){var player_container=document.getElementById(video_id)
var height=player_container.clientHeight.value+'px'
var width=player_container.clientHeight.value+'px'
var player=new YT.Player(video_id,{height:height,width:width,videoId:video_id,host:'https://www.youtube.com',playerVars:{enablejsapi:1},events:{'onReady':onReady,'onStateChange':checkPlayerStatus}})
return player;function onReady(event){var player=event.target;player.seekTo(startTime);var thumb=player.a.nextElementSibling;thumb.style.visibility='hidden';};function checkPlayerStatus(event){var loop=CURRENT_MATCH.attributes.loop.value;var play_all=CURRENT_MATCH.attributes.play_all.value;if(loop=="true"){addClassToElement(CURRENT_MATCH,'looped');}
if(event.data==0){CURRENT_MATCH.classList.remove('stopped','playing','paused');addClassToElement(CURRENT_MATCH,'stopped');CURRENT_PLAYER=null;};if(event.data==1){if(CURRENT_PLAYER&&CURRENT_PLAYER!=event.target){CURRENT_PLAYER.pauseVideo();}
CURRENT_PLAYER=event.target;addClassToElement(CURRENT_MATCH,'showed');CURRENT_MATCH.classList.remove('stopped','playing','paused');addClassToElement(CURRENT_MATCH,'playing');var player=event.target;var startTime=parseInt(CURRENT_MATCH.attributes.start_time.value)
var endTime=parseInt(CURRENT_MATCH.attributes.end_time.value)
var currentTime=parseInt(player.getCurrentTime());if(startTime<=currentTime&&currentTime<endTime){p_left_time=endTime-player.getCurrentTime();p_left_time=p_left_time*1000;p_left_time=parseInt(p_left_time)+delay_k;if(loop=="true"){var timeout=setTimeout(function(){player.seekTo(startTime);},p_left_time);CURRENT_TIMEOUT=timeout;}
else if(play_all=="true"){var next_match=CURRENT_MATCH.nextElementSibling;if(next_match!=null){if(CURRENT_MATCH.previousElementSibling!=null){var match_container=CURRENT_MATCH.parentElement;scrollToElm(match_container,CURRENT_MATCH.previousElementSibling,600);}
var timeout=setTimeout(function(){jumpToTime(next_match,'false','true')},p_left_time);CURRENT_TIMEOUT=timeout;}
else{var timeout=setTimeout(function(){player.pauseVideo();},p_left_time);CURRENT_TIMEOUT=timeout;}}
else{var timeout=setTimeout(function(){player.pauseVideo();},p_left_time);CURRENT_TIMEOUT=timeout;}
function stopTimeout(){clearTimeout(timeout);};player.addEventListener('onStateChange',stopTimeout);}
else{CURRENT_MATCH.classList.remove('stopped','playing','paused');CURRENT_MATCH=null;}}
if(event.data==2){CURRENT_MATCH.classList.remove('stopped','playing','paused');addClassToElement(CURRENT_MATCH,'paused');};};};function thumbPlayNoSpeech(e){if(CURRENT_PLAYER){CURRENT_PLAYER.pauseVideo();}
var result_container=e.closest('.result-container');var video_id=result_container.attributes.id.value.replace('result-','')
var player=createPlayerNoSpeech(video_id);CURRENT_PLAYER=player;}
function createPlayerNoSpeech(video_id){var player_container=document.getElementById(video_id)
var height=player_container.clientHeight.value+'px'
var width=player_container.clientHeight.value+'px'
var player=new YT.Player(video_id,{height:height,width:width,videoId:video_id,host:'https://www.youtube.com',playerVars:{enablejsapi:1},events:{'onReady':onReadyPlay,'onStateChange':pauseOtherPlayers}})
return player;function onReadyPlay(event){var player=event.target;player.playVideo();var thumb=player.a.nextElementSibling;thumb.style.visibility='hidden';};function pauseOtherPlayers(event){if(event.data==1){if(CURRENT_PLAYER&&CURRENT_PLAYER!=event.target){CURRENT_PLAYER.pauseVideo();}
CURRENT_PLAYER=event.target;}}}
function addClassToElement(e,class_name){if(e!=null&&!e.classList.contains(class_name)){e.className=e.className+' '+class_name;}};function playAllMatches(e){var match_container_wrap=$(e).closest(".match-container-wrap")[0];var match=match_container_wrap.getElementsByClassName("match")[0];jumpToTime(match,"false","true");}
function showVolumeInfo(e){$(e).prev().slideToggle('fast');var logo=$(e).children('.volume-slide-logo');$(logo).fadeOut(300,function(){if($(logo).hasClass("logo-rotate")){$(logo).removeClass("logo-rotate")}
else{$(logo).addClass("logo-rotate");};$(logo).fadeIn(300);});};;function updateTime(e,input_id,seconds=false){if(seconds==true){var time_input=document.getElementById(input_id);time_input.value=getStringTime(e.value);return;}
var hours=parseInt(e.value/60);var minutes=e.value-hours*60;if(hours<10||hours==0){hours="0"+hours.toString();};if(minutes<10||minutes==0){minutes="0"+minutes.toString();};var time_input=document.getElementById(input_id);time_input.value=hours+":"+minutes;};function getStringTime(total_seconds){var hours=parseInt(total_seconds/3600);var minutes=parseInt((total_seconds-hours*3600)/60);var seconds=total_seconds-hours*3600-minutes*60;if(hours<10||hours==0){hours="0"+hours.toString();};if(minutes<10||minutes==0){minutes="0"+minutes.toString();};if(seconds<10||seconds==0){seconds="0"+seconds.toString();};var res=hours+":"+minutes+":"+seconds;return res;};function stringTimeToSecs(string_time){var arr_string_time=string_time.split(":");var hours=parseInt(arr_string_time[0]);var minutes=parseInt(arr_string_time[1]);var seconds=parseInt(arr_string_time[2]);var result=hours*3600+minutes*60+seconds;return result;}
function updateRange(e,range_id,seconds=false){var time_input=e.value.split(':');var range_input=document.getElementById(range_id);if(time_input==""){return;}
if(seconds==true){var seconds=parseInt(time_input[0]*3600)+parseInt(time_input[1]*60)+parseInt(time_input[2]);range_input.value=seconds;}
else{var seconds=parseInt(time_input[0]*60)+parseInt(time_input[1]);range_input.value=seconds;}};function resetRange(e,range_id){var range_input=document.getElementById(range_id);range_input.value=0;};;function scrollToElm(container,elm,duration){var pos=getRelativePos(elm);scrollTo(container,pos.top,2);}
function getRelativePos(elm){var pPos=elm.parentNode.getBoundingClientRect(),cPos=elm.getBoundingClientRect(),pos={};pos.top=cPos.top-pPos.top+elm.parentNode.scrollTop,pos.right=cPos.right-pPos.right,pos.bottom=cPos.bottom-pPos.bottom,pos.left=cPos.left-pPos.left;return pos;}
function scrollTo(element,to,duration,onDone){var start=element.scrollTop,change=to-start,startTime=performance.now(),val,now,elapsed,t;function animateScroll(){now=performance.now();elapsed=(now-startTime)/1000;t=(elapsed/duration);element.scrollTop=start+change*easeInOutQuad(t);if(t<1)
window.requestAnimationFrame(animateScroll);else
onDone&&onDone();};animateScroll();}
function easeInOutQuad(t){return t<.5?2*t*t:-1+(4-2*t)*t};;function loadRestMatches(e){if(!e){return;}
var box=e.parentElement.parentElement;var last_match_wrap=e.parentElement.previousElementSibling;var match_container=e.parentElement.parentElement.parentElement;var matches_left=match_container.attributes.matches_left.value;var end_id=match_container.attributes.end_id.value;var video_id=last_match_wrap.attributes.video_id.value;var urlParams=new URLSearchParams(window.location.search);var request=urlParams.get('speech');var exact=urlParams.get('exact');var load_icon=e.querySelector('.load-icon');var load_more_button_wrap=e.parentElement;$.ajax({url:'/api/rest_matches/',data:{'request':request,'exact':exact,'id':video_id,'end_id':end_id},dataType:'json',beforeSend:function(){$(load_icon).fadeIn(200);},complete:function(data){$(load_icon).fadeOut(200,function(){$(load_more_button_wrap).insertAfter(last_match_wrap);var matches_left=data.responseJSON.matches_left;var dom_matches_left=match_container.parentElement.querySelector('.count-left-matches');var dom_matches_value=dom_matches_left.querySelector('.left-matches-value');if(matches_left==0){$(load_more_button_wrap).remove()
if(dom_matches_left){$(dom_matches_left).fadeOut(200)}}
else{$(dom_matches_value).fadeOut(200,function(){$(this).text(matches_left).fadeIn(200)})}})
$(box).on('scroll',setCheckScrolled);},success:function(data){if(data.matches){match_container.attributes.end_id.value=data.end_id;match_container.attributes.matches_left.value=data.matches_left;for(i=0;i<data.matches.length;i++){var new_match_wrap=last_match_wrap.cloneNode(true);var new_match_id=parseInt(data.last_match_id)+i+1;new_match_wrap.attributes.id.value='match-'+video_id+'-'+new_match_id;new_match_wrap.attributes.start_time.value=data.matches[i].startTime;new_match_wrap.attributes.end_time.value=data.matches[i].endTime;new_match_wrap.attributes.start_id.value=data.matches[i].start_id;new_match_wrap.attributes.end_id.value=data.matches[i].end_id;new_match_wrap.querySelector('.match-time').innerText=data.matches[i].startTime_formated;new_match_wrap.querySelector('.match-text').innerHTML='...'+data.matches[i].match+'...';last_match_wrap.parentElement.appendChild(new_match_wrap);last_match_wrap=new_match_wrap;}
$(window).trigger("resize.scrollBox");}
else{match_container.attributes.end_id.value=-1;}}})};function updateTabs(){var type=getUrlParameter('type');if(type){if(type=='speech'){return;}
var tab=document.getElementById('tab-'+type);changeTab(tab,'100%','100%','false');}
else{var tab=document.getElementById('tab-speech');$(tab).addClass('current-tab');}}
function swap(a,b){a=$(a);b=$(b);var tmp=$('<span>').hide();a.before(tmp);b.before(a);tmp.replaceWith(b);};function changeTab(e,main_input_width,optional_inputs_width,clear_option){if($(e).hasClass('current-tab')){return;}
else if(e.attributes.id.value=='tab-speech'&&$(e).hasClass('active-tab')){return;}
else{var active_tab=document.querySelector('.active-tab');$(active_tab).removeClass('active-tab');var tab_curr=document.querySelector('.current-tab');$(tab_curr).removeClass('current-tab');$(e).addClass('current-tab');var type=document.getElementById('id_type');type.value=e.attributes.id.value.replace('tab-','');var blank_input=document.querySelector('.blank.input');var curr_input=document.querySelector('.container-main-inputs').children[0];var curr_margin=$(curr_input).css('margin-bottom');if(clear_option=='true'){TAGIFY_WITH_VALUES.forEach(function(e){e.removeAllTags();})
var inputs=document.querySelector('form').querySelectorAll('input')
inputs.forEach(function(e){if(e.attributes.type.value=='range'){e.value=0;e.dispatchEvent(new Event('change'));}
else{e.value=null;}})}
if(e.attributes.id.value=='tab-title'){var next_input=document.getElementsByClassName('title input')[0];}
if(e.attributes.id.value=='tab-description'){var next_input=document.getElementsByClassName('description input')[0];}
if(e.attributes.id.value=='tab-tags'){var next_input=document.getElementsByClassName('tags input')[0];}
if(e.attributes.id.value=='tab-speech'){var next_input=document.getElementById('speech-input');}
var next_parent=$(next_input).closest('.options');var next_margin=$(next_input).css('margin-left');swap(blank_input,curr_input);swap(blank_input,next_input);$(curr_input).closest('.options').removeClass('blank');$(next_parent).addClass('blank');next_input.style.width=main_input_width;next_input.style.margin_bottom=curr_margin;curr_input.style.width=optional_inputs_width;curr_input.style.margin_bottom=next_margin;}}
function showAdvSettings(){$(".search-options-wrap").slideToggle(300);};function submitForm(){var form=document.querySelector('form');$(form).submit(function(e){var emptyinputs=$(this).find('input').filter(function(){return!$.trim(this.value).length;}).prop('disabled',true);});form.querySelectorAll('input[type=text]').forEach(function(e){if(e.value){var res=[]
try{v=JSON.parse(e.value)
v.forEach(function(t){res.push(t.value)})}
catch(e){return false;}
e.value=res.join(',');}})
$('form').submit();};function getUrlParameter(sParam){var sPageURL=window.location.search.substring(1),sURLVariables=sPageURL.split('&'),sParameterName,i;for(i=0;i<sURLVariables.length;i++){sParameterName=sURLVariables[i].split('=');if(sParameterName[0]===sParam){return sParameterName[1]===undefined?true:decodeURIComponent(sParameterName[1]);}}};